# AP Data Manager Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Deliver a live `/data-manager` page and authenticated API that safely measures, explains, and persists Outlook, Supabase, Slack, and Supervity integration health.

**Architecture:** A dedicated `IntegrationHealthService` owns all measurement, freshness, redaction, and transaction behavior. Supabase and Supervity use read-only probes; Outlook and Slack use passive database evidence. Thin FastAPI routes expose persisted snapshots and explicit refresh, while a typed Next.js page renders authoritative API state.

**Tech Stack:** FastAPI, SQLAlchemy, PostgreSQL JSON queries, Pydantic v2, httpx, pytest, Next.js 15, React 19, TypeScript, Tailwind CSS, Vitest, and Testing Library.

---

## Worktree and commit safety

Execute only in:

```text
C:\Users\User\Documents\AP-Control-Tower-Round2\.worktrees\ap-workbench
```

The branch already contains intentional uncommitted Workbench work, including changes to
`app/main.py`, `app/routers/__init__.py`, the three mandatory project documents, frontend package
files, and navigation-adjacent code. Do not reset, discard, overwrite, stage, or commit those
existing changes. Use `git status`, scoped diffs, and `git diff --check` at every checkpoint. Do not
merge, push, or create a pull request without Lim's explicit approval.

Because the dirty Workbench slice overlaps integration files, the task checkpoints below replace
automatic intermediate commits. A final implementation commit is optional and requires Lim's
approval plus a staged-diff review that proves no unrelated Workbench content is included.

## File map

### Create

- `app/services/integration_health.py` — measurement value object, freshness rules, safe probes,
  passive evidence queries, sanitization, and one-transaction persistence.
- `app/schemas/ap_data_manager.py` — public integration, counts, list, and refresh contracts.
- `app/routers/ap_data_manager.py` — authenticated list and refresh adapters.
- `tests/test_ap_data_manager.py` — service and API integration tests against PostgreSQL.
- `frontend/src/types/ap-data-manager.ts` — frontend API types.
- `frontend/src/lib/ap-data-manager.ts` — typed list and refresh calls plus pure summary helpers.
- `frontend/src/lib/ap-data-manager.test.ts` — data-layer unit tests.
- `frontend/src/app/data-manager/page.tsx` — live Data Manager screen.
- `frontend/src/app/data-manager/page.test.tsx` — page behavior tests.

### Modify

- `.env.example` — document `INTEGRATION_HEALTH_MAX_AGE_HOURS=24`.
- `app/routers/__init__.py` — export the Data Manager router without disturbing Workbench exports.
- `app/main.py` — register the Data Manager router after the Workbench router.
- `frontend/src/components/layout/Sidebar.tsx` — add desktop Data Manager navigation.
- `frontend/src/components/layout/MobileSidebar.tsx` — add mobile Data Manager navigation.
- `PROJECT_REQUIREMENTS.md` — add measurement, refresh, no-side-effect, and unknown-state rules.
- `ARCHITECTURE_AND_CODING_DESIGN.md` — document service boundaries, endpoints, evidence sources,
  persistence, and testing.
- `PROJECT_STATUS.md` — record completed scope, verification evidence, and live dependencies.

No dependency or database migration is required. `httpx`, the `Integration` model, the four seeded
registry rows, and the required integration-health columns already exist.

---

### Task 1: Lock status semantics and safe diagnostic behavior

**Files:**

- Create: `tests/test_ap_data_manager.py`
- Create: `app/services/integration_health.py`

- [ ] **Step 1: Add failing unit tests for the measurement value and 24-hour boundary**

Start `tests/test_ap_data_manager.py` with deterministic UTC timestamps and these assertions:

```python
from datetime import datetime, timedelta, timezone

from app.services.integration_health import (
    IntegrationMeasurement,
    activity_status,
    safe_error_category,
)

NOW = datetime(2026, 8, 4, 15, 0, tzinfo=timezone.utc)


def test_activity_status_is_unknown_without_activity():
    assert activity_status(None, NOW, 24) == "unknown"


def test_activity_status_keeps_exact_boundary_healthy():
    assert activity_status(NOW - timedelta(hours=24), NOW, 24) == "healthy"


def test_activity_status_degrades_only_after_boundary():
    assert activity_status(NOW - timedelta(hours=24, seconds=1), NOW, 24) == "degraded"


def test_safe_error_category_never_returns_raw_secret_text():
    raw = "Authorization: Bearer secret-value https://hooks.slack.com/services/private"
    assert safe_error_category(raw) == "authentication_failure"


def test_measurement_detail_contains_only_allowlisted_fields():
    measurement = IntegrationMeasurement(
        status="down",
        measurement_method="read_only_endpoint_probe",
        checked_at=NOW,
        latency_ms=120,
        records_seen=0,
        last_activity_at=None,
        detail={"message": "Connector request failed", "http_status": 401},
        last_error="authentication_failure",
    )
    assert measurement.detail == {
        "message": "Connector request failed",
        "http_status": 401,
    }
```

