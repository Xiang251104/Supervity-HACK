"""Response shapes for the AI Insights surface."""

from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict


class APInsight(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    key: str
    title: str
    severity: str
    body: str
    metric_value: float | None = None
    metric_unit: str | None = None
    evidence: dict[str, Any] | None = None
    action_label: str | None = None
    action_type: str | None = None
    action_payload: dict[str, Any] | None = None
    computed_at: datetime | None = None
    dismissed: bool


class APInsightListResponse(BaseModel):
    items: list[APInsight]
    total: int
    critical: int
    warning: int
    info: int
    decisions_analysed: int
    computed_at: datetime | None = None
