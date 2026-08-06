"""Safe public response contracts for AP integration health."""

from datetime import datetime
from typing import Literal

from pydantic import BaseModel


IntegrationStatus = Literal["healthy", "degraded", "down", "unknown"]
MeasurementMethod = Literal[
    "read_only_endpoint_probe",
    "recorded_run_activity",
    "recorded_delivery_activity",
]
SafeErrorCategory = Literal[
    "authentication_failure",
    "timeout",
    "rate_limited",
    "connector_failure",
]
SafeDetailValue = str | int | float | bool | None


class IntegrationHealthSummary(BaseModel):
    key: str
    name: str
    category: str
    purpose: str
    status: IntegrationStatus
    measurement_method: MeasurementMethod | None
    last_checked_at: datetime | None
    latency_ms: int | None
    records_seen: int
    last_activity_at: datetime | None
    detail: dict[str, SafeDetailValue] | None
    last_error: SafeErrorCategory | None


class StatusCounts(BaseModel):
    healthy: int = 0
    degraded: int = 0
    down: int = 0
    unknown: int = 0


class DataManagerResponse(BaseModel):
    integrations: list[IntegrationHealthSummary]
    counts: StatusCounts
    freshness_hours: float
    partial_failure: bool