- [ ] **Step 2: Run the focused tests and confirm RED**

```powershell
$env:DATABASE_URL='postgresql://workbench:workbench_test@127.0.0.1:55432/workbench_test'
$env:AUTH_BYPASS='true'
pytest tests/test_ap_data_manager.py -q
```

Expected: collection fails because `app.services.integration_health` does not exist.

- [ ] **Step 3: Implement the minimal measurement and pure status helpers**

Create `app/services/integration_health.py` with these public contracts:

```python
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Any, Literal

IntegrationStatus = Literal["healthy", "degraded", "down", "unknown"]


@dataclass(frozen=True)
class IntegrationMeasurement:
    status: IntegrationStatus
    measurement_method: str
    checked_at: datetime
    latency_ms: int | None = None
    records_seen: int = 0
    last_activity_at: datetime | None = None
    detail: dict[str, str | int | float | bool | None] = field(default_factory=dict)
    last_error: str | None = None


def activity_status(
    last_activity_at: datetime | None,
    now: datetime,
    max_age_hours: float,
) -> IntegrationStatus:
    if last_activity_at is None:
        return "unknown"
    return (
        "healthy"
        if now - last_activity_at <= timedelta(hours=max_age_hours)
        else "degraded"
    )


def safe_error_category(value: object) -> str:
    text = str(value).lower()
    if "timeout" in text:
        return "timeout"
    if "401" in text or "403" in text or "auth" in text:
        return "authentication_failure"
    return "connector_failure"
```

Do not add generic arbitrary-detail sanitization. Construct every detail dictionary from explicit
allowlisted keys at the measurement site.

- [ ] **Step 4: Run the focused tests and confirm GREEN**

Run the Step 2 command. Expected: 5 passed.

- [ ] **Step 5: Check the scoped diff**

```powershell
git diff --check -- app/services/integration_health.py tests/test_ap_data_manager.py
git status --short
```

Expected: only the two new Data Manager files appear for this task; existing Workbench changes are
still present and untouched.

---

### Task 2: Implement Supabase and Supervity read-only probes test-first

**Files:**

- Modify: `tests/test_ap_data_manager.py`
- Modify: `app/services/integration_health.py`
- Modify: `.env.example`

- [ ] **Step 1: Add async failing tests for safe active probes**

Use `httpx.MockTransport` so tests never contact external services:

```python
import httpx
import pytest

from app.services.integration_health import SupabaseHealthClient, measure_supervity


@pytest.mark.asyncio
async def test_supabase_probe_is_unknown_when_unconfigured():
    client = SupabaseHealthClient(url="", service_key="")
    result = await client.measure(NOW)
    assert result.status == "unknown"
    assert result.detail == {"message": "Health probe is not configured"}


@pytest.mark.asyncio
async def test_supabase_probe_is_read_only_and_records_exact_count():
    async def handler(request: httpx.Request) -> httpx.Response:
        assert request.method == "GET"
        assert request.url.path.endswith("/rest/v1/ap_invoices")
        assert request.url.params["select"] == "belnr"
        assert request.url.params["limit"] == "1"
        assert request.headers["Prefer"] == "count=exact"
        return httpx.Response(206, json=[{"belnr": "redacted"}], headers={"Content-Range": "0-0/450"})

    http_client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    client = SupabaseHealthClient("https://example.supabase.co", "secret", http_client)
    result = await client.measure(NOW)
    await http_client.aclose()

    assert result.status == "healthy"
    assert result.records_seen == 450
    assert result.detail == {"message": "Read-only query succeeded", "http_status": 206}
    assert "redacted" not in str(result.detail)


class FakeSupervityConfig:
    def __init__(self, configured: bool):
        self.configured = configured


class FakeSupervityClient:
    def __init__(self, configured=True, result=None):
        self.config = FakeSupervityConfig(configured)
        self.result = result or ("healthy", 42, {"sample": "must not escape"})

    async def health(self):
        return self.result


@pytest.mark.asyncio
async def test_supervity_probe_does_not_require_workflow_id_or_expose_sample():
    result = await measure_supervity(FakeSupervityClient(), NOW)
    assert result.status == "healthy"
    assert result.latency_ms == 42
    assert result.detail == {"message": "Read-only run listing succeeded"}
```

