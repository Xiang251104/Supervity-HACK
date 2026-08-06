from copy import deepcopy
from datetime import datetime, timedelta, timezone
from typing import Any, Callable
from uuid import uuid4

import httpx
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import cast, event, inspect as sqlalchemy_inspect
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Session

from app.core.database import SessionLocal, engine
from app.main import app
from app.models.ap import Integration, Run, RunEvent
from app.routers.ap_data_manager import get_integration_health_service
from app.security import get_current_user
from app.services import integration_health
from app.services.integration_health import (
    IntegrationMeasurement,
    activity_status,
    safe_error_category,
)
from app.services.supervity import SupervityError


NOW = datetime(2026, 8, 4, 15, 0, tzinfo=timezone.utc)


def test_activity_status_is_unknown_without_activity() -> None:
    assert activity_status(None, NOW, 24) == "unknown"


def test_activity_status_is_healthy_at_inclusive_freshness_boundary() -> None:
    assert activity_status(NOW - timedelta(hours=24), NOW, 24) == "healthy"


def test_activity_status_is_degraded_beyond_freshness_boundary() -> None:
    assert activity_status(NOW - timedelta(hours=24, seconds=1), NOW, 24) == "degraded"


def test_safe_error_category_never_returns_raw_secret_bearing_text() -> None:
    raw_error = (
        "Authorization: Bearer secret-token; "
        "webhook=https://example.test/hooks/private-value"
    )

    category = safe_error_category(raw_error)

    assert category == "authentication_failure"
    assert category in {"timeout", "authentication_failure", "connector_failure"}
    assert category != raw_error


def test_integration_measurement_accepts_allowlisted_scalar_detail() -> None:
    safe_detail = {
        "connector": "ap_data_manager",
        "configured": True,
        "http_status": 200,
        "sample_ratio": 1.0,
    }

    measurement = IntegrationMeasurement(
        status="healthy",
        measurement_method="activity_freshness",
        checked_at=NOW,
        latency_ms=12,
        records_seen=4,
        last_activity_at=NOW - timedelta(minutes=5),
        detail=safe_detail,
        last_error=None,
    )

    assert measurement.detail == safe_detail
    assert measurement.latency_ms == 12


def test_integration_measurement_rejects_non_integer_latency() -> None:
    with pytest.raises(TypeError, match="latency_ms must be an integer or None"):
        IntegrationMeasurement(
            status="healthy",
            measurement_method="activity_freshness",
            checked_at=NOW,
            latency_ms=12.5,
        )


@pytest.mark.asyncio
async def test_supabase_health_is_unknown_when_not_configured() -> None:
    measurement = await integration_health.SupabaseHealthClient(
        url="", service_key=""
    ).measure(NOW)

    assert measurement == IntegrationMeasurement(
        status="unknown",
        measurement_method="read_only_endpoint_probe",
        checked_at=NOW,
        detail={"message": "Health probe is not configured"},
    )


