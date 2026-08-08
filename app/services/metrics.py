# app/services/metrics.py
"""Headline numbers for the Command Center dashboard.

Everything here is derived from what the agent actually produced — `ap_decisions`,
`ap_runs` and `ap_workbench_items`. No sample figures, no projections.

The same two rules that govern the Insights engine apply:

  1. One invoice counts once. A re-run appends another `ap_decisions` row for the same
     `belnr`, so the population is the latest decision per invoice.
  2. Money is grouped by currency and never summed across them, and protected value is
     never conflated with spend awaiting a decision.
"""

from __future__ import annotations

import logging
from collections import defaultdict
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Any

from .insights import _codes, _money, latest_decisions

if TYPE_CHECKING:  # pragma: no cover
    from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)

VERDICTS = ("PAY_READY", "HUMAN_REVIEW", "PAYMENT_HOLD", "DATA_ERROR")

# How long an exception has been waiting for a human.
AGING_BUCKETS = (
    ("0-1 days", 0, 1),
    ("2-3 days", 2, 3),
    ("4-7 days", 4, 7),
    ("8+ days", 8, None),
)


def _aging_bucket(days: int) -> str:
    for label, low, high in AGING_BUCKETS:
        if days >= low and (high is None or days <= high):
            return label
    return AGING_BUCKETS[-1][0]


def _as_aware(value: datetime | None) -> datetime | None:
    """Postgres gives tz-aware datetimes, SQLite gives naive ones."""
    if value is None:
        return None
    return value if value.tzinfo else value.replace(tzinfo=timezone.utc)


def build_metrics(db: "Session") -> dict[str, Any]:
    from ..models.ap import Run, WorkbenchItem

    decisions = latest_decisions(db)
    processed = len(decisions)

    verdict_counts = {v: 0 for v in VERDICTS}
    for d in decisions:
        verdict_counts[d.verdict] = verdict_counts.get(d.verdict, 0) + 1

    cleared = verdict_counts.get("PAY_READY", 0)
    touchless_rate = round(100.0 * cleared / processed, 1) if processed else 0.0

    protected: dict[str, float] = defaultdict(float)
    under_review: dict[str, float] = defaultdict(float)
    for d in decisions:
        currency = d.currency or "UNKNOWN"
        protected[currency] += abs(_money(d.money_protected))
        under_review[currency] += abs(_money(d.spend_under_review))
    protected = {c: round(v, 2) for c, v in protected.items() if v > 0}
    under_review = {c: round(v, 2) for c, v in under_review.items() if v > 0}

    exceptions_by_type: dict[str, int] = defaultdict(int)
    for d in decisions:
        if d.verdict == "PAY_READY":
            continue
        for code in _codes(d):
            exceptions_by_type[code] += 1
    ranked_exceptions = sorted(exceptions_by_type.items(), key=lambda kv: kv[1], reverse=True)

    confidences = [_money(d.confidence) for d in decisions if d.confidence is not None]
    avg_confidence = round(sum(confidences) / len(confidences), 3) if confidences else None

    open_items = db.query(WorkbenchItem).filter(WorkbenchItem.status == "open").all()
    resolved_count = db.query(WorkbenchItem).filter(WorkbenchItem.status == "resolved").count()

    now = datetime.now(timezone.utc)
    aging: dict[str, int] = {label: 0 for label, _, _ in AGING_BUCKETS}
    for item in open_items:
        created = _as_aware(item.created_at)
        days = max((now - created).days, 0) if created else 0
        aging[_aging_bucket(days)] += 1

    priority_counts: dict[str, int] = defaultdict(int)
    for item in open_items:
        priority_counts[item.priority or "normal"] += 1

    recent_runs = (
        db.query(Run).order_by(Run.started_at.desc()).limit(5).all()
    )
    completed = [r for r in recent_runs if r.duration_ms]
    avg_duration = (
        int(sum(r.duration_ms for r in completed) / len(completed)) if completed else None
    )

    latest_decision_at = max(
        (_as_aware(d.created_at) for d in decisions if d.created_at), default=None
    )

    return {
        "invoices_processed": processed,
        "touchless_rate": touchless_rate,
        "pay_ready": cleared,
        "verdict_breakdown": verdict_counts,
        "money_protected": protected,
        "spend_under_review": under_review,
        "exceptions_by_type": [
            {"code": code, "count": count} for code, count in ranked_exceptions
        ],
        "workbench_open": len(open_items),
        "workbench_resolved": resolved_count,
        "workbench_priority": dict(priority_counts),
        "exception_aging": [
            {"bucket": label, "count": aging[label]} for label, _, _ in AGING_BUCKETS
        ],
        "average_confidence": avg_confidence,
        "total_runs": db.query(Run).count(),
        "average_run_ms": avg_duration,
        "recent_runs": [
            {
                "run_id": r.run_id,
                "invoice_ref": r.invoice_ref,
                "status": r.status,
                "started_at": _as_aware(r.started_at),
                "duration_ms": r.duration_ms,
                "policy_version_label": r.policy_version_label,
            }
            for r in recent_runs
        ],
        "last_decision_at": latest_decision_at,
    }