Add separate tests for Supabase timeout/401 and unconfigured Supervity. Assert errors contain only
`timeout`, `authentication_failure`, or `connector_failure`, never the raw response body.

- [ ] **Step 2: Run the new tests and confirm RED**

```powershell
pytest tests/test_ap_data_manager.py -q
```

Expected: failures for missing `SupabaseHealthClient` and `measure_supervity`.

- [ ] **Step 3: Implement the Supabase health client**

Add a client with environment construction and optional injected `httpx.AsyncClient`:

```python
import os
import time

import httpx


class SupabaseHealthClient:
    def __init__(self, url: str, service_key: str, client: httpx.AsyncClient | None = None):
        self._url = url.rstrip("/")
        self._service_key = service_key
        self._client = client

    @classmethod
    def from_env(cls) -> "SupabaseHealthClient":
        return cls(
            os.getenv("SUPABASE_URL", "").strip(),
            os.getenv("SUPABASE_SERVICE_KEY", "").strip(),
        )

    async def measure(self, now: datetime) -> IntegrationMeasurement:
        if not self._url or not self._service_key:
            return IntegrationMeasurement(
                status="unknown",
                measurement_method="read_only_endpoint_probe",
                checked_at=now,
                detail={"message": "Health probe is not configured"},
            )

        owned_client = self._client is None
        client = self._client or httpx.AsyncClient(timeout=10.0)
        started = time.monotonic()
        try:
            response = await client.get(
                f"{self._url}/rest/v1/ap_invoices",
                params={"select": "belnr", "limit": "1"},
                headers={
                    "apikey": self._service_key,
                    "Authorization": f"Bearer {self._service_key}",
                    "Prefer": "count=exact",
                    "Range": "0-0",
                },
            )
            latency = int((time.monotonic() - started) * 1000)
            response.raise_for_status()
            total = _content_range_total(response.headers.get("Content-Range"))
            return IntegrationMeasurement(
                status="healthy",
                measurement_method="read_only_endpoint_probe",
                checked_at=now,
                latency_ms=latency,
                records_seen=total,
                last_activity_at=now,
                detail={"message": "Read-only query succeeded", "http_status": response.status_code},
            )
        except (httpx.TimeoutException, httpx.HTTPError) as exc:
            latency = int((time.monotonic() - started) * 1000)
            status_code = exc.response.status_code if isinstance(exc, httpx.HTTPStatusError) else None
            detail = {"message": "Read-only query failed"}
            if status_code is not None:
                detail["http_status"] = status_code
            return IntegrationMeasurement(
                status="down",
                measurement_method="read_only_endpoint_probe",
                checked_at=now,
                latency_ms=latency,
                detail=detail,
                last_error=safe_error_category(exc),
            )
        finally:
            if owned_client:
                await client.aclose()
```

Implement `_content_range_total` to return the integer after `/`, or zero for missing, `*`, or
malformed headers. Never inspect or persist the JSON response body.

- [ ] **Step 4: Implement safe Supervity mapping**

Add `measure_supervity(client, now)` that checks `client.config.configured` before calling health.
Map unconfigured to `unknown`, configured success to `healthy`, and configured failure to `down`.
Persist only a fixed message, status, latency, and safe error category; discard the returned sample.

- [ ] **Step 5: Document the freshness variable**

Add under the backend or integration section in `.env.example`:

```dotenv
# Outlook/Slack activity stays healthy for this many hours (must be positive)
INTEGRATION_HEALTH_MAX_AGE_HOURS=24
```

- [ ] **Step 6: Run focused tests and diff checks**

```powershell
pytest tests/test_ap_data_manager.py -q
git diff --check -- app/services/integration_health.py tests/test_ap_data_manager.py .env.example
```

Expected: all focused tests pass and no secret values appear in the diff.

---

