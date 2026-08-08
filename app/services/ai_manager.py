# app/services/ai_manager.py
"""The AI Manager — questions answered from what the agent actually recorded.

Every sentence this module produces is composed from rows in `ap_decisions`,
`ap_runs`, `ap_policies`, `ap_insights`, `ap_workbench_items` and
`ap_integrations`. There is no language model behind it and that is deliberate:

  * The standing rule for this build is "never invent a value". A model asked
    "why was invoice 5110000150 held?" can produce a fluent answer with a wrong
    number in it, and a wrong number in front of a finance judge is worse than
    no answer at all. Here, if a fact is not in the database, the reply says so.
  * It needs no API key, no network call and no extra dependency, so it cannot
    fail during a live demo and a clean clone runs it with no configuration.

Three rules hold throughout:

  1. Only `source = "auto_run"` decisions are ever read. Rows backfilled from
     the oracle for development must never surface as agent output.
  2. One invoice counts once — the most recent decision for that `belnr`.
  3. Nothing account-shaped leaves this module unredacted. Operator evidence
     carries bank numbers, and it reaches the screen through here.

This is a read-only surface. It answers questions; it never starts a run,
changes a policy or resolves an exception. A chat box that can act on the
system is a liability in a judged demo, and every one of those actions already
has its own explicit, audited endpoint.
"""

from __future__ import annotations

import re
import uuid
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Any, Iterable

from .language import policy_name, reason_label
from .slack import redact_account_numbers

if TYPE_CHECKING:  # pragma: no cover
    from sqlalchemy.orm import Session

    from ..models.ap import Decision

# An invoice number in this dataset is an unbroken run of 8-12 digits. The
# bound stops a comma-stripped amount or a year from being read as one.
_INVOICE_TOKEN = re.compile(r"\b\d{8,12}\b")

# Mirrors OPERATOR_KEYS in app/routers/ap_runs.py — that module owns the
# mapping when parsing Auto's output, this one owns how it reads on screen.
# If an Operator is renamed, change it in both places.
OPERATOR_LABELS: dict[str, str] = {
    "intake_result": "Intake and Normalize",
    "duplicate_result": "Duplicate and Fraud Screen",
    "bank_result": "Bank Change Verification",
    "match_result": "Three Way Match",
    "entity_result": "Entity and Approval Control",
    "po_entity_result": "PO Entity Resolver",
}

VERDICT_PHRASES: dict[str, str] = {
    "PAY_READY": "cleared for payment automatically, with no human involvement",
    "HUMAN_REVIEW": "routed to a person to decide",
    "PAYMENT_HOLD": "held — the payment was stopped",
    "DATA_ERROR": "stopped, because it could not be read safely enough to decide",
}

# What the assistant will say it can do, and what the empty-state bubbles ask.
# Kept in one place so the two can never drift apart.
CAPABILITIES: tuple[str, ...] = (
    "Explain one invoice — *why was invoice 5110000150 held?*",
    "Report the headline numbers — *what is our touchless rate?*",
    "List what is waiting for a person — *what is in the workbench?*",
    "Show the rules in force — *which policies are active?*",
    "Repeat what the agent noticed — *what insights do you have?*",
    "Report recent runs — *show me recent activity*",
    "Report integration health — *are the integrations healthy?*",
)


@dataclass
class GroundedAnswer:
    """A reply plus the lookups that produced it."""

    response: str
    tool_calls: list[dict[str, Any]] = field(default_factory=list)


class _Grounding:
    """Records each lookup so the reply can show its working."""

    def __init__(self) -> None:
        self.calls: list[dict[str, Any]] = []

    def record(self, name: str, args: dict[str, Any], result: Any) -> None:
        self.calls.append(
            {"id": uuid.uuid4().hex[:12], "name": name, "args": args, "result": result}
        )


# --------------------------------------------------------------------------- #
# Formatting
# --------------------------------------------------------------------------- #


def _money(value: Any) -> float:
    try:
        return float(value or 0.0)
    except (TypeError, ValueError):
        return 0.0


def _amount(value: Any, currency: str | None) -> str:
    if value is None:
        return "not recorded"
    return f"{currency or ''} {_money(value):,.2f}".strip()


def _totals(totals: dict[str, float]) -> str:
    """Currency totals, never summed across currencies."""
    live = {c: v for c, v in totals.items() if round(v, 2) > 0}
    if not live:
        return "nothing"
    return ", ".join(f"{c} {v:,.2f}" for c, v in sorted(live.items()))


