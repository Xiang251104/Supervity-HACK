"""Human-review queue and resolution endpoints for AP exceptions."""

from datetime import datetime, timezone
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import case, func
from sqlalchemy.orm import Session

from ..core.database import get_db
from ..models.ap import Decision, RunEvent, WorkbenchItem
from ..schemas.ap_workbench import (
    WorkbenchDecision,
    WorkbenchItemDetail,
    WorkbenchItemSummary,
    WorkbenchListResponse,
    WorkbenchResolveRequest,
)
from ..security import get_current_user

router = APIRouter(prefix="/ap/workbench", tags=["AP Workbench"])


def _reviewer_name(current_user: dict | None) -> str:
    if not current_user:
        return "unknown-reviewer"
    return (
        current_user.get("email")
        or current_user.get("preferred_username")
        or current_user.get("sub")
        or "unknown-reviewer"
    )


def _decision_schema(decision: Decision | None) -> WorkbenchDecision | None:
    return WorkbenchDecision.model_validate(decision) if decision else None


def _detail(item: WorkbenchItem, decision: Decision | None) -> WorkbenchItemDetail:
    return WorkbenchItemDetail(
        id=item.id,
        run_id=item.run_id,
        decision_id=item.decision_id,
        belnr=item.belnr,
        title=item.title,
        exception_type=item.exception_type,
        priority=item.priority,
        recommendation=item.recommendation,
        context=item.context,
        assigned_role=item.assigned_role,
        assigned_email=item.assigned_email,
        status=item.status,
        created_at=item.created_at,
        resolved_at=item.resolved_at,
        resolved_by=item.resolved_by,
        action=item.action,
        note=item.note,
        decision=_decision_schema(decision),
    )


@router.get("", response_model=WorkbenchListResponse)
def list_workbench_items(
    item_status: Literal["open", "resolved"] | None = Query(default=None, alias="status"),
    priority: Literal["critical", "high", "normal"] | None = None,
    db: Session = Depends(get_db),
):
    query = db.query(WorkbenchItem, Decision).outerjoin(
        Decision, WorkbenchItem.decision_id == Decision.id
    )
    if item_status:
        query = query.filter(WorkbenchItem.status == item_status)
    if priority:
        query = query.filter(WorkbenchItem.priority == priority)

    priority_order = case(
        (WorkbenchItem.priority == "critical", 0),
        (WorkbenchItem.priority == "high", 1),
        else_=2,
    )
    rows = query.order_by(priority_order, WorkbenchItem.created_at.desc()).all()
    items = [
        WorkbenchItemSummary(
            id=item.id,
            run_id=item.run_id,
            decision_id=item.decision_id,
            belnr=item.belnr,
            title=item.title,
            exception_type=item.exception_type,
            priority=item.priority,
            status=item.status,
            assigned_role=item.assigned_role,
            created_at=item.created_at,
            verdict=decision.verdict if decision else None,
            currency=decision.currency if decision else None,
            amount=decision.amount if decision else None,
            money_protected=decision.money_protected if decision else None,
        )
        for item, decision in rows
    ]
    return WorkbenchListResponse(items=items, total=len(items))


@router.get("/{item_id}", response_model=WorkbenchItemDetail)
def get_workbench_item(item_id: int, db: Session = Depends(get_db)):
    item = db.get(WorkbenchItem, item_id)
    if not item:
        raise HTTPException(status_code=404, detail="Workbench item not found")
    decision = db.get(Decision, item.decision_id) if item.decision_id else None
    return _detail(item, decision)


@router.post("/{item_id}/resolve", response_model=WorkbenchItemDetail)
def resolve_workbench_item(
    item_id: int,
    resolution: WorkbenchResolveRequest,
    db: Session = Depends(get_db),
    current_user: dict | None = Depends(get_current_user),
):
    try:
        item = (
            db.query(WorkbenchItem)
            .filter(WorkbenchItem.id == item_id)
            .with_for_update()
            .first()
        )
        if not item:
            raise HTTPException(status_code=404, detail="Workbench item not found")
        if item.status == "resolved":
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Workbench item is already resolved",
            )
        if not item.decision_id:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Workbench item has no linked decision",
            )

        decision = (
            db.query(Decision)
            .filter(Decision.id == item.decision_id)
            .with_for_update()
            .first()
        )
        if not decision:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Linked decision was not found",
            )

        reviewer = _reviewer_name(current_user)
        now = datetime.now(timezone.utc)
        human_status = {
            "approve": "APPROVED",
            "reject": "REJECTED",
            "request_info": "PENDING_INFORMATION",
        }[resolution.action]

        item.status = "open" if resolution.action == "request_info" else "resolved"
        item.resolved_at = None if resolution.action == "request_info" else now
        item.resolved_by = reviewer
        item.action = resolution.action
        item.note = resolution.note

        decision.human_status = human_status
        decision.resolved_at = None if resolution.action == "request_info" else now
        decision.resolved_by = reviewer
        decision.resolution_action = resolution.action
        decision.resolution_note = resolution.note

        next_seq = (
            db.query(func.coalesce(func.max(RunEvent.seq), 0))
            .filter(RunEvent.run_id == item.run_id)
            .scalar()
            + 1
        )
        db.add(
            RunEvent(
                run_id=item.run_id,
                seq=next_seq,
                event_type="human_action",
                operator_name="AP Workbench",
                summary=f"Reviewer selected {resolution.action} for invoice {item.belnr}.",
                payload={
                    "action": resolution.action,
                    "note": resolution.note,
                    "reviewer": reviewer,
                    "workbench_item_id": item.id,
                    "decision_id": decision.id,
                    "human_status": human_status,
                },
            )
        )
        db.commit()
        db.refresh(item)
        db.refresh(decision)
        return _detail(item, decision)
    except HTTPException:
        db.rollback()
        raise
    except Exception:
        db.rollback()
        raise
