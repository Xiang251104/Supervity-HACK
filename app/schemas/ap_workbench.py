"""Public API schemas for the AP human-review Workbench."""

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator


class WorkbenchDecision(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    run_id: str
    belnr: str
    lifnr: str | None = None
    ebeln: str | None = None
    vendor_name: str | None = None
    currency: str | None = None
    amount: float | None = None
    verdict: str
    reason_codes: list[str]
    evidence: dict[str, Any] | None = None
    money_protected: float
    spend_under_review: float
    policy_version_label: str | None = None
    confidence: float | None = None
    human_status: str | None = None
    resolved_by: str | None = None
    resolved_at: datetime | None = None
    resolution_action: str | None = None
    resolution_note: str | None = None


class WorkbenchItemSummary(BaseModel):
    id: int
    run_id: str
    decision_id: int | None = None
    belnr: str
    title: str
    exception_type: str
    priority: str
    status: str
    assigned_role: str | None = None
    created_at: datetime
    verdict: str | None = None
    currency: str | None = None
    amount: float | None = None
    money_protected: float | None = None


class WorkbenchListResponse(BaseModel):
    items: list[WorkbenchItemSummary]
    total: int


class WorkbenchItemDetail(BaseModel):
    id: int
    run_id: str
    decision_id: int | None = None
    belnr: str
    title: str
    exception_type: str
    priority: str
    recommendation: str | None = None
    context: dict[str, Any] | None = None
    assigned_role: str | None = None
    assigned_email: str | None = None
    status: str
    created_at: datetime
    resolved_at: datetime | None = None
    resolved_by: str | None = None
    action: str | None = None
    note: str | None = None
    decision: WorkbenchDecision | None = None


class WorkbenchResolveRequest(BaseModel):
    action: Literal["approve", "reject", "request_info"]
    note: str = Field(min_length=1, max_length=4000)

    @field_validator("note")
    @classmethod
    def note_must_not_be_blank(cls, value: str) -> str:
        note = value.strip()
        if not note:
            raise ValueError("Reviewer note must not be blank")
        return note
