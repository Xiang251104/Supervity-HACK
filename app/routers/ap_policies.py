"""Editable AP policy endpoints and append-only version history."""

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from ..core.database import get_db
from ..models.ap import Policy, PolicyVersion
from ..schemas.ap_policies import (
    APPolicyHistoryResponse,
    APPolicyListResponse,
    APPolicyResponse,
    APPolicyUpdateRequest,
)
from ..security import get_current_user
from ..services.policies import build_snapshot, normalize_policy_value, update_policy

router = APIRouter(prefix="/ap/policies", tags=["AP Policies"])


def _actor(current_user: dict | None) -> str:
    if not current_user:
        return "unknown-actor"
    return (
        current_user.get("email")
        or current_user.get("preferred_username")
        or current_user.get("sub")
        or "unknown-actor"
    )


@router.get("", response_model=APPolicyListResponse)
def list_policies(db: Session = Depends(get_db)):
    policies = db.query(Policy).order_by(Policy.key.asc()).all()
    snapshot = build_snapshot(db)
    return APPolicyListResponse(
        items=[APPolicyResponse.model_validate(policy) for policy in policies],
        total=len(policies),
        snapshot_label=snapshot.label,
    )


@router.patch("/{key}", response_model=APPolicyResponse)
def update_policy_value(
    key: str,
    update: APPolicyUpdateRequest,
    db: Session = Depends(get_db),
    current_user: dict | None = Depends(get_current_user),
):
    policy = db.query(Policy).filter(Policy.key == key).one_or_none()
    if policy is None:
        raise HTTPException(status_code=404, detail="Policy not found")

    try:
        normalized_value = normalize_policy_value(
            policy.value_type,
            policy.options,
            update.value,
        )
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=str(exc),
        ) from exc

    return update_policy(
        db,
        key,
        normalized_value,
        changed_by=_actor(current_user),
        note=update.note,
    )


@router.get("/{key}/history", response_model=APPolicyHistoryResponse)
def get_policy_history(key: str, db: Session = Depends(get_db)):
    policy = db.query(Policy).filter(Policy.key == key).one_or_none()
    if policy is None:
        raise HTTPException(status_code=404, detail="Policy not found")

    versions = (
        db.query(PolicyVersion)
        .filter(PolicyVersion.policy_key == key)
        .order_by(PolicyVersion.version.desc(), PolicyVersion.changed_at.desc())
        .all()
    )
    return APPolicyHistoryResponse(
        policy_key=key,
        items=versions,
        total=len(versions),
    )