def test_supabase_health_from_env_strips_configuration(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("SUPABASE_URL", "  https://project.supabase.test/  ")
    monkeypatch.setenv("SUPABASE_SERVICE_KEY", "  private-service-key  ")

    client = integration_health.SupabaseHealthClient.from_env()

    assert client.url == "https://project.supabase.test/"
    assert client.service_key == "private-service-key"


@pytest.mark.asyncio
async def test_supabase_health_uses_read_only_query_and_discards_response_body() -> (
    None
):
    service_key = "private-service-key"
    invoice_value = "sensitive-invoice-value"
    captured_request: httpx.Request | None = None

    def handle_request(request: httpx.Request) -> httpx.Response:
        nonlocal captured_request
        captured_request = request
        return httpx.Response(
            206,
            headers={"Content-Range": "0-0/450"},
            json=[{"belnr": invoice_value}],
        )

    client = httpx.AsyncClient(transport=httpx.MockTransport(handle_request))
    try:
        measurement = await integration_health.SupabaseHealthClient(
            url="https://project.supabase.test/",
            service_key=service_key,
            client=client,
        ).measure(NOW)
        assert not client.is_closed
    finally:
        await client.aclose()

    assert captured_request is not None
    assert captured_request.method == "GET"
    assert captured_request.url.path == "/rest/v1/ap_invoices"
    assert dict(captured_request.url.params) == {"select": "belnr", "limit": "1"}
    assert captured_request.headers["Prefer"] == "count=exact"
    assert captured_request.headers["Range"] == "0-0"
    assert captured_request.headers["apikey"] == service_key
    assert captured_request.headers["Authorization"] == f"Bearer {service_key}"
    assert measurement.status == "healthy"
    assert measurement.records_seen == 450
    assert type(measurement.latency_ms) is int
    assert measurement.last_activity_at == NOW
    assert measurement.detail == {
        "message": "Read-only query succeeded",
        "http_status": 206,
    }
    assert invoice_value not in repr(measurement)
    assert service_key not in repr(measurement)


@pytest.mark.asyncio
@pytest.mark.parametrize("http_status", [201, 204])
async def test_supabase_health_rejects_unsupported_success_status(
    http_status: int,
) -> None:
    def handle_request(request: httpx.Request) -> httpx.Response:
        return httpx.Response(http_status, text="sensitive response body")

    client = httpx.AsyncClient(transport=httpx.MockTransport(handle_request))
    try:
        measurement = await integration_health.SupabaseHealthClient(
            url="https://project.supabase.test",
            service_key="private-service-key",
            client=client,
        ).measure(NOW)
    finally:
        await client.aclose()

    assert measurement.status == "down"
    assert measurement.last_error == "connector_failure"
    assert measurement.detail == {
        "message": "Read-only query failed",
        "http_status": http_status,
    }
    assert "sensitive response body" not in repr(measurement)


@pytest.mark.asyncio
async def test_supabase_health_closes_only_an_owned_client(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    created_clients: list[object] = []

    class OwnedClient:
        def __init__(self, *, timeout: float) -> None:
            self.timeout = timeout
            self.closed = False
            created_clients.append(self)

        async def get(self, url: str, **kwargs: object) -> httpx.Response:
            request = httpx.Request("GET", url)
            return httpx.Response(
                206,
                headers={"Content-Range": "0-0/1"},
                request=request,
            )

        async def aclose(self) -> None:
            self.closed = True

    monkeypatch.setattr(httpx, "AsyncClient", OwnedClient)

    measurement = await integration_health.SupabaseHealthClient(
        url="https://project.supabase.test",
        service_key="private-service-key",
    ).measure(NOW)

    assert measurement.status == "healthy"
    assert len(created_clients) == 1
    assert created_clients[0].timeout == 10.0
    assert created_clients[0].closed is True


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "content_range",
    [
        None,
        "malformed",
        "0-0/*",
        "0-0/-1",
        "0-0/not-an-integer",
        "0-0/450/2",
        "garbage/450",
        "0-0/ +450",
        "1-0/450",
        "0-5/2",
        "2-2/1",
        "0-0/0",
    ],
)
async def test_supabase_health_treats_invalid_content_range_as_zero_records(
    content_range: str | None,
) -> None:
    def handle_request(request: httpx.Request) -> httpx.Response:
        headers = {} if content_range is None else {"Content-Range": content_range}
        return httpx.Response(206, headers=headers)

    client = httpx.AsyncClient(transport=httpx.MockTransport(handle_request))
    try:
        measurement = await integration_health.SupabaseHealthClient(
            url="https://project.supabase.test",
            service_key="private-service-key",
            client=client,
        ).measure(NOW)
    finally:
        await client.aclose()

    assert measurement.status == "healthy"
    assert measurement.records_seen == 0


@pytest.mark.asyncio
async def test_supabase_health_sanitizes_timeout() -> None:
    def handle_request(request: httpx.Request) -> httpx.Response:
        raise httpx.ReadTimeout(
            "private-service-key timed out at /private/path",
            request=request,
        )

    client = httpx.AsyncClient(transport=httpx.MockTransport(handle_request))
    try:
        measurement = await integration_health.SupabaseHealthClient(
            url="https://project.supabase.test",
            service_key="private-service-key",
            client=client,
        ).measure(NOW)
    finally:
        await client.aclose()

    assert measurement.status == "down"
    assert measurement.last_error == "timeout"
    assert measurement.detail == {"message": "Read-only query failed"}
    assert "private" not in repr(measurement)


@pytest.mark.asyncio
async def test_supabase_health_propagates_unexpected_runtime_error() -> None:
    def handle_request(request: httpx.Request) -> httpx.Response:
        raise RuntimeError("unexpected programming fault")

    client = httpx.AsyncClient(transport=httpx.MockTransport(handle_request))
    try:
        with pytest.raises(RuntimeError, match="unexpected programming fault"):
            await integration_health.SupabaseHealthClient(
                url="https://project.supabase.test",
                service_key="private-service-key",
                client=client,
            ).measure(NOW)
    finally:
        await client.aclose()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "misleading_message",
    ["request returned 401 with private-key", "timeout for private endpoint"],
)
async def test_supabase_health_classifies_connect_errors_by_type(
    misleading_message: str,
) -> None:
    def handle_request(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError(misleading_message, request=request)

    client = httpx.AsyncClient(transport=httpx.MockTransport(handle_request))
    try:
        measurement = await integration_health.SupabaseHealthClient(
            url="https://project.supabase.test",
            service_key="private-service-key",
            client=client,
        ).measure(NOW)
    finally:
        await client.aclose()

    assert measurement.status == "down"
    assert measurement.last_error == "connector_failure"
    assert measurement.detail == {"message": "Read-only query failed"}
    assert misleading_message not in repr(measurement)


@pytest.mark.asyncio
@pytest.mark.parametrize("http_status", [401, 403])
async def test_supabase_health_classifies_http_status_errors_by_status(
    http_status: int,
) -> None:
    def handle_request(request: httpx.Request) -> httpx.Response:
        response = httpx.Response(http_status, request=request)
        raise httpx.HTTPStatusError(
            "private connector failure",
            request=request,
            response=response,
        )

    client = httpx.AsyncClient(transport=httpx.MockTransport(handle_request))
    try:
        measurement = await integration_health.SupabaseHealthClient(
            url="https://project.supabase.test",
            service_key="private-service-key",
            client=client,
        ).measure(NOW)
    finally:
        await client.aclose()

    assert measurement.status == "down"
    assert measurement.last_error == "authentication_failure"
    assert measurement.detail == {
        "message": "Read-only query failed",
        "http_status": http_status,
    }
    assert "private connector failure" not in repr(measurement)


@pytest.mark.asyncio
@pytest.mark.parametrize("http_status", [401, 403])
async def test_supabase_health_sanitizes_authentication_failure(
    http_status: int,
) -> None:
    service_key = "private-service-key"

    def handle_request(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            http_status,
            text=(
                f"Authorization: Bearer {service_key}; "
                "url=https://project.supabase.test/private"
            ),
        )

    client = httpx.AsyncClient(transport=httpx.MockTransport(handle_request))
    try:
        measurement = await integration_health.SupabaseHealthClient(
            url="https://project.supabase.test",
            service_key=service_key,
            client=client,
        ).measure(NOW)
    finally:
        await client.aclose()

    assert measurement.status == "down"
    assert measurement.last_error == "authentication_failure"
    assert measurement.detail == {
        "message": "Read-only query failed",
        "http_status": http_status,
    }
    assert service_key not in repr(measurement)
    assert "Authorization" not in repr(measurement)
    assert "supabase.test" not in repr(measurement)


class _FakeSupervityConfig:
    def __init__(self, configured: bool) -> None:
        self.configured = configured


class _FakeSupervityClient:
    def __init__(
        self,
        configured: bool,
        health_result: tuple[str, int | None, dict[str, object]] | None = None,
        health_error: Exception | None = None,
    ) -> None:
        self.config = _FakeSupervityConfig(configured)
        self.health_result = health_result
        self.health_error = health_error
        self.health_calls = 0

    async def health(self) -> tuple[str, int | None, dict[str, object]]:
        self.health_calls += 1
        if self.health_error is not None:
            raise self.health_error
        assert self.health_result is not None
        return self.health_result


@pytest.mark.asyncio
async def test_supervity_health_is_unknown_when_not_configured_without_probe() -> None:
    client = _FakeSupervityClient(configured=False)

    measurement = await integration_health.measure_supervity(client, NOW)

    assert client.health_calls == 0
    assert measurement == IntegrationMeasurement(
        status="unknown",
        measurement_method="read_only_endpoint_probe",
        checked_at=NOW,
        detail={"message": "Health probe is not configured"},
    )


@pytest.mark.asyncio
async def test_supervity_health_discards_healthy_sample() -> None:
    client = _FakeSupervityClient(
        configured=True,
        health_result=("healthy", 42, {"sample": "must not escape"}),
    )

    measurement = await integration_health.measure_supervity(client, NOW)

    assert measurement == IntegrationMeasurement(
        status="healthy",
        measurement_method="read_only_endpoint_probe",
        checked_at=NOW,
        latency_ms=42,
        detail={"message": "Read-only run listing succeeded"},
    )


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "returned_detail",
    [
        {"error": "Authorization: Bearer private-key returned 401"},
        {"error": "timeout at private URL with secret-token"},
    ],
)
async def test_supervity_health_ignores_down_result_detail(
    returned_detail: dict[str, object],
) -> None:
    client = _FakeSupervityClient(
        configured=True,
        health_result=("down", 42, returned_detail),
    )

    measurement = await integration_health.measure_supervity(client, NOW)

    assert measurement == IntegrationMeasurement(
        status="down",
        measurement_method="read_only_endpoint_probe",
        checked_at=NOW,
        latency_ms=42,
        detail={"message": "Read-only run listing failed"},
        last_error="connector_failure",
    )
    assert "private-key" not in repr(measurement)
    assert "secret-token" not in repr(measurement)