### Task 3: Add passive Outlook and Slack evidence plus atomic persistence

**Files:**

- Modify: `tests/test_ap_data_manager.py`
- Modify: `app/services/integration_health.py`

- [ ] **Step 1: Add PostgreSQL fixtures for isolated integration activity**

Create unique run IDs with `uuid4()`. Insert Outlook `Run` rows and Slack `RunEvent` rows using the
approved contract:

```python
Run(
    run_id=run_id,
    status="completed",
    trigger_source="outlook",
    started_at=NOW - timedelta(hours=2),
)

RunEvent(
    run_id=run_id,
    seq=1,
    event_type="integration_activity",
    operator_name="Slack",
    payload={"integration_key": "slack", "outcome": "success"},
    ts=NOW - timedelta(hours=1),
)
```

The fixture must delete only its unique `RunEvent` and `Run` rows in `finally`. Snapshot the four
seeded `Integration` rows before tests that refresh them, then restore all health fields afterward.

- [ ] **Step 2: Add failing tests for passive evidence**

Cover these exact cases:

- Outlook: zero rows → unknown; recent row → healthy; row older than 24 hours → degraded.
- Slack: zero events → unknown; recent success → healthy; stale success → degraded; a newer failure
  overrides an older success and becomes down.
- Slack `records_seen` counts successful delivery events only.
- Slack stores only an allowlisted `error_category`, truncated to 80 safe characters; it never stores
  the full payload.

Normalize an event-provided category with this exact rule before persistence:

```python
import re


def safe_activity_error_category(value: object) -> str:
    normalized = re.sub(r"[^a-z0-9_.-]+", "_", str(value).lower()).strip("_")[:80]
    return normalized or "connector_failure"
```

Use direct service calls with `SessionLocal()` and injected `now=lambda: NOW`.

- [ ] **Step 3: Run the passive-evidence tests and confirm RED**

```powershell
pytest tests/test_ap_data_manager.py -q -k "outlook or slack or refresh"
```

Expected: failures for missing passive measurement and service methods.

- [ ] **Step 4: Implement `IntegrationHealthService`**

Give the service these public methods:

```python
class IntegrationHealthService:
    def __init__(
        self,
        db: Session,
        *,
        supabase: SupabaseHealthClient | None = None,
        supervity: SupervityClient | None = None,
        now: Callable[[], datetime] | None = None,
        max_age_hours: float | None = None,
    ): ...

    def snapshot(self) -> list[Integration]: ...

    async def refresh(self) -> tuple[list[Integration], bool]: ...
```

Implementation rules:

1. Parse `INTEGRATION_HEALTH_MAX_AGE_HOURS`, defaulting to 24 only when absent. Reject zero,
   negative, NaN, or non-numeric values with a clear configuration error.
2. Query Outlook with `count(Run.id)` and `max(Run.started_at)` filtered by `trigger_source`.
3. Query Slack events using PostgreSQL JSON extraction:

```python
RunEvent.event_type == "integration_activity"
RunEvent.payload["integration_key"].astext == "slack"
```

4. Order Slack attempts by `RunEvent.ts.desc(), RunEvent.id.desc()` so the latest attempt controls
   status.
5. Measure all four integrations into memory first.
6. Update only existing registry rows, matching by key.
7. Persist `detail` as `{"measurement_method": measurement.measurement_method, **measurement.detail}`
   so the method is always explicit without accepting arbitrary connector payloads.
8. Set `last_checked_at` for every measurement and clear stale latency/error fields when a new result
   does not supply them.
9. Commit once after all rows are assigned. On unexpected exceptions, roll back and re-raise.
10. Return `partial_failure=True` only when at least one measured status is `down`; unknown is not a
   refresh failure.

- [ ] **Step 5: Add a rollback test**

Monkeypatch `db.commit` to raise `SQLAlchemyError`, then assert `db.rollback` was called and persisted
registry values remain unchanged in a fresh session.

- [ ] **Step 6: Run the complete backend Data Manager tests**

```powershell
pytest tests/test_ap_data_manager.py -q
git diff --check -- app/services/integration_health.py tests/test_ap_data_manager.py
```

Expected: all Data Manager backend tests pass.

---

### Task 4: Add authenticated Data Manager API contracts

**Files:**

