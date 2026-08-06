"""Pure integration-health status and safe diagnostic contracts."""

from __future__ import annotations

import os
import re
import time
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from math import isfinite
from typing import Any, Callable, Literal, TypeAlias

import httpx
from sqlalchemy import cast, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Session

from app.models.ap import Integration, Run, RunEvent
from app.services.supervity import SupervityClient, SupervityError


IntegrationStatus = Literal["healthy", "degraded", "down", "unknown"]
SafeDetailValue: TypeAlias = str | int | float | bool | None
SafeErrorCategory = Literal[
    "timeout",
    "authentication_failure",
    "rate_limited",
    "connector_failure",
]
_CONTENT_RANGE_PATTERN = re.compile(
    r"(?P<start>[0-9]+)-(?P<end>[0-9]+)/(?P<total>[0-9]+)"
)


@dataclass(frozen=True)
class IntegrationMeasurement:
    """A point-in-time integration measurement containing only safe details."""

    status: IntegrationStatus
    measurement_method: str
    checked_at: datetime
    latency_ms: int | None = None
    records_seen: int = 0
    last_activity_at: datetime | None = None
    detail: dict[str, SafeDetailValue] = field(default_factory=dict)
    last_error: SafeErrorCategory | None = None

    def __post_init__(self) -> None:
        if self.latency_ms is not None and type(self.latency_ms) is not int:
            raise TypeError("latency_ms must be an integer or None")


def activity_status(
    last_activity_at: datetime | None,
    now: datetime,
    max_age_hours: float,
) -> IntegrationStatus:
    """Classify activity freshness with an inclusive healthy boundary."""

    if last_activity_at is None:
        return "unknown"
    if now - last_activity_at <= timedelta(hours=max_age_hours):
        return "healthy"
    return "degraded"


def safe_error_category(value: object) -> SafeErrorCategory:
    """Map an error to a fixed category without returning its raw text."""

    text = str(value).lower()
    if "timeout" in text:
        return "timeout"
    if "401" in text or "403" in text or "auth" in text:
        return "authentication_failure"
    return "connector_failure"


def _content_range_total(value: str | None) -> int:
    """Return a non-negative total from a Content-Range header."""

    if value is None:
        return 0
    match = _CONTENT_RANGE_PATTERN.fullmatch(value)
    if match is None:
        return 0
    start = int(match.group("start"))
    end = int(match.group("end"))
    total = int(match.group("total"))
    if total == 0 or start > end or end >= total:
        return 0
    return total


