"""Dashboard metrics — the live operational picture of the AP agent."""

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from ..core.database import get_db
from ..schemas.ap_metrics import APMetricsResponse
from ..services.metrics import build_metrics

router = APIRouter(prefix="/ap/metrics", tags=["AP Metrics"])


@router.get("", response_model=APMetricsResponse)
def get_metrics(db: Session = Depends(get_db)):
    """Every figure here is derived from decisions the agent produced.

    Before the first run this returns zeros rather than sample data — an empty
    dashboard is honest, a populated one would not be.
    """
    return build_metrics(db)
