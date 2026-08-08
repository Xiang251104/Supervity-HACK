"""Response shape for the AP dashboard."""

from datetime import datetime

from pydantic import BaseModel


class ExceptionCount(BaseModel):
    code: str
    count: int


class AgingBucket(BaseModel):
    bucket: str
    count: int


class RecentRun(BaseModel):
    run_id: str
    invoice_ref: str | None = None
    status: str
    started_at: datetime | None = None
    duration_ms: int | None = None
    policy_version_label: str | None = None


class APMetricsResponse(BaseModel):
    invoices_processed: int
    touchless_rate: float
    pay_ready: int
    verdict_breakdown: dict[str, int]

    # Grouped by currency — never summed across them.
    money_protected: dict[str, float]
    spend_under_review: dict[str, float]

    exceptions_by_type: list[ExceptionCount]
    workbench_open: int
    workbench_resolved: int
    workbench_priority: dict[str, int]
    exception_aging: list[AgingBucket]

    average_confidence: float | None = None
    total_runs: int
    average_run_ms: int | None = None
    recent_runs: list[RecentRun]
    last_decision_at: datetime | None = None