def _codes(decision: "Decision") -> list[str]:
    raw = decision.reason_codes or []
    return [str(c) for c in raw] if isinstance(raw, list) else []


def _reasons_sentence(codes: Iterable[str]) -> str:
    labels = [reason_label(c) for c in codes]
    if not labels:
        return ""
    if len(labels) == 1:
        return labels[0]
    return ", ".join(labels[:-1]) + f" and {labels[-1]}"


def _when(value: datetime | None) -> str:
    if value is None:
        return "an unrecorded time"
    aware = value if value.tzinfo else value.replace(tzinfo=timezone.utc)
    return aware.strftime("%d %b %Y at %H:%M UTC")


def _bullets(lines: Iterable[str]) -> str:
    return "\n".join(f"* {line}" for line in lines)


# --------------------------------------------------------------------------- #
# Queries — every one of these is scoped to real agent output
# --------------------------------------------------------------------------- #


def _latest_decision(db: "Session", belnr: str) -> "Decision | None":
    from ..models.ap import Decision

    return (
        db.query(Decision)
        .filter(Decision.belnr == belnr, Decision.source == "auto_run")
        .order_by(Decision.created_at.desc(), Decision.id.desc())
        .first()
    )


def _latest_decisions(db: "Session") -> list["Decision"]:
    """One decision per invoice, newest first. Mirrors the dashboard's rule."""
    from .insights import latest_decisions

    return latest_decisions(db)


# --------------------------------------------------------------------------- #
# Answers
# --------------------------------------------------------------------------- #


def _answer_help(page: str | None) -> str:
    where = ""
    if page and page not in ("/", ""):
        where = f"\n\nYou are on the **{page.strip('/').replace('/', ' › ')}** page."
    return (
        "I answer from what the agent has actually recorded — every figure below "
        "comes from a stored decision, run, policy or exception, never from a guess.\n\n"
        f"{_bullets(CAPABILITIES)}"
        f"{where}"
    )


def _answer_invoice(db: "Session", belnr: str, ground: _Grounding) -> str:
    from ..models.ap import WorkbenchItem

    decision = _latest_decision(db, belnr)
    ground.record(
        "lookup_decision",
        {"belnr": belnr, "source": "auto_run"},
        {"found": decision is not None},
    )

    if decision is None:
        return (
            f"I have no decision recorded for invoice **{belnr}**.\n\n"
            "That means the agent has not processed it yet, or it was processed "
            "under a different invoice number. I will not guess at a verdict for "
            "an invoice I have not seen."
        )

    codes = _codes(decision)
    verdict_phrase = VERDICT_PHRASES.get(decision.verdict, decision.verdict)

    lines = [
        f"Invoice **{belnr}** was {verdict_phrase}.",
        "",
    ]

    facts = [
        f"**Vendor:** {decision.vendor_name or decision.lifnr or 'not recorded'}",
        f"**Amount:** {_amount(decision.amount, decision.currency)}",
    ]
    if decision.ebeln:
        facts.append(f"**Purchase order:** {decision.ebeln}")
    if decision.bukrs:
        facts.append(f"**Company:** {decision.bukrs}")
    if _money(decision.money_protected) > 0:
        facts.append(
            f"**Money protected:** {_amount(decision.money_protected, decision.currency)}"
        )
    if _money(decision.spend_under_review) > 0:
        facts.append(
            f"**Spend awaiting a decision:** "
            f"{_amount(decision.spend_under_review, decision.currency)}"
        )
    if decision.policy_version_label:
        facts.append(f"**Policies applied:** {decision.policy_version_label}")
    lines.append(_bullets(facts))

    if codes:
        lines += ["", f"**Why:** {_reasons_sentence(codes)}."]

    # The Operator explanations are the actual "why" — each one is a sentence
    # written about the values it compared, so a reviewer needs no lookup.
    evidence = decision.evidence if isinstance(decision.evidence, dict) else {}
    flagged: list[str] = []
    for key, label in OPERATOR_LABELS.items():
        result = evidence.get(key)
        if not isinstance(result, dict):
            continue
        status = str(result.get("status", "")).upper()
        if status not in ("FAIL", "REVIEW"):
            continue
        explanation = str(result.get("explanation") or "").strip()
        flagged.append(f"**{label}** ({status.lower()}): {explanation or 'no detail recorded'}")
    if flagged:
        lines += ["", "**What each check found:**", _bullets(flagged)]

    item = (
        db.query(WorkbenchItem)
        .filter(WorkbenchItem.belnr == belnr)
        .order_by(WorkbenchItem.created_at.desc(), WorkbenchItem.id.desc())
        .first()
    )
    ground.record("lookup_workbench_item", {"belnr": belnr}, {"found": item is not None})
    if item is not None:
        if item.status == "resolved":
            lines += [
                "",
                f"A reviewer resolved this on {_when(item.resolved_at)} "
                f"({item.action or 'no action recorded'}). "
                "The agent's original verdict above is unchanged — the human "
                "resolution is stored separately.",
            ]
        else:
            lines += [
                "",
                f"It is still open in the Workbench as a **{item.priority}** "
                f"exception, raised {_when(item.created_at)}.",
            ]
            if item.recommendation:
                lines.append(f"Recommended next step: {item.recommendation}")

    return "\n".join(lines)