class SupabaseHealthClient:
    """Read-only Supabase health probe with allowlisted diagnostics."""

    def __init__(
        self,
        url: str,
        service_key: str,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        self.url = url.strip()
        self.service_key = service_key.strip()
        self._client = client

    @classmethod
    def from_env(cls) -> "SupabaseHealthClient":
        return cls(
            url=os.getenv("SUPABASE_URL", "").strip(),
            service_key=os.getenv("SUPABASE_SERVICE_KEY", "").strip(),
        )

    async def measure(self, now: datetime) -> IntegrationMeasurement:
        if not self.url or not self.service_key:
            return IntegrationMeasurement(
                status="unknown",
                measurement_method="read_only_endpoint_probe",
                checked_at=now,
                detail={"message": "Health probe is not configured"},
            )

        owns_client = self._client is None
        client = (
            self._client
            if self._client is not None
            else httpx.AsyncClient(timeout=10.0)
        )
        started = time.monotonic()
        try:
            response = await client.get(
                f"{self.url.rstrip('/')}/rest/v1/ap_invoices",
                params={"select": "belnr", "limit": "1"},
                headers={
                    "apikey": self.service_key,
                    "Authorization": f"Bearer {self.service_key}",
                    "Prefer": "count=exact",
                    "Range": "0-0",
                },
            )
            latency_ms = int((time.monotonic() - started) * 1000)
            if response.status_code in {200, 206}:
                return IntegrationMeasurement(
                    status="healthy",
                    measurement_method="read_only_endpoint_probe",
                    checked_at=now,
                    latency_ms=latency_ms,
                    records_seen=_content_range_total(
                        response.headers.get("Content-Range")
                    ),
                    last_activity_at=now,
                    detail={
                        "message": "Read-only query succeeded",
                        "http_status": response.status_code,
                    },
                )

            error_category: SafeErrorCategory = (
                "authentication_failure"
                if response.status_code in {401, 403}
                else "connector_failure"
            )
            return IntegrationMeasurement(
                status="down",
                measurement_method="read_only_endpoint_probe",
                checked_at=now,
                latency_ms=latency_ms,
                detail={
                    "message": "Read-only query failed",
                    "http_status": response.status_code,
                },
                last_error=error_category,
            )
        except httpx.TimeoutException:
            return IntegrationMeasurement(
                status="down",
                measurement_method="read_only_endpoint_probe",
                checked_at=now,
                latency_ms=int((time.monotonic() - started) * 1000),
                detail={"message": "Read-only query failed"},
                last_error="timeout",
            )
        except httpx.HTTPStatusError as exc:
            http_status = exc.response.status_code
            error_category: SafeErrorCategory = (
                "authentication_failure"
                if http_status in {401, 403}
                else "connector_failure"
            )
            return IntegrationMeasurement(
                status="down",
                measurement_method="read_only_endpoint_probe",
                checked_at=now,
                latency_ms=int((time.monotonic() - started) * 1000),
                detail={
                    "message": "Read-only query failed",
                    "http_status": http_status,
                },
                last_error=error_category,
            )
        except httpx.HTTPError:
            return IntegrationMeasurement(
                status="down",
                measurement_method="read_only_endpoint_probe",
                checked_at=now,
                latency_ms=int((time.monotonic() - started) * 1000),
                detail={"message": "Read-only query failed"},
                last_error="connector_failure",
            )
        finally:
            if owns_client:
                await client.aclose()


async def measure_supervity(client: Any, now: datetime) -> IntegrationMeasurement:
    """Adapt Supervity's health tuple to the safe measurement contract."""

    config = getattr(client, "config", None)
    if not getattr(config, "configured", False):
        return IntegrationMeasurement(
            status="unknown",
            measurement_method="read_only_endpoint_probe",
            checked_at=now,
            detail={"message": "Health probe is not configured"},
        )

    try:
        status, latency_ms, _ = await client.health()
    except httpx.TimeoutException:
        return IntegrationMeasurement(
            status="down",
            measurement_method="read_only_endpoint_probe",
            checked_at=now,
            detail={"message": "Read-only run listing failed"},
            last_error="timeout",
        )
    except httpx.HTTPStatusError as exc:
        error_category: SafeErrorCategory = (
            "authentication_failure"
            if exc.response.status_code in {401, 403}
            else "connector_failure"
        )
        return IntegrationMeasurement(
            status="down",
            measurement_method="read_only_endpoint_probe",
            checked_at=now,
            detail={"message": "Read-only run listing failed"},
            last_error=error_category,
        )
    except (SupervityError, httpx.HTTPError):
        return IntegrationMeasurement(
            status="down",
            measurement_method="read_only_endpoint_probe",
            checked_at=now,
            detail={"message": "Read-only run listing failed"},
            last_error="connector_failure",
        )

    safe_latency = latency_ms if type(latency_ms) is int else None
    if status == "healthy":
        return IntegrationMeasurement(
            status="healthy",
            measurement_method="read_only_endpoint_probe",
            checked_at=now,
            latency_ms=safe_latency,
            detail={"message": "Read-only run listing succeeded"},
        )

    return IntegrationMeasurement(
        status="down",
        measurement_method="read_only_endpoint_probe",
        checked_at=now,
        latency_ms=safe_latency,
        detail={"message": "Read-only run listing failed"},
        last_error="connector_failure",
    )


class IntegrationHealthService:
    """Measure passive integration evidence and atomically refresh the registry."""

    _SLACK_ERROR_CATEGORIES: frozenset[str] = frozenset(
        {
            "authentication_failure",
            "timeout",
            "rate_limited",
            "connector_failure",
        }
    )

    def __init__(
        self,
        db: Session,
        *,
        supabase: SupabaseHealthClient | None = None,
        supervity: SupervityClient | None = None,
        now: Callable[[], datetime] | None = None,
        max_age_hours: float | None = None,
    ) -> None:
        self._db = db
        self._supabase = supabase or SupabaseHealthClient.from_env()
        self._supervity = supervity or SupervityClient()
        self._now = now or (lambda: datetime.now(timezone.utc))
        self.max_age_hours = self._resolve_max_age_hours(max_age_hours)

    @staticmethod
    def _resolve_max_age_hours(value: float | None) -> float:
        if value is None:
            configured = os.getenv("INTEGRATION_HEALTH_MAX_AGE_HOURS")
            if configured is None or not configured.strip():
                return 24.0
            candidate: object = configured.strip()
        else:
            candidate = value

        try:
            parsed = float(candidate)
        except (TypeError, ValueError):
            parsed = float("nan")
        if isinstance(candidate, bool) or not isfinite(parsed) or parsed <= 0:
            raise ValueError(
                "INTEGRATION_HEALTH_MAX_AGE_HOURS must be a finite positive number"
            )
        return parsed

    @staticmethod
    def _as_utc(value: datetime, *, label: str) -> datetime:
        if not isinstance(value, datetime):
            raise ValueError(f"{label} must be a datetime")
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError(f"{label} must be timezone-aware")
        return value.astimezone(timezone.utc)

    def snapshot(self) -> list[Integration]:
        """Return the registry in deterministic key order without probing."""

        return self._db.query(Integration).order_by(Integration.key).all()

    def _measure_outlook(self, now: datetime) -> IntegrationMeasurement:
        count, latest = (
            self._db.query(func.count(Run.id), func.max(Run.started_at))
            .filter(Run.trigger_source == "outlook")
            .one()
        )
        records_seen = int(count or 0)
        if latest is None:
            return IntegrationMeasurement(
                status="unknown",
                measurement_method="recorded_run_activity",
                checked_at=now,
                records_seen=records_seen,
                detail={"message": "No Outlook-triggered runs recorded"},
            )

        last_activity_at = self._as_utc(latest, label="Outlook activity timestamp")
        status = activity_status(last_activity_at, now, self.max_age_hours)
        message = (
            "Outlook-triggered run activity is recent"
            if status == "healthy"
            else "Outlook-triggered run activity is stale"
        )
        return IntegrationMeasurement(
            status=status,
            measurement_method="recorded_run_activity",
            checked_at=now,
            records_seen=records_seen,
            last_activity_at=last_activity_at,
            detail={"message": message},
        )

    def _measure_slack(self, now: datetime) -> IntegrationMeasurement:
        payload = cast(RunEvent.payload, JSONB)
        slack_filter = (
            RunEvent.event_type == "integration_activity",
            payload["integration_key"].astext == "slack",
        )
        latest = (
            self._db.query(RunEvent)
            .filter(*slack_filter)
            .order_by(RunEvent.ts.desc(), RunEvent.id.desc())
            .first()
        )
        success_count = (
            self._db.query(func.count(RunEvent.id))
            .filter(*slack_filter, payload["outcome"].astext == "success")
            .scalar()
        )
        records_seen = int(success_count or 0)
        if latest is None:
            return IntegrationMeasurement(
                status="unknown",
                measurement_method="recorded_delivery_activity",
                checked_at=now,
                records_seen=records_seen,
                detail={"message": "No Slack delivery attempts recorded"},
            )

        last_activity_at = self._as_utc(latest.ts, label="Slack activity timestamp")
        latest_payload = latest.payload if isinstance(latest.payload, dict) else {}
        if latest_payload.get("outcome") == "success":
            status = activity_status(last_activity_at, now, self.max_age_hours)
            message = (
                "Slack delivery activity is recent"
                if status == "healthy"
                else "Slack delivery activity is stale"
            )
            return IntegrationMeasurement(
                status=status,
                measurement_method="recorded_delivery_activity",
                checked_at=now,
                records_seen=records_seen,
                last_activity_at=last_activity_at,
                detail={"message": message},
            )

        raw_category = latest_payload.get("error_category")
        last_error: SafeErrorCategory = (
            raw_category
            if isinstance(raw_category, str)
            and raw_category in self._SLACK_ERROR_CATEGORIES
            else "connector_failure"
        )
        return IntegrationMeasurement(
            status="down",
            measurement_method="recorded_delivery_activity",
            checked_at=now,
            records_seen=records_seen,
            last_activity_at=last_activity_at,
            detail={"message": "Latest Slack delivery attempt failed"},
            last_error=last_error,
        )

    async def refresh(self) -> tuple[list[Integration], bool]:
        """Measure all integrations, then persist one atomic registry update."""

        try:
            now = self._as_utc(self._now(), label="now")
            supabase_measurement = await self._supabase.measure(now)
            supervity_measurement = await measure_supervity(self._supervity, now)
            measurements = {
                "supabase": supabase_measurement,
                "supervity": supervity_measurement,
                "outlook": self._measure_outlook(now),
                "slack": self._measure_slack(now),
            }
            rows = self.snapshot()
            for row in rows:
                measurement = measurements.get(row.key)
                if measurement is None:
                    continue
                row.status = measurement.status
                row.last_checked_at = measurement.checked_at
                row.latency_ms = measurement.latency_ms
                row.detail = {
                    "measurement_method": measurement.measurement_method,
                    **measurement.detail,
                }
                row.last_error = measurement.last_error
                row.records_seen = measurement.records_seen
                row.last_activity_at = measurement.last_activity_at
            self._db.flush()
            for row in rows:
                self._db.expunge(row)
            self._db.commit()
        except Exception:
            self._db.rollback()
            raise

        partial_failure = any(
            measurement.status == "down" for measurement in measurements.values()
        )
        return rows, partial_failure
