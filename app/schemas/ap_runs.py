"""Request and response shapes for AP Orchestrator runs."""

from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class RunRequest(BaseModel):
    """Start one Orchestrator run for one invoice."""

    invoice_ref: str = Field(min_length=1, max_length=64)
    run_id: str | None = Field(default=None, max_length=64)
    workflow_id: str | None = Field(default=None, max_length=128)
    trigger_source: str = Field(default="api", max_length=50)


class RunEventOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    seq: int
    event_type: str
    operator_name: str | None
    summary: str | None
    ts: datetime | None


class DecisionOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    belnr: str
    lifnr: str | None
    ebeln: str | None
    bukrs: str | None
    currency: str | None
    amount: float | None
    amount_myr: float | None
    verdict: str
    reason_codes: list[str]
    money_protected: float
    spend_under_review: float
    policy_version_label: str | None
    confidence: float | None
    human_status: str | None


class PolicyEvaluationOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    policy_key: str
    policy_version: int
    threshold_value: Any | None
    observed_value: Any | None
    fired: bool
    outcome: str | None
    explanation: str | None


class RunSummary(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    run_id: str
    invoice_ref: str | None
    workflow_run_id: str | None
    status: str
    trigger_source: str
    policy_version_label: str | None
    started_at: datetime | None
    finished_at: datetime | None
    duration_ms: int | None
    error: str | None


class RunDetail(RunSummary):
    events: list[RunEventOut] = []
    decision: DecisionOut | None = None
    policy_evaluations: list[PolicyEvaluationOut] = []
    workbench_item_id: int | None = None


class RunListResponse(BaseModel):
    runs: list[RunSummary]
    total: int