def _answer_metrics(db: "Session", ground: _Grounding) -> str:
    from .metrics import build_metrics

    m = build_metrics(db)
    ground.record("read_dashboard_metrics", {}, {"invoices_processed": m["invoices_processed"]})

    if not m["invoices_processed"]:
        return (
            "The agent has not processed any invoices yet, so there are no "
            "numbers to report. I would rather say that than show you a figure "
            "nobody produced."
        )

    breakdown = m["verdict_breakdown"]
    lines = [
        f"Across **{m['invoices_processed']} invoices** the agent has processed:",
        "",
        _bullets(
            [
                f"**Touchless rate:** {m['touchless_rate']}% "
                f"({m['pay_ready']} cleared with no human involvement)",
                f"**Money protected:** {_totals(m['money_protected'])}",
                f"**Spend awaiting a decision:** {_totals(m['spend_under_review'])}",
                f"**Held:** {breakdown.get('PAYMENT_HOLD', 0)} · "
                f"**sent to a person:** {breakdown.get('HUMAN_REVIEW', 0)} · "
                f"**could not be read:** {breakdown.get('DATA_ERROR', 0)}",
                f"**Open exceptions:** {m['workbench_open']} "
                f"({m['workbench_resolved']} already resolved)",
            ]
        ),
    ]

    top = m["exceptions_by_type"][:3]
    if top:
        lines += [
            "",
            "**Most common reasons for an exception:**",
            _bullets(f"{reason_label(e['code'])} — {e['count']}" for e in top),
        ]
    return "\n".join(lines)


def _answer_activity(db: "Session", ground: _Grounding) -> str:
    from ..models.ap import Run

    runs = db.query(Run).order_by(Run.started_at.desc(), Run.id.desc()).limit(5).all()
    ground.record("list_recent_runs", {"limit": 5}, {"rows": len(runs)})

    if not runs:
        return "No runs have been recorded yet, so there is no activity to show."

    lines = ["The five most recent runs:", ""]
    rows = []
    for run in runs:
        duration = f"{run.duration_ms / 1000:.1f}s" if run.duration_ms else "not recorded"
        rows.append(
            f"**{run.invoice_ref or 'no invoice'}** — {run.status}, {duration}, "
            f"started {_when(run.started_at)}"
            + (f", policies {run.policy_version_label}" if run.policy_version_label else "")
        )
    lines.append(_bullets(rows))
    lines += ["", "Ask me about any of those invoice numbers and I will explain the decision."]
    return "\n".join(lines)


def _answer_workbench(db: "Session", ground: _Grounding) -> str:
    from ..models.ap import WorkbenchItem

    items = (
        db.query(WorkbenchItem)
        .filter(WorkbenchItem.status == "open")
        .order_by(WorkbenchItem.created_at.desc(), WorkbenchItem.id.desc())
        .limit(10)
        .all()
    )
    total = db.query(WorkbenchItem).filter(WorkbenchItem.status == "open").count()
    resolved = db.query(WorkbenchItem).filter(WorkbenchItem.status == "resolved").count()
    ground.record("list_workbench_items", {"status": "open"}, {"open": total, "resolved": resolved})

    if not items:
        return (
            f"Nothing is waiting for a person right now. "
            f"{resolved} exception(s) have been resolved."
        )

    by_priority: dict[str, int] = defaultdict(int)
    for item in items:
        by_priority[item.priority or "normal"] += 1

    lines = [
        f"**{total}** exception(s) are waiting for a person "
        f"({resolved} already resolved).",
        "",
        _bullets(
            f"**{item.belnr}** — {reason_label(item.exception_type)} ({item.priority})"
            for item in items
        ),
    ]
    if total > len(items):
        lines.append(f"\nShowing the {len(items)} most recent of {total}.")
    return "\n".join(lines)