@pytest.mark.asyncio
async def test_supervity_health_propagates_unexpected_runtime_error() -> None:
    client = _FakeSupervityClient(
        configured=True,
        health_error=RuntimeError("unexpected programming fault"),
    )

    with pytest.raises(RuntimeError, match="unexpected programming fault"):
        await integration_health.measure_supervity(client, NOW)


@pytest.mark.asyncio
async def test_supervity_health_classifies_typed_timeout() -> None:
    request = httpx.Request("GET", "https://auto.supervity.test/private")
    client = _FakeSupervityClient(
        configured=True,
        health_error=httpx.ReadTimeout("private timeout details", request=request),
    )

    measurement = await integration_health.measure_supervity(client, NOW)

    assert measurement.status == "down"
    assert measurement.detail == {"message": "Read-only run listing failed"}
    assert measurement.last_error == "timeout"
    assert "private" not in repr(measurement)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("http_status", "expected_category"),
    [
        (401, "authentication_failure"),
        (403, "authentication_failure"),
        (500, "connector_failure"),
    ],
)
async def test_supervity_health_classifies_http_status_error_by_status(
    http_status: int,
    expected_category: str,
) -> None:
    request = httpx.Request("GET", "https://auto.supervity.test/private")
    response = httpx.Response(http_status, request=request)
    client = _FakeSupervityClient(
        configured=True,
        health_error=httpx.HTTPStatusError(
            "private connector details",
            request=request,
            response=response,
        ),
    )

    measurement = await integration_health.measure_supervity(client, NOW)

    assert measurement.status == "down"
    assert measurement.detail == {"message": "Read-only run listing failed"}
    assert measurement.last_error == expected_category
    assert "private" not in repr(measurement)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "health_error",
    [
        SupervityError("timeout and 401 in private connector details"),
        httpx.ConnectError(
            "timeout and 401 in private connector details",
            request=httpx.Request("GET", "https://auto.supervity.test/private"),
        ),
    ],
)
async def test_supervity_health_classifies_expected_connector_errors(
    health_error: Exception,
) -> None:
    client = _FakeSupervityClient(configured=True, health_error=health_error)

    measurement = await integration_health.measure_supervity(client, NOW)

    assert measurement.status == "down"
    assert measurement.detail == {"message": "Read-only run listing failed"}
    assert measurement.last_error == "connector_failure"
    assert "private" not in repr(measurement)


_INTEGRATION_KEYS = ("outlook", "slack", "supabase", "supervity")
_HEALTH_FIELDS = (
    "status",
    "last_checked_at",
    "latency_ms",
    "detail",
    "last_error",
    "records_seen",
    "last_activity_at",
)


def _database_digest(db: Session) -> dict[str, tuple[object, ...]]:
    return {
        "integrations": tuple(
            (
                row.id,
                row.key,
                *(deepcopy(getattr(row, field)) for field in _HEALTH_FIELDS),
            )
            for row in db.query(Integration).order_by(Integration.id)
        ),
        "runs": tuple(
            (row.id, row.run_id, row.trigger_source, row.started_at)
            for row in db.query(Run).order_by(Run.id)
        ),
        "events": tuple(
            (
                row.id,
                row.run_id,
                row.event_type,
                deepcopy(row.payload),
                row.ts,
            )
            for row in db.query(RunEvent).order_by(RunEvent.id)
        ),
    }


@pytest.fixture
def integration_registry_db() -> Session:
    """Keep every test write inside an outer transaction that is never committed."""

    with SessionLocal() as external_db:
        before = _database_digest(external_db)
    connection = engine.connect()
    outer_transaction = connection.begin()
    db = Session(
        bind=connection,
        join_transaction_mode="create_savepoint",
    )
    mask = f"masked-{uuid4()}"
    existing_outlook = db.query(Run).filter(Run.trigger_source == "outlook").all()
    existing_slack = (
        db.query(RunEvent)
        .filter(
            RunEvent.event_type == "integration_activity",
            cast(RunEvent.payload, JSONB)["integration_key"].astext == "slack",
        )
        .all()
    )
    try:
        for row in existing_outlook:
            row.trigger_source = mask
        for row in existing_slack:
            row.event_type = mask
        db.flush()
        yield db
    finally:
        db.close()
        outer_transaction.rollback()
        connection.close()
        with SessionLocal() as external_db:
            after = _database_digest(external_db)
        assert after == before


