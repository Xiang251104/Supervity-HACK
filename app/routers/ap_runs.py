"""Run the Auto Orchestrator and persist everything it did.

This is the seam between the agent and the Command Center. One POST here:

  1. captures the active policies as an immutable snapshot,
  2. hands that snapshot to the Auto Orchestrator along with the invoice,
  3. streams the Orchestrator's steps into ap_run_events as they happen,
  4. gates the proposed verdict through the Policies engine BEFORE any action,
  5. logs every policy evaluation, fired or not,
  6. writes the immutable decision,
  7. opens a Workbench item when a human is required.

Money is computed here rather than in Auto, because the rule is easy to get wrong
and expensive when it is: protected value is the single largest candidate among the
Operators that FAILED, never the sum. Three Operators flagging the same invoice at
230,681.50 protect 230,681.50, not 692,044.50.
"""

from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func
from sqlalchemy.orm import Session

from ..core.database import get_db
from ..models.ap import Decision, PolicyEvaluation, Run, RunEvent, WorkbenchItem
from ..schemas.ap_runs import (
    DecisionOut,
    PolicyEvaluationOut,
    RunDetail,
    RunEventOut,
    RunListResponse,
    RunRequest,
    RunSummary,
)
from ..services.policies import build_snapshot, evaluate, record_evaluations
from ..services import slack
from ..services.supervity import SupervityClient, SupervityError, SupervityNotConfigured

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/ap/runs", tags=["AP Runs"])

# Operator result keys the Orchestrator publishes, mapped to the name a human reads.
OPERATOR_KEYS = {
    "intake_result": "AP - Intake and Normalize",
    "duplicate_result": "AP - Duplicate and Fraud Screen",
    "bank_result": "AP - Bank Change Verification",
    "match_result": "AP - Three Way Match",
    "entity_result": "AP - Entity and Approval Control",
    "po_entity_result": "AP - PO Entity Resolver",
}

PRIORITY_BY_VERDICT = {
    "PAYMENT_HOLD": "critical",
    "DATA_ERROR": "high",
    "HUMAN_REVIEW": "normal",
}


# --------------------------------------------------------------------------- #
# Parsing what Auto sent back
# --------------------------------------------------------------------------- #


def _find(payload: Any, key: str, _depth: int = 0) -> Any:
    """Locate `key` anywhere in a nested payload.

    Auto's terminal frame shape is not contractual, so we search rather than assume
    a path. Depth-limited so a pathological payload cannot hang the request.
    """
    if _depth > 6 or payload is None:
        return None
    if isinstance(payload, dict):
        if key in payload and payload[key] not in (None, "", [], {}):
            return payload[key]
        for value in payload.values():
            found = _find(value, key, _depth + 1)
            if found is not None:
                return found
    elif isinstance(payload, list):
        for value in payload:
            found = _find(value, key, _depth + 1)
            if found is not None:
                return found
    return None