def _answer_policies(db: "Session", ground: _Grounding) -> str:
    from ..models.ap import Policy

    policies = db.query(Policy).filter(Policy.active.is_(True)).order_by(Policy.key).all()
    ground.record("list_active_policies", {"active": True}, {"rows": len(policies)})

    if not policies:
        return "No policies are active. Nothing is gating the agent's decisions."

    rows = []
    for p in policies:
        unit = f" {p.unit}" if p.unit else ""
        rows.append(
            f"**{policy_name(p.key)}** — {p.value}{unit} "
            f"(version {p.version}, {p.severity})"
        )
    return "\n".join(
        [
            f"**{len(policies)}** policies are active. Every one is editable in "
            "AI Policies without touching code, and each is evaluated before the "
            "agent acts, not after.",
            "",
            _bullets(rows),
        ]
    )


def _answer_insights(db: "Session", ground: _Grounding) -> str:
    from ..models.ap import Insight

    insights = (
        db.query(Insight)
        .filter(Insight.dismissed.is_(False))
        .order_by(Insight.computed_at.desc(), Insight.id.desc())
        .limit(5)
        .all()
    )
    ground.record("list_insights", {"dismissed": False, "limit": 5}, {"rows": len(insights)})

    if not insights:
        return (
            "No insights have been computed yet. They are derived from processed "
            "decisions, so they appear once the agent has run."
        )

    lines = ["What the agent has noticed:", ""]
    for i in insights:
        metric = ""
        if i.metric_value is not None:
            metric = f" ({i.metric_value:,.2f}{' ' + i.metric_unit if i.metric_unit else ''})"
        lines.append(f"**{i.title}**{metric} — _{i.severity}_")
        lines.append(f"{i.body}")
        if i.action_label:
            lines.append(f"> Suggested action: {i.action_label}")
        lines.append("")
    return "\n".join(lines).strip()


def _answer_integrations(db: "Session", ground: _Grounding) -> str:
    from ..models.ap import Integration

    rows = db.query(Integration).order_by(Integration.key).all()
    ground.record("list_integrations", {}, {"rows": len(rows)})

    if not rows:
        return "No integrations are registered."

    lines = []
    for r in rows:
        checked = f", last checked {_when(r.last_checked_at)}" if r.last_checked_at else ""
        lines.append(
            f"**{r.name}** ({r.category.replace('_', ' ')}) — **{r.status}**{checked}"
        )
    return "\n".join(
        [
            "Integration health, measured rather than declared:",
            "",
            _bullets(lines),
            "",
            "Full detail, including latency and the last measurement method, is on "
            "the Data Manager page.",
        ]
    )


def _answer_fraud(db: "Session", ground: _Grounding) -> str:
    """The hero case. Grounded in decisions, so the count is always the real one."""
    fraud_codes = {"BEC_SUSPECTED", "BANK_CHANGE_UNVERIFIED", "BANK_ACCOUNT_UNKNOWN", "BANK_MISMATCH"}

    decisions = _latest_decisions(db)
    hits = [d for d in decisions if fraud_codes & set(_codes(d))]
    ground.record(
        "scan_decisions_for_bank_risk",
        {"reason_codes": sorted(fraud_codes)},
        {"scanned": len(decisions), "matched": len(hits)},
    )

    if not decisions:
        return "The agent has not processed any invoices yet, so there is nothing to scan."
    if not hits:
        return (
            f"None of the {len(decisions)} invoices processed so far carry a "
            "bank-change or payment-redirection flag."
        )

    protected: dict[str, float] = defaultdict(float)
    for d in hits:
        protected[d.currency or "UNKNOWN"] += abs(_money(d.money_protected))

    lines = [
        f"**{len(hits)}** of {len(decisions)} processed invoices carry a "
        f"bank-change or payment-redirection flag, protecting {_totals(protected)}.",
        "",
        _bullets(
            f"**{d.belnr}** — {d.vendor_name or d.lifnr or 'vendor not recorded'}, "
            f"{_amount(d.amount, d.currency)}, {d.verdict.replace('_', ' ').lower()} "
            f"({_reasons_sentence(c for c in _codes(d) if c in fraud_codes)})"
            for d in hits[:10]
        ),
    ]
    return "\n".join(lines)