@pytest.fixture
def recorded_activity(
    integration_registry_db: Session,
) -> Callable[..., str]:
    """Insert UUID-scoped activity rows inside the fixture's outer transaction."""

    db = integration_registry_db

    def insert(
        *,
        trigger_source: str = "api",
        started_at: datetime = NOW,
        slack_events: list[dict[str, Any]] | None = None,
    ) -> str:
        run_id = f"integration-health-{uuid4()}"
        db.add(
            Run(
                id=-(uuid4().int % 2_000_000_000 + 1),
                run_id=run_id,
                status="completed",
                trigger_source=trigger_source,
                started_at=started_at,
            )
        )
        db.flush()
        for seq, activity_event in enumerate(slack_events or [], start=1):
            payload = {
                "integration_key": "slack",
                "outcome": activity_event["outcome"],
            }
            if "error_category" in activity_event:
                payload["error_category"] = activity_event["error_category"]
            db.add(
                RunEvent(
                    id=-(uuid4().int % 2_000_000_000 + 1),
                    run_id=run_id,
                    seq=seq,
                    event_type="integration_activity",
                    payload=payload,
                    ts=activity_event["ts"],
                )
            )
        db.flush()
        return run_id

    yield insert


class _StaticSupabaseClient:
    def __init__(
        self,
        measurement: IntegrationMeasurement | None = None,
        error: Exception | None = None,
    ) -> None:
        self.measurement = measurement
        self.error = error
        self.calls = 0

    async def measure(self, now: datetime) -> IntegrationMeasurement:
        self.calls += 1
        if self.error is not None:
            raise self.error
        return self.measurement or IntegrationMeasurement(
            status="unknown",
            measurement_method="read_only_endpoint_probe",
            checked_at=now,
            detail={"message": "Health probe is not configured"},
        )


def _service(
    db: Session,
    *,
    supabase: _StaticSupabaseClient | None = None,
    supervity: _FakeSupervityClient | None = None,
    now: Callable[[], datetime] = lambda: NOW,
    max_age_hours: float | None = 24,
) -> Any:
    return integration_health.IntegrationHealthService(
        db,
        supabase=supabase or _StaticSupabaseClient(),
        supervity=supervity or _FakeSupervityClient(configured=False),
        now=now,
        max_age_hours=max_age_hours,
    )


def _integration(db: Session, key: str) -> Integration:
    return db.query(Integration).filter(Integration.key == key).one()