def _as_list(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        return [value] if value else []
    if isinstance(value, list):
        return [str(v) for v in value if v not in (None, "")]
    return []


def _as_float(value: Any) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _collect_operator_results(payload: Any) -> dict[str, dict[str, Any]]:
    """Pull each Operator's complete result object out of the final frame."""
    results: dict[str, dict[str, Any]] = {}
    for key in OPERATOR_KEYS:
        found = _find(payload, key)
        if isinstance(found, dict):
            results[key] = found
    return results


def _money_protected(
    operator_results: dict[str, dict[str, Any]],
    verdict: str,
) -> float:
    """Largest single protected value among failing Operators. Never a sum."""
    if verdict != "PAYMENT_HOLD":
        return 0.0
    candidates = [
        _as_float(result.get("protected_value_candidate")) or 0.0
        for result in operator_results.values()
        if str(result.get("status", "")).upper() == "FAIL"
    ]
    return max(candidates) if candidates else 0.0


def _combined_reason_codes(
    payload: Any,
    operator_results: dict[str, dict[str, Any]],
) -> list[str]:
    """Prefer the Orchestrator's own combined list; fall back to merging per Operator."""
    codes = _as_list(_find(payload, "reason_codes"))
    for result in operator_results.values():
        codes.extend(_as_list(result.get("reason_codes")))
    return list(dict.fromkeys(codes))


def _default_trigger_source(canonical: dict[str, Any], trigger_source: str) -> str:
    """Derive Outlook provenance only when the caller left the API default intact."""
    if trigger_source.strip().lower() != "api":
        return trigger_source
    source_channel = str(canonical.get("source_channel") or "").strip().upper()
    return "outlook" if source_channel == "EMAIL" else "api"


def _alert_amount(canonical: dict[str, Any], amount: float | None) -> str | None:
    if amount is None:
        return None
    currency = str(canonical.get("waers") or "").strip()
    return f"{currency + ' ' if currency else ''}{amount:,.2f}"


def _safe_slack_detail(result: slack.SlackResult) -> str:
    """Persist a stable delivery description without retaining transport details."""
    if result.outcome == "success":
        return "Slack accepted the exception alert."
    if result.outcome == "not_configured":
        return "Slack is not configured; no exception alert was sent."
    return "Slack exception-alert delivery failed."


def _record_exception_alert(
    db: Session,
    *,
    run_id: str,
    belnr: str,
    canonical: dict[str, Any],
    amount: float | None,
    verdict: str,
    reason_codes: list[str],
    workbench_item_id: int,
) -> None:
    """Send one alert for an opened exception and retain its real outcome."""
    vendor = canonical.get("vendor_name") or canonical.get("vendor")
    message = slack.build_exception_alert(
        run_id=run_id,
        belnr=belnr,
        vendor=str(vendor) if vendor else None,
        amount=_alert_amount(canonical, amount),
        verdict=verdict,
        reason_codes=reason_codes,
    )
    try:
        result = slack.send(message)
    except Exception as exc:  # Notification transport is deliberately best-effort.
        logger.warning(
            "Slack exception alert failed; exception_type=%s",
            type(exc).__name__,
        )
        result = slack.SlackResult(
            sent=False,
            outcome="failed",
            detail="unexpected Slack send failure",
        )

    next_seq = (
        db.query(func.coalesce(func.max(RunEvent.seq), 0))
        .filter(RunEvent.run_id == run_id)
        .scalar()
        + 1
    )
    db.add(
        RunEvent(
            run_id=run_id,
            seq=next_seq,
            event_type="integration_activity",
            operator_name="AP Workbench",
            summary=(
                f"Exception alert for invoice {belnr} "
                f"{'sent to Slack' if result.sent else 'not sent'} ({result.outcome})."
            ),
            payload={
                "integration_key": "slack",
                "outcome": result.outcome,
                "detail": _safe_slack_detail(result),
                "run_id": run_id,
                "belnr": belnr,
                "workbench_item_id": workbench_item_id,
            },
        )
    )


# --------------------------------------------------------------------------- #
# The run
# --------------------------------------------------------------------------- #


@router.post("", response_model=RunDetail, status_code=status.HTTP_201_CREATED)
async def start_run(
    body: RunRequest,
    db: Session = Depends(get_db),
) -> RunDetail:
    run_id = body.run_id or f"RUN-{datetime.now(timezone.utc):%Y%m%d}-{uuid.uuid4().hex[:8].upper()}"

    if db.query(Run).filter(Run.run_id == run_id).first():
        raise HTTPException(status_code=409, detail=f"run_id {run_id} already exists")

    # 1. Capture policy state BEFORE anything runs. This is what makes the decision
    #    reproducible and what the judge edits to change behaviour live.
    snapshot = build_snapshot(db)

    run = Run(
        run_id=run_id,
        invoice_ref=body.invoice_ref,
        workflow_id=body.workflow_id,
        status="running",
        trigger_source=body.trigger_source,
        policy_version_label=snapshot.label,
        policy_snapshot=snapshot.as_operator_inputs(),
    )
    db.add(run)
    db.commit()

    client = SupervityClient()
    inputs = {
        "invoice_ref": body.invoice_ref,
        "policy_snapshot": snapshot.as_operator_inputs(),
        "run_id": run_id,
    }

    final_payload: dict[str, Any] = {}
    seq = 0
    started = datetime.now(timezone.utc)

    # 2 + 3. Stream the Orchestrator, persisting each frame so the dashboard moves
    #        while the run is still in flight.
    try:
        async for event in client.execute_stream(inputs, workflow_id=body.workflow_id):
            seq = event.seq
            db.add(
                RunEvent(
                    run_id=run_id,
                    seq=event.seq,
                    event_type=event.event_type,
                    operator_name=event.operator_name,
                    summary=event.summary,
                    payload=event.payload,
                )
            )
            if event.event_type == "result":
                final_payload = event.payload
            if event.event_type == "error":
                run.error = (event.summary or "Auto reported an error")[:2000]
            if event.seq % 5 == 0:
                db.commit()
        db.commit()
    except SupervityNotConfigured as exc:
        run.status = "failed"
        run.error = str(exc)
        run.finished_at = datetime.now(timezone.utc)
        db.commit()
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except SupervityError as exc:
        run.status = "failed"
        run.error = str(exc)[:2000]
        run.finished_at = datetime.now(timezone.utc)
        db.commit()
        raise HTTPException(status_code=502, detail=f"Auto run failed: {exc}") from exc

    if not final_payload:
        # An empty result is a failure, not a clean run. Never invent a verdict.
        run.status = "failed"
        run.error = run.error or "Orchestrator returned no result frame"
        run.finished_at = datetime.now(timezone.utc)
        db.commit()
        raise HTTPException(
            status_code=502,
            detail="Orchestrator produced no result. Nothing was decided and nothing was written.",
        )

    # The Operators' evidence is not in the parent run — it sits in one child run
    # per Operator. Flatten both into the shape the rest of this function reads.
    try:
        final_payload = await client.collect_run_outputs(final_payload)
    except SupervityError as exc:
        run.status = "failed"
        run.error = f"Could not read Operator results: {exc}"[:2000]
        run.finished_at = datetime.now(timezone.utc)
        db.commit()
        raise HTTPException(
            status_code=502,
            detail=f"Auto ran but its Operator results could not be read: {exc}",
        ) from exc

    workflow_run_id = _find(final_payload, "runId") or _find(final_payload, "workflowRunId")
    if workflow_run_id:
        run.workflow_run_id = str(workflow_run_id)[:128]

    # 4. Interpret what came back.
    operator_results = _collect_operator_results(final_payload)
    canonical = _find(final_payload, "canonical_invoice") or {}
    if not isinstance(canonical, dict):
        canonical = {}

    run.trigger_source = _default_trigger_source(canonical, body.trigger_source)

    belnr = str(canonical.get("belnr") or body.invoice_ref)
    proposed_verdict = str(_find(final_payload, "verdict") or "").upper() or "DATA_ERROR"
    reason_codes = _combined_reason_codes(final_payload, operator_results)

    entity = operator_results.get("entity_result", {})
    amount = _as_float(canonical.get("amount"))
    invoice_context = {
        "amount": amount,
        "amount_myr": _as_float(entity.get("amount_myr")),
        "confidence": _as_float(canonical.get("confidence")),
        "is_po": bool(canonical.get("is_po")),
        # Absent on most invoices; the cost-centre policy records that fact rather
        # than pretending the invoice named one.
        "kostl": canonical.get("kostl"),
    }

    # 5. Gate BEFORE any outward action, and log every evaluation.
    gate = evaluate(snapshot, proposed_verdict, reason_codes, invoice_context)
    record_evaluations(db, run_id, belnr, gate)

    money_protected = _money_protected(operator_results, gate.verdict)
    spend_under_review = abs(amount) if (gate.verdict == "HUMAN_REVIEW" and amount) else 0.0

    # 6. The immutable decision.
    decision = Decision(
        run_id=run_id,
        belnr=belnr,
        lifnr=canonical.get("lifnr"),
        ebeln=canonical.get("ebeln"),
        bukrs=canonical.get("bukrs_on_inv"),
        currency=canonical.get("waers"),
        amount=amount,
        amount_myr=_as_float(entity.get("amount_myr")),
        fx_rate=_as_float(entity.get("fx_rate")),
        fx_rate_date=entity.get("fx_rate_date"),
        verdict=gate.verdict,
        reason_codes=reason_codes,
        evidence={k: v for k, v in operator_results.items()},
        money_protected=money_protected,
        spend_under_review=spend_under_review,
        policy_version_label=snapshot.label,
        confidence=_as_float(canonical.get("confidence")),
        source="auto_run",
    )
    db.add(decision)
    db.commit()
    db.refresh(decision)

    # 7. Route to a human when the gate says so.
    workbench_item: WorkbenchItem | None = None
    if gate.requires_human:
        workbench_item = WorkbenchItem(
            run_id=run_id,
            decision_id=decision.id,
            belnr=belnr,
            title=f"{gate.verdict.replace('_', ' ').title()} — invoice {belnr}",
            exception_type=(reason_codes[0] if reason_codes else gate.verdict),
            priority=PRIORITY_BY_VERDICT.get(gate.verdict, "normal"),
            recommendation=gate.explanation,
            context={
                "invoice": canonical,
                "operator_results": operator_results,
                "policies_fired": gate.fired,
                "policies_evaluated": gate.evaluated,
                "policy_version": snapshot.label,
                "money_protected": money_protected,
                "spend_under_review": spend_under_review,
                "allowed_actions": gate.allowed_actions,
            },
            assigned_role=entity.get("proposed_approver_role"),
            assigned_email=entity.get("proposed_approver_email"),
            status="open",
        )
        db.add(workbench_item)

    finished = datetime.now(timezone.utc)
    run.status = "completed"
    run.finished_at = finished
    run.duration_ms = int((finished - started).total_seconds() * 1000)
    db.commit()

    if workbench_item is not None:
        db.refresh(workbench_item)
        _record_exception_alert(
            db,
            run_id=run_id,
            belnr=belnr,
            canonical=canonical,
            amount=amount,
            verdict=gate.verdict,
            reason_codes=reason_codes,
            workbench_item_id=workbench_item.id,
        )
        db.commit()

    logger.info(
        "Run %s invoice %s -> %s (%d policies evaluated, %d fired)",
        run_id, belnr, gate.verdict, len(gate.evaluated), len(gate.fired),
    )

    return _detail(db, run, workbench_item.id if workbench_item else None)


# --------------------------------------------------------------------------- #
# Reading runs back — this is what the Command Center renders
# --------------------------------------------------------------------------- #


def _detail(db: Session, run: Run, workbench_item_id: int | None = None) -> RunDetail:
    events = (
        db.query(RunEvent)
        .filter(RunEvent.run_id == run.run_id)
        .order_by(RunEvent.seq)
        .all()
    )
    decision = db.query(Decision).filter(Decision.run_id == run.run_id).first()
    evaluations = (
        db.query(PolicyEvaluation)
        .filter(PolicyEvaluation.run_id == run.run_id)
        .order_by(PolicyEvaluation.id)
        .all()
    )
    if workbench_item_id is None:
        item = db.query(WorkbenchItem).filter(WorkbenchItem.run_id == run.run_id).first()
        workbench_item_id = item.id if item else None

    return RunDetail(
        **RunSummary.model_validate(run).model_dump(),
        events=[RunEventOut.model_validate(e) for e in events],
        decision=DecisionOut.model_validate(decision) if decision else None,
        policy_evaluations=[PolicyEvaluationOut.model_validate(e) for e in evaluations],
        workbench_item_id=workbench_item_id,
    )


@router.get("", response_model=RunListResponse)
def list_runs(
    limit: int = Query(default=25, ge=1, le=200),
    run_status: str | None = Query(default=None, alias="status"),
    db: Session = Depends(get_db),
) -> RunListResponse:
    query = db.query(Run)
    if run_status:
        query = query.filter(Run.status == run_status)
    rows = query.order_by(Run.started_at.desc()).limit(limit).all()
    return RunListResponse(
        runs=[RunSummary.model_validate(r) for r in rows],
        total=query.count(),
    )


@router.get("/{run_id}", response_model=RunDetail)
def get_run(run_id: str, db: Session = Depends(get_db)) -> RunDetail:
    run = db.query(Run).filter(Run.run_id == run_id).first()
    if not run:
        raise HTTPException(status_code=404, detail="Run not found")
    return _detail(db, run)