def _answer_unknown(page: str | None) -> str:
    return (
        "I could not match that to anything I can answer from stored records, "
        "and I will not improvise an answer.\n\n"
        "Here is what I can tell you, all of it from real agent output:\n\n"
        f"{_bullets(CAPABILITIES)}"
    )


# --------------------------------------------------------------------------- #
# Intent
# --------------------------------------------------------------------------- #

# Ordered — the first matching group wins, so the specific beats the general.
_INTENTS: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("help", ("what can you", "what do you do", "how can you help", "capabilities", "help me with")),
    (
        "fraud",
        ("fraud", "bec", "bank change", "bank-change", "redirect", "spoof", "impersonat", "scam"),
    ),
    (
        "workbench",
        ("workbench", "queue", "waiting", "pending", "exception", "escalat", "needs a human",
         "for review"),
    ),
    ("policies", ("policy", "policies", "rule", "rules", "threshold", "tolerance", "limit")),
    ("insights", ("insight", "noticed", "pattern", "anomal", "trend", "observ")),
    (
        "integrations",
        ("integration", "data manager", "connector", "healthy", "health", "connected", "slack",
         "outlook", "supabase"),
    ),
    (
        "metrics",
        ("touchless", "metric", "how are we", "how many", "money protected", "protected",
         "performance", "summary", "dashboard", "overall", "rate", "statistics", "stats",
         "processed"),
    ),
    (
        "activity",
        ("recent activity", "activity", "recent run", "latest run", "last run", "what happened",
         "runs", "history"),
    ),
)

# Phrases that mean "the invoice we were already talking about".
_FOLLOW_UP = (
    "why", "held", "hold", "blocked", "flagged", "explain", "what about it", "that invoice",
    "this invoice", "it ",
)


def _detect_intent(message: str) -> str:
    lowered = message.lower()
    for intent, needles in _INTENTS:
        if any(needle in lowered for needle in needles):
            return intent
    return "unknown"


def _invoice_from_history(history: Iterable[Any]) -> str | None:
    """The last invoice number either side mentioned, newest first.

    This is what lets "why was it held?" work as a follow-up without a model:
    the subject carries over from the previous turn.
    """
    for turn in reversed(list(history)):
        content = getattr(turn, "content", "") or ""
        found = _INVOICE_TOKEN.findall(content)
        if found:
            return found[-1]
    return None


# --------------------------------------------------------------------------- #
# Entry point
# --------------------------------------------------------------------------- #


def answer(
    db: "Session",
    message: str,
    history: Iterable[Any] = (),
    page: str | None = None,
) -> GroundedAnswer:
    """Answer one question from stored records, or say plainly that we cannot."""
    ground = _Grounding()
    text = (message or "").strip()
    if not text:
        return GroundedAnswer(_answer_help(page), ground.calls)

    # An invoice number in the question always wins — it is the most specific
    # thing anyone can ask, and the one the demo turns on.
    explicit = _INVOICE_TOKEN.findall(text)
    if explicit:
        body = _answer_invoice(db, explicit[0], ground)
        return GroundedAnswer(redact_account_numbers(body), ground.calls)

    intent = _detect_intent(text)
    lowered = text.lower()

    # "Why was it held?" — carry the subject over from the previous turn, but
    # only when the question reads like a follow-up about one invoice.
    if intent in ("unknown", "metrics") and any(w in lowered for w in _FOLLOW_UP):
        carried = _invoice_from_history(history)
        if carried:
            body = _answer_invoice(db, carried, ground)
            return GroundedAnswer(redact_account_numbers(body), ground.calls)

    handlers = {
        "help": lambda: _answer_help(page),
        "fraud": lambda: _answer_fraud(db, ground),
        "workbench": lambda: _answer_workbench(db, ground),
        "policies": lambda: _answer_policies(db, ground),
        "insights": lambda: _answer_insights(db, ground),
        "integrations": lambda: _answer_integrations(db, ground),
        "metrics": lambda: _answer_metrics(db, ground),
        "activity": lambda: _answer_activity(db, ground),
    }
    body = handlers.get(intent, lambda: _answer_unknown(page))()
    return GroundedAnswer(redact_account_numbers(body), ground.calls)