@pytest.mark.asyncio
async def test_external_probes_finish_before_passive_database_measurements(
    integration_registry_db: Session,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    call_order: list[str] = []

    class OrderedSupabaseClient(_StaticSupabaseClient):
        async def measure(self, now: datetime) -> IntegrationMeasurement:
            call_order.append("supabase")
            return await super().measure(now)

    class OrderedSupervityClient(_FakeSupervityClient):
        async def health(self) -> tuple[str, int | None, dict[str, object]]:
            call_order.append("supervity")
            return await super().health()

    service = _service(
        integration_registry_db,
        supabase=OrderedSupabaseClient(),
        supervity=OrderedSupervityClient(
            configured=True,
            health_result=("healthy", 4, {}),
        ),
    )

    def passive_measurement(source: str) -> IntegrationMeasurement:
        assert call_order[:2] == ["supabase", "supervity"]
        call_order.append(source)
        return IntegrationMeasurement(
            status="unknown",
            measurement_method=f"recorded_{source}_activity",
            checked_at=NOW,
        )

    monkeypatch.setattr(
        service,
        "_measure_outlook",
        lambda now: passive_measurement("outlook"),
    )
    monkeypatch.setattr(
        service,
        "_measure_slack",
        lambda now: passive_measurement("slack"),
    )

    await service.refresh()

    assert call_order == ["supabase", "supervity", "outlook", "slack"]


def test_temporary_activity_is_invisible_to_external_sessions(
    integration_registry_db: Session,
    recorded_activity: Callable[..., str],
) -> None:
    run_id = recorded_activity(trigger_source="outlook")

    assert integration_registry_db.query(Run).filter(Run.run_id == run_id).one()
    with SessionLocal() as external_db:
        assert external_db.query(Run).filter(Run.run_id == run_id).one_or_none() is None


@pytest.mark.asyncio
async def test_refresh_returns_one_detached_ordered_registry_snapshot(
    integration_registry_db: Session,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    statements: list[str] = []
    bind = integration_registry_db.get_bind()
    original_commit = integration_registry_db.commit
    commit_calls = 0
    commit_returned = False
    statements_after_commit: list[str] = []

    def capture_statement(
        connection: object,
        cursor: object,
        statement: str,
        parameters: object,
        context: object,
        executemany: bool,
    ) -> None:
        statements.append(statement)
        if commit_returned:
            statements_after_commit.append(statement)

    def tracked_commit() -> None:
        nonlocal commit_calls, commit_returned
        commit_calls += 1
        original_commit()
        commit_returned = True

    event.listen(bind, "before_cursor_execute", capture_statement)
    monkeypatch.setattr(integration_registry_db, "commit", tracked_commit)
    try:
        rows, _ = await _service(integration_registry_db).refresh()
        registry_selects = [
            statement
            for statement in statements
            if "from ap_integrations" in statement.lower()
        ]
        assert len(registry_selects) == 1
        assert "order by ap_integrations.key" in registry_selects[0].lower()
        assert commit_calls == 1
        assert statements_after_commit == []

        statements.clear()
        assert [row.key for row in rows] == sorted(_INTEGRATION_KEYS)
        assert all(sqlalchemy_inspect(row).detached for row in rows)
        assert all(
            (
                row.id,
                row.key,
                row.name,
                row.category,
                row.purpose,
                row.status,
                row.last_checked_at,
                row.latency_ms,
                row.detail,
                row.last_error,
                row.records_seen,
                row.last_activity_at,
            )
            for row in rows
        )
        assert statements == []
    finally:
        event.remove(bind, "before_cursor_execute", capture_statement)


@pytest.mark.asyncio
async def test_outlook_zero_rows_is_unknown(
    integration_registry_db: Session,
) -> None:
    rows, partial_failure = await _service(integration_registry_db).refresh()

    outlook = next(row for row in rows if row.key == "outlook")
    assert outlook.status == "unknown"
    assert outlook.records_seen == 0
    assert outlook.last_activity_at is None
    assert outlook.detail == {
        "measurement_method": "recorded_run_activity",
        "message": "No Outlook-triggered runs recorded",
    }
    assert partial_failure is False


@pytest.mark.asyncio
async def test_recent_outlook_rows_are_healthy_with_count_and_latest_time(
    integration_registry_db: Session,
    recorded_activity: Callable[..., str],
) -> None:
    recorded_activity(trigger_source="outlook", started_at=NOW - timedelta(hours=2))
    recorded_activity(trigger_source="outlook", started_at=NOW - timedelta(minutes=10))

    await _service(integration_registry_db).refresh()

    outlook = _integration(integration_registry_db, "outlook")
    assert outlook.status == "healthy"
    assert outlook.records_seen == 2
    assert outlook.last_activity_at == NOW - timedelta(minutes=10)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("age", "expected_status"),
    [
        (timedelta(hours=24), "healthy"),
        (timedelta(hours=24, seconds=1), "degraded"),
    ],
)
async def test_outlook_freshness_uses_inclusive_boundary(
    integration_registry_db: Session,
    recorded_activity: Callable[..., str],
    age: timedelta,
    expected_status: str,
) -> None:
    recorded_activity(trigger_source="outlook", started_at=NOW - age)

    await _service(integration_registry_db).refresh()

    assert _integration(integration_registry_db, "outlook").status == expected_status


@pytest.mark.asyncio
async def test_slack_zero_events_is_unknown(
    integration_registry_db: Session,
) -> None:
    await _service(integration_registry_db).refresh()

    slack = _integration(integration_registry_db, "slack")
    assert slack.status == "unknown"
    assert slack.records_seen == 0
    assert slack.last_activity_at is None
    assert slack.detail == {
        "measurement_method": "recorded_delivery_activity",
        "message": "No Slack delivery attempts recorded",
    }


@pytest.mark.asyncio
async def test_recent_slack_success_is_healthy(
    integration_registry_db: Session,
    recorded_activity: Callable[..., str],
) -> None:
    latest = NOW - timedelta(minutes=5)
    recorded_activity(slack_events=[{"outcome": "success", "ts": latest}])

    await _service(integration_registry_db).refresh()

    slack = _integration(integration_registry_db, "slack")
    assert slack.status == "healthy"
    assert slack.records_seen == 1
    assert slack.last_activity_at == latest
    assert slack.last_error is None


@pytest.mark.asyncio
async def test_stale_slack_success_is_degraded(
    integration_registry_db: Session,
    recorded_activity: Callable[..., str],
) -> None:
    recorded_activity(
        slack_events=[
            {"outcome": "success", "ts": NOW - timedelta(hours=24, seconds=1)}
        ]
    )

    await _service(integration_registry_db).refresh()

    assert _integration(integration_registry_db, "slack").status == "degraded"


@pytest.mark.asyncio
async def test_newest_slack_failure_overrides_success_and_counts_successes_only(
    integration_registry_db: Session,
    recorded_activity: Callable[..., str],
) -> None:
    latest = NOW - timedelta(minutes=1)
    recorded_activity(
        slack_events=[
            {"outcome": "success", "ts": NOW - timedelta(minutes=2)},
            {
                "outcome": "failure",
                "error_category": "timeout",
                "ts": latest,
            },
        ]
    )

    _, partial_failure = await _service(integration_registry_db).refresh()

    slack = _integration(integration_registry_db, "slack")
    assert slack.status == "down"
    assert slack.records_seen == 1
    assert slack.last_activity_at == latest
    assert slack.last_error == "timeout"
    assert partial_failure is True


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("raw_category", "expected_category"),
    [
        ("authentication_failure", "authentication_failure"),
        ("timeout", "timeout"),
        ("rate_limited", "rate_limited"),
        ("connector_failure", "connector_failure"),
        ("Bearer private-token at https://hooks.test/private", "connector_failure"),
    ],
)
async def test_slack_failure_persists_only_allowlisted_error_categories(
    integration_registry_db: Session,
    recorded_activity: Callable[..., str],
    raw_category: str,
    expected_category: str,
) -> None:
    recorded_activity(
        slack_events=[
            {
                "outcome": "failure",
                "error_category": raw_category,
                "ts": NOW,
            }
        ]
    )

    await _service(integration_registry_db).refresh()

    slack = _integration(integration_registry_db, "slack")
    assert slack.last_error == expected_category
    assert raw_category not in repr(slack.detail)


