"""AI Insights — patterns and anomalies computed from what the agent processed."""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from ..core.database import get_db
from ..models.ap import Insight
from ..schemas.ap_insights import APInsight, APInsightListResponse
from ..services.insights import SEVERITY_ORDER, latest_decisions, refresh_insights

router = APIRouter(prefix="/ap/insights", tags=["AP Insights"])


def _response(db: Session, rows: list[Insight]) -> APInsightListResponse:
    visible = [r for r in rows if not r.dismissed]
    # One invoice counts once, matching the population the insights were computed from.
    analysed = len(latest_decisions(db))
    return APInsightListResponse(
        items=[APInsight.model_validate(r) for r in visible],
        total=len(visible),
        critical=sum(1 for r in visible if r.severity == "critical"),
        warning=sum(1 for r in visible if r.severity == "warning"),
        info=sum(1 for r in visible if r.severity == "info"),
        decisions_analysed=analysed,
        computed_at=max((r.computed_at for r in rows if r.computed_at), default=None),
    )


@router.get("", response_model=APInsightListResponse)
def list_insights(db: Session = Depends(get_db)):
    """Return the stored insights.

    Deliberately read-only. An earlier version recomputed here when the table was empty,
    which meant two concurrent GETs — React Strict Mode fires the page's effect twice —
    could each insert a full set and double every card. The client calls /refresh instead.
    """
    rows = db.query(Insight).all()
    rows.sort(key=lambda r: (SEVERITY_ORDER.get(r.severity, 3), r.key))
    return _response(db, rows)


@router.post("/refresh", response_model=APInsightListResponse)
def recompute_insights(db: Session = Depends(get_db)):
    """Recompute every insight from current decisions."""
    rows = refresh_insights(db)
    return _response(db, rows)


@router.post("/{insight_id}/dismiss", response_model=APInsight)
def dismiss_insight(insight_id: int, db: Session = Depends(get_db)):
    insight = db.get(Insight, insight_id)
    if not insight:
        raise HTTPException(status_code=404, detail="Insight not found")
    insight.dismissed = True
    db.commit()
    db.refresh(insight)
    return APInsight.model_validate(insight)


@router.delete("/{insight_id}/dismiss", response_model=APInsight)
def restore_insight(insight_id: int, db: Session = Depends(get_db)):
    """Undo a dismissal. Without this a stray click hides a finding permanently."""
    insight = db.get(Insight, insight_id)
    if not insight:
        raise HTTPException(status_code=404, detail="Insight not found")
    insight.dismissed = False
    db.commit()
    db.refresh(insight)
    return APInsight.model_validate(insight)
