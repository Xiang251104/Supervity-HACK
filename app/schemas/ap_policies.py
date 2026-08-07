"""Public API schemas for editable AP policies and their history."""

from datetime import datetime
from typing import Annotated, Literal

from pydantic import (
    BaseModel,
    ConfigDict,
    StrictBool,
    StrictFloat,
    StrictInt,
    StrictStr,
    StringConstraints,
)

PolicyScalar = StrictStr | StrictInt | StrictFloat | StrictBool
PolicyNote = Annotated[str, StringConstraints(strip_whitespace=True, max_length=1000)]


class APPolicyResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    key: str
    name: str
    description: str
    value_type: Literal["number", "enum", "boolean", "date"]
    value: PolicyScalar
    options: list[PolicyScalar] | None = None
    unit: str | None = None
    severity: Literal["block", "escalate", "advise"]
    active: bool
    version: int
    updated_at: datetime | None = None
    updated_by: str | None = None


class APPolicyListResponse(BaseModel):
    items: list[APPolicyResponse]
    total: int
    snapshot_label: str


class APPolicyUpdateRequest(BaseModel):
    value: PolicyScalar
    note: PolicyNote = ""


class APPolicyVersionResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    version: int
    value: PolicyScalar
    previous_value: PolicyScalar | None = None
    changed_by: str | None = None
    changed_at: datetime
    note: str | None = None


class APPolicyHistoryResponse(BaseModel):
    policy_key: str
    items: list[APPolicyVersionResponse]
    total: int
