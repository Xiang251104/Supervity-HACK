"""Authenticated AP integration-health snapshot and refresh endpoints."""

from typing import cast

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from ..core.database import get_db
from ..models.ap import Integration
from ..schemas.ap_data_manager import (
    DataManagerResponse,
    IntegrationHealthSummary,
    MeasurementMethod,
    SafeErrorCategory,
    StatusCounts,
)
from ..security import get_current_user
from ..services.integration_health import IntegrationHealthService


router = APIRouter(prefix="/ap/data-manager", tags=["AP Data Manager"])

_MEASUREMENT_METHODS: frozenset[str] = frozenset(
    {
        "read_only_endpoint_probe",
        "recorded_run_activity",
        "recorded_delivery_activity",
    }
)
_ERROR_CATEGORIES: frozenset[str] = frozenset(
    {
        "authentication_failure",
        "timeout",
        "rate_limited",
        "connector_failure",
    }
)
_SAFE_MESSAGES: frozenset[str] = frozenset(
    {
        "Health probe is not configured",
        "Latest Slack delivery attempt failed",
        "No Outlook-triggered runs recorded",
        "No Slack delivery attempts recorded",
        "Outlook-triggered run activity is recent",
        "Outlook-triggered run activity is stale",
        "Read-only query failed",
        "Read-only query succeeded",
        "Read-only run listing failed",
        "Read-only run listing succeeded",
        "Slack delivery activity is recent",
        "Slack delivery activity is stale",
    }
)


def get_integration_health_service(
    db: Session = Depends(get_db),
) -> IntegrationHealthService:
    return IntegrationHealthService(db)


def _safe_detail(value: object) -> dict[str, str | int] | None:
    if not isinstance(value, dict):
        return None

    detail: dict[str, str | int] = {}
    message = value.get("message")
    if isinstance(message, str) and message in _SAFE_MESSAGES:
        detail["message"] = message
    http_status = value.get("http_status")
    if type(http_status) is int:
        detail["http_status"] = http_status
    return detail or None


def _measurement_method(value: object) -> MeasurementMethod | None:
    if isinstance(value, str) and value in _MEASUREMENT_METHODS:
        return cast(MeasurementMethod, value)
    return None


def _last_error(row: Integration) -> SafeErrorCategory | None:
    if isinstance(row.last_error, str) and row.last_error in _ERROR_CATEGORIES:
        return cast(SafeErrorCategory, row.last_error)
    if row.status == "down":
        return "connector_failure"
    return None


def _summary(row: Integration) -> IntegrationHealthSummary:
    stored_detail = row.detail if isinstance(row.detail, dict) else {}
    return IntegrationHealthSummary(
        key=row.key,
        name=row.name,
        category=row.category,
        purpose=row.purpose,
        status=row.status,
        measurement_method=_measurement_method(stored_detail.get("measurement_method")),
        last_checked_at=row.last_checked_at,
        latency_ms=row.latency_ms,
        records_seen=row.records_seen,
        last_activity_at=row.last_activity_at,
        detail=_safe_detail(stored_detail),
        last_error=_last_error(row),
    )


def _response(
    rows: list[Integration],
    *,
    freshness_hours: float,
    partial_failure: bool,
) -> DataManagerResponse:
    integrations = [_summary(row) for row in rows]
    count_values = {
        "healthy": 0,
        "degraded": 0,
        "down": 0,
        "unknown": 0,
    }
    for integration in integrations:
        count_values[integration.status] += 1
    return DataManagerResponse(
        integrations=integrations,
        counts=StatusCounts(**count_values),
        freshness_hours=freshness_hours,
        partial_failure=partial_failure,
    )


@router.get("", response_model=DataManagerResponse)
def get_data_manager(
    _current_user: dict | None = Depends(get_current_user),
    service: IntegrationHealthService = Depends(get_integration_health_service),
) -> DataManagerResponse:
    rows = service.snapshot()
    return _response(
        rows,
        freshness_hours=service.max_age_hours,
        partial_failure=any(row.status == "down" for row in rows),
    )


@router.post("/refresh", response_model=DataManagerResponse)
async def refresh_data_manager(
    _current_user: dict | None = Depends(get_current_user),
    service: IntegrationHealthService = Depends(get_integration_health_service),
) -> DataManagerResponse:
    rows, partial_failure = await service.refresh()
    return _response(
        rows,
        freshness_hours=service.max_age_hours,
        partial_failure=partial_failure,
    )