- Create: `app/schemas/ap_data_manager.py`
- Create: `app/routers/ap_data_manager.py`
- Modify: `app/routers/__init__.py`
- Modify: `app/main.py`
- Modify: `tests/test_ap_data_manager.py`

- [ ] **Step 1: Add failing list and refresh endpoint tests**

Add tests that call:

```python
persisted = client.get("/api/ap/data-manager")
refreshed = client.post("/api/ap/data-manager/refresh")
```

Assert the response shape:

```python
{
    "integrations": [
        {
            "key": "outlook",
            "name": "Microsoft Outlook",
            "category": "channel",
            "purpose": str,
            "status": "unknown",
            "measurement_method": "recorded_run_activity",
            "last_checked_at": str | None,
            "latency_ms": int | None,
            "records_seen": int,
            "last_activity_at": str | None,
            "detail": dict | None,
            "last_error": str | None,
        }
    ],
    "counts": {"healthy": int, "degraded": int, "down": int, "unknown": int},
    "freshness_hours": 24.0,
    "partial_failure": bool,
}
```

Patch the router's service factory for the POST test so no external request occurs. Also assert GET
does not call any probe.

- [ ] **Step 2: Run endpoint tests and confirm RED**

```powershell
pytest tests/test_ap_data_manager.py -q -k "endpoint or api"
```

Expected: 404 for both routes.

- [ ] **Step 3: Implement Pydantic schemas**

Create models with `ConfigDict(from_attributes=True)` where appropriate and literals for the four
statuses. Keep `detail` typed as `dict[str, str | int | float | bool | None] | None`. Do not expose
internal database IDs.

- [ ] **Step 4: Implement the thin router**

Use:

```python
router = APIRouter(prefix="/ap/data-manager", tags=["AP Data Manager"])


@router.get("", response_model=DataManagerResponse)
def get_data_manager(
    db: Session = Depends(get_db),
    _current_user: dict | None = Depends(get_current_user),
): ...


@router.post("/refresh", response_model=DataManagerResponse)
async def refresh_data_manager(
    db: Session = Depends(get_db),
    _current_user: dict | None = Depends(get_current_user),
): ...
```

Build counts from the returned rows, always including all four status keys. Derive
`measurement_method` from `Integration.detail["measurement_method"]`; the service must place that
fixed method label into persisted detail alongside the safe message.

- [ ] **Step 5: Register the router without disturbing Workbench wiring**

Add `ap_data_manager_router` to `app/routers/__init__.py` imports and `__all__`. Import it in
`app/main.py` and include it immediately after `ap_workbench_router`.

Before and after editing, inspect scoped diffs because both files already contain uncommitted
Workbench changes:

```powershell
git diff -- app/main.py app/routers/__init__.py
```

- [ ] **Step 6: Run API and full backend tests**

```powershell
pytest tests/test_ap_data_manager.py -q
pytest -q
```

Expected: Data Manager tests pass and the complete backend count increases from the current 41 with
no regressions.

- [ ] **Step 7: Check backend scope and formatting**

```powershell
git diff --check -- app tests .env.example
git status --short
```

Do not stage or commit overlapping files at this checkpoint.

---

### Task 5: Add the typed frontend data layer test-first

**Files:**

- Create: `frontend/src/types/ap-data-manager.ts`
- Create: `frontend/src/lib/ap-data-manager.ts`
- Create: `frontend/src/lib/ap-data-manager.test.ts`

- [ ] **Step 1: Write failing helper tests**

Test `summarizeIntegrationStatuses` and the two API calls:

```typescript
expect(
  summarizeIntegrationStatuses([
    { status: 'healthy' },
    { status: 'unknown' },
    { status: 'healthy' },
    { status: 'down' },
  ])
).toEqual({ healthy: 2, degraded: 0, down: 1, unknown: 1 })
```

Mock `@/lib/api-client` and assert:

```typescript
expect(apiClient.get).toHaveBeenCalledWith('/api/ap/data-manager')
expect(apiClient.post).toHaveBeenCalledWith('/api/ap/data-manager/refresh')
```

- [ ] **Step 2: Run the unit test and confirm RED**

```powershell
Set-Location frontend
npm.cmd run test:run -- src/lib/ap-data-manager.test.ts --reporter=dot
```

Expected: module-not-found failure.

- [ ] **Step 3: Define exact frontend types**

Create:

```typescript
export type IntegrationStatus = 'healthy' | 'degraded' | 'down' | 'unknown'

export interface IntegrationHealth {
  key: string
  name: string
  category: string
  purpose: string
  status: IntegrationStatus
  measurement_method: string | null
  last_checked_at: string | null
  latency_ms: number | null
  records_seen: number
  last_activity_at: string | null
  detail: Record<string, string | number | boolean | null> | null
  last_error: string | null
}

export interface StatusCounts {
  healthy: number
  degraded: number
  down: number
  unknown: number
}

export interface DataManagerResponse {
  integrations: IntegrationHealth[]
  counts: StatusCounts
  freshness_hours: number
  partial_failure: boolean
}
```

- [ ] **Step 4: Implement the API helpers and pure summary**

Use the existing `apiClient`:

```typescript
export const getDataManager = () =>
  apiClient.get<DataManagerResponse>('/api/ap/data-manager')

export const refreshDataManager = () =>
  apiClient.post<DataManagerResponse>('/api/ap/data-manager/refresh')
```

The pure summary must initialize all four counts to zero and increment only recognized statuses.

- [ ] **Step 5: Run focused tests and TypeScript**

```powershell
npm.cmd run test:run -- src/lib/ap-data-manager.test.ts --reporter=dot
npx.cmd tsc --noEmit
```

Expected: focused tests and TypeScript pass.

---

### Task 6: Build the Data Manager page and navigation test-first

**Files:**

- Create: `frontend/src/app/data-manager/page.test.tsx`
- Create: `frontend/src/app/data-manager/page.tsx`
- Modify: `frontend/src/components/layout/Sidebar.tsx`
- Modify: `frontend/src/components/layout/MobileSidebar.tsx`

- [ ] **Step 1: Write failing page tests using mocked API helpers**

Use the established Workbench test pattern and mock `getDataManager`/`refreshDataManager`. Cover:

1. Initial loading text.
2. Rendering all four integrations and status summary counts.
3. Unknown detail shown as `Awaiting real Outlook activity`.
4. Latency shown for Supabase and omitted when null.
5. Empty registry state.
6. Initial request error with retry.
7. Refresh button disabled while pending.
8. Partial-failure banner after a response with `partial_failure: true`.
9. Authoritative rendering from the refresh response.

Use an API fixture containing Outlook unknown, Supabase healthy with latency, Slack down, and
Supervity healthy.

- [ ] **Step 2: Run the page test and confirm RED**

```powershell
npm.cmd run test:run -- src/app/data-manager/page.test.tsx --reporter=dot
```

Expected: module-not-found failure for the page.

- [ ] **Step 3: Implement the smallest accessible page**

The page must:

- Fetch persisted state once in `useEffect`.
- Keep `loading`, `refreshing`, `error`, and `data` state separate.
- Keep the last successful snapshot visible when refresh fails.
- Render four summary tiles using API `counts` rather than recomputing hidden business state.
- Render integration cards with semantic status labels and text, not color alone.
- Render `last_checked_at` and `last_activity_at` as `Never` when null.
- Render latency only when non-null.
- Render safe detail entries, never raw objects with `JSON.stringify`.
- Disable `Refresh health` while refreshing and set `aria-busy`.
- Provide retry buttons for initial and refresh errors.

Use the existing `Card`, `Button`, `Icons`, brand colors, and motion style. Do not add dependencies
or copy placeholder integration data from Settings.

- [ ] **Step 4: Add desktop and mobile navigation**

Add this item to the `System` section in both navigation files:

```typescript
{ href: '/data-manager', label: 'Data Manager', icon: Icons.network }
```

`Icons.network` already exists; do not edit the icon registry.

- [ ] **Step 5: Run focused and full frontend tests**

```powershell
npm.cmd run test:run -- src/app/data-manager/page.test.tsx --reporter=dot
npm.cmd run test:run -- --reporter=dot
```

Expected: the new page tests pass and the existing seven Workbench tests remain green.

- [ ] **Step 6: Run TypeScript after generating stable Next types**

Do not run `next build` and `tsc` concurrently because both access `.next/types`.

```powershell
npm.cmd run build
npx.cmd tsc --noEmit
```

Expected: production build and TypeScript pass. The two documented unrelated unused-variable
warnings and pre-existing chart-container warning may remain.

- [ ] **Step 7: Check frontend scope**

```powershell
Set-Location ..
git diff --check -- frontend/src
git status --short
```