def test_health_max_age_defaults_to_24_when_env_is_absent(
    integration_registry_db: Session,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("INTEGRATION_HEALTH_MAX_AGE_HOURS", raising=False)

    service = _service(integration_registry_db, max_age_hours=None)

    assert service.max_age_hours == 24.0


def test_health_max_age_accepts_positive_numeric_env_value(
    integration_registry_db: Session,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("INTEGRATION_HEALTH_MAX_AGE_HOURS", "12.5")

    service = _service(integration_registry_db, max_age_hours=None)

    assert service.max_age_hours == 12.5


@pytest.mark.parametrize("value", ["0", "-1", "NaN", "Infinity", "not-a-number"])
def test_health_max_age_rejects_invalid_env_values(
    integration_registry_db: Session,
    monkeypatch: pytest.MonkeyPatch,
    value: str,
) -> None:
    monkeypatch.setenv("INTEGRATION_HEALTH_MAX_AGE_HOURS", value)

    with pytest.raises(
        ValueError,
        match="INTEGRATION_HEALTH_MAX_AGE_HOURS must be a finite positive number",
    ):
        _service(integration_registry_db, max_age_hours=None)


@pytest.mark.asyncio
async def test_refresh_normalizes_aware_now_to_utc(
    integration_registry_db: Session,
) -> None:
    local_now = NOW.astimezone(timezone(timedelta(hours=8)))

    await _service(integration_registry_db, now=lambda: local_now).refresh()

    assert _integration(integration_registry_db, "outlook").last_checked_at == NOW


@pytest.mark.asyncio
async def test_refresh_rejects_naive_now(
    integration_registry_db: Session,
) -> None:
    with pytest.raises(ValueError, match="now must be timezone-aware"):
        await _service(
            integration_registry_db,
            now=lambda: NOW.replace(tzinfo=None),
        ).refresh()


@pytest.mark.asyncio
async def test_refresh_persists_every_field_and_clears_stale_optional_values(
    integration_registry_db: Session,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    supabase_row = _integration(integration_registry_db, "supabase")
    supabase_row.status = "down"
    supabase_row.last_checked_at = NOW - timedelta(days=2)
    supabase_row.latency_ms = 999
    supabase_row.detail = {"message": "stale"}
    supabase_row.last_error = "timeout"
    supabase_row.records_seen = 99
    supabase_row.last_activity_at = NOW - timedelta(days=2)
    integration_registry_db.commit()
    measurement = IntegrationMeasurement(
        status="healthy",
        measurement_method="read_only_endpoint_probe",
        checked_at=NOW,
        latency_ms=None,
        records_seen=7,
        last_activity_at=None,
        detail={"message": "Read-only query succeeded", "http_status": 200},
        last_error=None,
    )
    original_commit = integration_registry_db.commit
    commit_calls = 0

    def counted_commit() -> None:
        nonlocal commit_calls
        commit_calls += 1
        original_commit()

    monkeypatch.setattr(integration_registry_db, "commit", counted_commit)

    await _service(
        integration_registry_db,
        supabase=_StaticSupabaseClient(measurement),
    ).refresh()

    refreshed = _integration(integration_registry_db, "supabase")
    assert refreshed.status == "healthy"
    assert refreshed.last_checked_at == NOW
    assert refreshed.latency_ms is None
    assert refreshed.detail == {
        "measurement_method": "read_only_endpoint_probe",
        "message": "Read-only query succeeded",
        "http_status": 200,
    }
    assert refreshed.last_error is None
    assert refreshed.records_seen == 7
    assert refreshed.last_activity_at is None
    assert commit_calls == 1


@pytest.mark.asyncio
async def test_unknown_measurements_do_not_count_as_partial_failure(
    integration_registry_db: Session,
) -> None:
    rows, partial_failure = await _service(integration_registry_db).refresh()

    assert all(row.status == "unknown" for row in rows)
    assert partial_failure is False


@pytest.mark.asyncio
async def test_expected_connector_down_persists_with_successful_results(
    integration_registry_db: Session,
) -> None:
    supabase_measurement = IntegrationMeasurement(
        status="healthy",
        measurement_method="read_only_endpoint_probe",
        checked_at=NOW,
        latency_ms=8,
        records_seen=10,
        last_activity_at=NOW,
        detail={"message": "Read-only query succeeded", "http_status": 200},
    )
    supervity = _FakeSupervityClient(
        configured=True,
        health_result=("down", 19, {"secret": "must not persist"}),
    )

    rows, partial_failure = await _service(
        integration_registry_db,
        supabase=_StaticSupabaseClient(supabase_measurement),
        supervity=supervity,
    ).refresh()

    statuses = {row.key: row.status for row in rows}
    assert statuses["supabase"] == "healthy"
    assert statuses["supervity"] == "down"
    assert _integration(integration_registry_db, "supervity").last_error == (
        "connector_failure"
    )
    assert partial_failure is True


@pytest.mark.asyncio
async def test_unexpected_measurement_exception_rolls_back_and_propagates(
    integration_registry_db: Session,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    before = {
        row.key: {field: getattr(row, field) for field in _HEALTH_FIELDS}
        for row in integration_registry_db.query(Integration).all()
    }
    original_rollback = integration_registry_db.rollback
    rollback_calls = 0

    def counted_rollback() -> None:
        nonlocal rollback_calls
        rollback_calls += 1
        original_rollback()

    monkeypatch.setattr(integration_registry_db, "rollback", counted_rollback)
    supervity = _FakeSupervityClient(
        configured=True,
        health_error=RuntimeError("unexpected measurement fault"),
    )

    with pytest.raises(RuntimeError, match="unexpected measurement fault"):
        await _service(integration_registry_db, supervity=supervity).refresh()

    integration_registry_db.expire_all()
    after = {
        row.key: {field: getattr(row, field) for field in _HEALTH_FIELDS}
        for row in integration_registry_db.query(Integration).all()
    }
    assert rollback_calls == 1
    assert after == before


@pytest.mark.asyncio
async def test_flush_failure_rolls_back_before_commit_and_leaves_registry_unchanged(
    integration_registry_db: Session,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    with SessionLocal() as verification_db:
        before = _database_digest(verification_db)
    original_commit = integration_registry_db.commit
    original_rollback = integration_registry_db.rollback
    commit_calls = 0
    rollback_calls = 0

    def fail_flush() -> None:
        raise RuntimeError("simulated flush failure")

    def counted_commit() -> None:
        nonlocal commit_calls
        commit_calls += 1
        original_commit()

    def counted_rollback() -> None:
        nonlocal rollback_calls
        rollback_calls += 1
        original_rollback()

    monkeypatch.setattr(integration_registry_db, "autoflush", False)
    monkeypatch.setattr(integration_registry_db, "flush", fail_flush)
    monkeypatch.setattr(integration_registry_db, "commit", counted_commit)
    monkeypatch.setattr(integration_registry_db, "rollback", counted_rollback)

    with pytest.raises(RuntimeError, match="simulated flush failure"):
        await _service(integration_registry_db).refresh()

    with SessionLocal() as verification_db:
        after = _database_digest(verification_db)
    assert commit_calls == 0
    assert rollback_calls == 1
    assert after == before


@pytest.mark.asyncio
async def test_commit_failure_rolls_back_and_leaves_registry_unchanged(
    integration_registry_db: Session,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    with SessionLocal() as verification_db:
        before = {
            row.key: {field: getattr(row, field) for field in _HEALTH_FIELDS}
            for row in verification_db.query(Integration).all()
        }
    rollback_calls = 0
    original_rollback = integration_registry_db.rollback

    def fail_commit() -> None:
        raise RuntimeError("simulated commit failure")

    def counted_rollback() -> None:
        nonlocal rollback_calls
        rollback_calls += 1
        original_rollback()

    monkeypatch.setattr(integration_registry_db, "commit", fail_commit)
    monkeypatch.setattr(integration_registry_db, "rollback", counted_rollback)

    with pytest.raises(RuntimeError, match="simulated commit failure"):
        await _service(integration_registry_db).refresh()

    with SessionLocal() as verification_db:
        after = {
            row.key: {field: getattr(row, field) for field in _HEALTH_FIELDS}
            for row in verification_db.query(Integration).all()
        }
    assert rollback_calls == 1
    assert after == before


def test_snapshot_returns_registry_in_key_order_without_probing(
    integration_registry_db: Session,
) -> None:
    supabase = _StaticSupabaseClient(
        error=AssertionError("snapshot must not probe connectors")
    )

    rows = _service(integration_registry_db, supabase=supabase).snapshot()

    assert [row.key for row in rows] == sorted(_INTEGRATION_KEYS)
    assert supabase.calls == 0


_PUBLIC_INTEGRATION_FIELDS = {
    "key",
    "name",
    "category",
    "purpose",
    "status",
    "measurement_method",
    "last_checked_at",
    "latency_ms",
    "records_seen",
    "last_activity_at",
    "detail",
    "last_error",
}


class _FakeApiHealthService:
    def __init__(
        self,
        rows: list[Integration],
        *,
        partial_failure: bool = False,
        max_age_hours: float = 24.0,
        snapshot_error: Exception | None = None,
        refresh_error: Exception | None = None,
    ) -> None:
        self.rows = rows
        self.partial_failure = partial_failure
        self.max_age_hours = max_age_hours
        self.snapshot_error = snapshot_error
        self.refresh_error = refresh_error
        self.snapshot_calls = 0
        self.refresh_calls = 0

    def snapshot(self) -> list[Integration]:
        self.snapshot_calls += 1
        if self.snapshot_error is not None:
            raise self.snapshot_error
        return self.rows

    async def refresh(self) -> tuple[list[Integration], bool]:
        self.refresh_calls += 1
        if self.refresh_error is not None:
            raise self.refresh_error
        return self.rows, self.partial_failure


def _api_integration(
    *,
    key: str = "supabase",
    status: str = "healthy",
    detail: object = None,
    last_error: str | None = None,
) -> Integration:
    return Integration(
        id=987,
        key=key,
        name=f"{key.title()} integration",
        category="system_of_record",
        purpose=f"Safely connect {key}",
        status=status,
        last_checked_at=NOW,
        latency_ms=17,
        records_seen=42,
        last_activity_at=NOW - timedelta(minutes=3),
        detail=detail,
        last_error=last_error,
    )


@pytest.fixture
def data_manager_api() -> tuple[TestClient, list[dict[str, object]]]:
    previous_overrides = dict(app.dependency_overrides)
    authenticated_users: list[dict[str, object]] = []

    def authenticated_user() -> dict[str, object]:
        user = {
            "sub": "data-manager-reviewer",
            "active": True,
            "realm_access": {"roles": ["user"]},
        }
        authenticated_users.append(user)
        return user

    app.dependency_overrides[get_current_user] = authenticated_user
    client = TestClient(app)
    try:
        yield client, authenticated_users
    finally:
        client.close()
        app.dependency_overrides.clear()
        app.dependency_overrides.update(previous_overrides)


def test_get_data_manager_returns_persisted_snapshot_without_probing_or_refreshing(
    data_manager_api: tuple[TestClient, list[dict[str, object]]],
    integration_registry_db: Session,
) -> None:
    client, _ = data_manager_api
    supabase = _StaticSupabaseClient(
        error=AssertionError("GET must not probe Supabase")
    )
    supervity = _FakeSupervityClient(
        configured=True,
        health_error=AssertionError("GET must not probe Supervity"),
    )
    service = _service(
        integration_registry_db,
        supabase=supabase,
        supervity=supervity,
        max_age_hours=12.5,
    )
    persisted = _integration(integration_registry_db, "supabase")
    persisted.status = "healthy"
    persisted.detail = {
        "measurement_method": "read_only_endpoint_probe",
        "message": "Read-only query succeeded",
    }
    integration_registry_db.flush()
    app.dependency_overrides[get_integration_health_service] = lambda: service

    response = client.get("/api/ap/data-manager")

    assert response.status_code == 200
    body = response.json()
    supabase_response = next(
        row for row in body["integrations"] if row["key"] == "supabase"
    )
    assert supabase_response["status"] == "healthy"
    assert supabase_response["detail"] == {"message": "Read-only query succeeded"}
    assert body["freshness_hours"] == 12.5
    assert supabase.calls == 0


def test_get_data_manager_calls_snapshot_only(
    data_manager_api: tuple[TestClient, list[dict[str, object]]],
) -> None:
    client, _ = data_manager_api
    service = _FakeApiHealthService([_api_integration()])
    app.dependency_overrides[get_integration_health_service] = lambda: service

    response = client.get("/api/ap/data-manager")

    assert response.status_code == 200
    assert service.snapshot_calls == 1
    assert service.refresh_calls == 0


def test_post_data_manager_refresh_awaits_service_once_and_uses_returned_flag(
    data_manager_api: tuple[TestClient, list[dict[str, object]]],
) -> None:
    client, _ = data_manager_api
    rows = [_api_integration(key="slack", status="unknown")]
    service = _FakeApiHealthService(
        rows,
        partial_failure=True,
        max_age_hours=6,
    )
    app.dependency_overrides[get_integration_health_service] = lambda: service

    response = client.post("/api/ap/data-manager/refresh")

    assert response.status_code == 200
    assert response.json()["partial_failure"] is True
    assert response.json()["freshness_hours"] == 6.0
    assert service.refresh_calls == 1
    assert service.snapshot_calls == 0


def test_approved_user_is_authorized_for_both_data_manager_endpoints(
    data_manager_api: tuple[TestClient, list[dict[str, object]]],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr("app.security.AUTH_BYPASS", False)
    client, authenticated_users = data_manager_api
    service = _FakeApiHealthService([])
    app.dependency_overrides[get_integration_health_service] = lambda: service

    assert client.get("/api/ap/data-manager").status_code == 200
    assert client.post("/api/ap/data-manager/refresh").status_code == 200

    assert authenticated_users == [
        {
            "sub": "data-manager-reviewer",
            "active": True,
            "realm_access": {"roles": ["user"]},
        },
        {
            "sub": "data-manager-reviewer",
            "active": True,
            "realm_access": {"roles": ["user"]},
        },
    ]


def test_data_manager_response_has_complete_public_contract_and_all_count_keys(
    data_manager_api: tuple[TestClient, list[dict[str, object]]],
) -> None:
    client, _ = data_manager_api
    row = _api_integration(
        status="degraded",
        detail={
            "measurement_method": "recorded_run_activity",
            "message": "Outlook-triggered run activity is stale",
            "http_status": 206,
        },
    )
    service = _FakeApiHealthService([row])
    app.dependency_overrides[get_integration_health_service] = lambda: service

    body = client.get("/api/ap/data-manager").json()

    assert body.keys() == {
        "integrations",
        "counts",
        "freshness_hours",
        "partial_failure",
    }
    assert body["counts"] == {
        "healthy": 0,
        "degraded": 1,
        "down": 0,
        "unknown": 0,
    }
    assert set(body["integrations"][0]) == _PUBLIC_INTEGRATION_FIELDS
    assert "id" not in body["integrations"][0]


@pytest.mark.parametrize(
    ("statuses", "expected_partial_failure"),
    [
        (["unknown"], False),
        (["healthy", "degraded", "unknown"], False),
        (["unknown", "down"], True),
    ],
)
def test_get_partial_failure_is_derived_only_from_persisted_down_rows(
    data_manager_api: tuple[TestClient, list[dict[str, object]]],
    statuses: list[str],
    expected_partial_failure: bool,
) -> None:
    client, _ = data_manager_api
    rows = [
        _api_integration(key=f"integration-{index}", status=status)
        for index, status in enumerate(statuses)
    ]
    service = _FakeApiHealthService(rows, partial_failure=not expected_partial_failure)
    app.dependency_overrides[get_integration_health_service] = lambda: service

    body = client.get("/api/ap/data-manager").json()

    assert body["partial_failure"] is expected_partial_failure


@pytest.mark.parametrize(
    ("measurement_method", "expected_method"),
    [
        ("read_only_endpoint_probe", "read_only_endpoint_probe"),
        ("recorded_run_activity", "recorded_run_activity"),
        ("recorded_delivery_activity", "recorded_delivery_activity"),
        ("secret_bearing_custom_probe", None),
        (None, None),
    ],
)
def test_data_manager_response_allowlists_detail_and_measurement_method(
    data_manager_api: tuple[TestClient, list[dict[str, object]]],
    measurement_method: str | None,
    expected_method: str | None,
) -> None:
    client, _ = data_manager_api
    row = _api_integration(
        detail={
            "measurement_method": measurement_method,
            "message": "Read-only query succeeded",
            "http_status": 200,
            "token": "private-token",
            "Authorization": "Bearer private-token",
            "webhook_url": "https://hooks.test/private",
            "response_body": "sensitive response",
        }
    )
    service = _FakeApiHealthService([row])
    app.dependency_overrides[get_integration_health_service] = lambda: service

    public_row = client.get("/api/ap/data-manager").json()["integrations"][0]

    assert public_row["measurement_method"] == expected_method
    assert public_row["detail"] == {
        "message": "Read-only query succeeded",
        "http_status": 200,
    }
    assert "private-token" not in repr(public_row)
    assert "hooks.test" not in repr(public_row)
    assert "sensitive response" not in repr(public_row)


def test_data_manager_response_drops_arbitrary_stored_message_but_keeps_http_status(
    data_manager_api: tuple[TestClient, list[dict[str, object]]],
) -> None:
    client, _ = data_manager_api
    fake_credential = "Authorization: Bearer FAKE-DATA-MANAGER-SENTINEL"
    row = _api_integration(
        detail={
            "measurement_method": "read_only_endpoint_probe",
            "message": fake_credential,
            "http_status": 401,
        }
    )
    service = _FakeApiHealthService([row])
    app.dependency_overrides[get_integration_health_service] = lambda: service

    response = client.get("/api/ap/data-manager")

    assert response.status_code == 200
    assert response.json()["integrations"][0]["detail"] == {"http_status": 401}
    assert fake_credential not in response.text


@pytest.mark.parametrize(
    ("status", "stored_error", "expected_error"),
    [
        ("down", "authentication_failure", "authentication_failure"),
        ("down", "timeout", "timeout"),
        ("down", "rate_limited", "rate_limited"),
        ("down", "connector_failure", "connector_failure"),
        ("down", "Bearer private-token", "connector_failure"),
        ("healthy", "Bearer private-token", None),
        ("unknown", "private connector trace", None),
    ],
)
def test_data_manager_response_never_returns_arbitrary_last_error(
    data_manager_api: tuple[TestClient, list[dict[str, object]]],
    status: str,
    stored_error: str,
    expected_error: str | None,
) -> None:
    client, _ = data_manager_api
    service = _FakeApiHealthService(
        [_api_integration(status=status, last_error=stored_error)]
    )
    app.dependency_overrides[get_integration_health_service] = lambda: service

    public_row = client.get("/api/ap/data-manager").json()["integrations"][0]

    assert public_row["last_error"] == expected_error
    assert "private-token" not in repr(public_row)
    assert "private connector trace" not in repr(public_row)


def test_empty_data_manager_registry_returns_zeroed_response(
    data_manager_api: tuple[TestClient, list[dict[str, object]]],
) -> None:
    client, _ = data_manager_api
    service = _FakeApiHealthService([])
    app.dependency_overrides[get_integration_health_service] = lambda: service

    body = client.get("/api/ap/data-manager").json()

    assert body == {
        "integrations": [],
        "counts": {
            "healthy": 0,
            "degraded": 0,
            "down": 0,
            "unknown": 0,
        },
        "freshness_hours": 24.0,
        "partial_failure": False,
    }


@pytest.mark.parametrize(
    ("method", "path", "error_attribute"),
    [
        ("get", "/api/ap/data-manager", "snapshot_error"),
        ("post", "/api/ap/data-manager/refresh", "refresh_error"),
    ],
)
def test_data_manager_service_exceptions_are_not_replaced_with_fake_health(
    data_manager_api: tuple[TestClient, list[dict[str, object]]],
    method: str,
    path: str,
    error_attribute: str,
) -> None:
    client, _ = data_manager_api
    service = _FakeApiHealthService([])
    setattr(service, error_attribute, RuntimeError("database unavailable"))
    app.dependency_overrides[get_integration_health_service] = lambda: service

    with pytest.raises(RuntimeError, match="database unavailable"):
        getattr(client, method)(path)