Do not stage or commit package or Workbench files.

---

### Task 7: Update mandatory documentation and verify the complete slice

**Files:**

- Modify: `PROJECT_REQUIREMENTS.md`
- Modify: `ARCHITECTURE_AND_CODING_DESIGN.md`
- Modify: `PROJECT_STATUS.md`

- [ ] **Step 1: Update project requirements**

Add a `Data Manager Requirements` section recording:

- Outlook, Supabase, and Slack measured across two categories.
- Unknown before passive evidence exists.
- Configurable 24-hour activity freshness.
- Read-only Supabase/Supervity probing.
- No test email or Slack side effects.
- Persisted refresh data and explicit UI states.
- Secret and bank-data redaction.

- [ ] **Step 2: Update architecture and coding design**

Document the service/schema/router boundaries, both endpoints, passive event contract, one-commit
refresh transaction, frontend data flow, and test strategy. Link to
`docs/superpowers/specs/2026-08-04-ap-data-manager-design.md`.

- [ ] **Step 3: Update project status honestly**

Move Data Manager implementation to Completed only after all automated checks pass. Keep these live
dependencies Pending:

- Real Outlook-triggered run evidence.
- Real Slack `integration_activity` event from Ku's notification path.
- Real Supabase credentials and health probe.
- Final live gate proof and Workbench Auto-run acceptance test.

Correct the stale `Current Next Step` so it does not assign the separately handled Entity & Approval
Operator to this repository session.

- [ ] **Step 4: Run complete backend verification**

```powershell
$env:DATABASE_URL='postgresql://workbench:workbench_test@127.0.0.1:55432/workbench_test'
$env:AUTH_BYPASS='true'
pytest -q
```

Expected: all tests pass with zero failures.

- [ ] **Step 5: Run complete frontend verification sequentially**

```powershell
Set-Location frontend
npm.cmd run test:run -- --reporter=dot
npm.cmd run build
npx.cmd tsc --noEmit
Set-Location ..
```

Expected: all Vitest tests, production build, and TypeScript pass.

- [ ] **Step 6: Run repository integrity checks**

```powershell
git diff --check
git status --short --branch
git diff --stat
```

Run a high-confidence secret scan that prints filenames only, never matching values:

```powershell
rg -l --hidden -g '!frontend/node_modules/**' -g '!frontend/.next/**' `
  '(sk-[A-Za-z0-9_-]{20,}|gh[pousr]_[A-Za-z0-9]{20,}|AKIA[0-9A-Z]{16}|-----BEGIN (RSA |EC |OPENSSH )?PRIVATE KEY-----)' .
```

Expected: no high-confidence secret-like values in project files. Review the final diff for sample
IDs, hardcoded statuses, thresholds, credentials, webhook URLs, and unrelated edits.

- [ ] **Step 7: Request approval before any implementation commit**

Report the exact modified/untracked file set and verification counts. Do not stage or commit the
implementation, merge, push, or create a PR until Lim chooses the next action.

---

### Task 8: Perform live Data Manager acceptance when external activity is available

**Files:** None unless a verified defect requires a separately approved fix.

- [ ] **Step 1: Configure local secrets without exposing them**

Populate the ignored `.env` locally with `SUPABASE_URL`, `SUPABASE_SERVICE_KEY`,
`SUPERVITY_API_KEY`, and `SUPERVITY_ACTIVE_ORG`. The Orchestrator workflow ID is not required for
the Supervity read-only health check. Never paste secret values into chat or Git.

- [ ] **Step 2: Start the stack and refresh Data Manager**

Open `/data-manager`, choose `Refresh health`, and verify Supabase and Supervity show measured
read-only results with latency and no sensitive detail.

- [ ] **Step 3: Verify passive Outlook evidence**

After a real Outlook-triggered AP run exists, refresh and confirm Outlook changes from Unknown to
Healthy with the real run count and activity time.

- [ ] **Step 4: Verify passive Slack evidence**

After Ku's notification path records a real successful `integration_activity` event, refresh and
confirm Slack changes from Unknown to Healthy without Data Manager sending any message.

- [ ] **Step 5: Record remaining gate status**

Do not call the Round 2 integration gate green until Outlook, Supabase, and Slack all show honest
live evidence across the required categories. Preserve screenshots and database evidence for the
demo checklist without exposing credentials or full bank information.
