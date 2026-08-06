# Architecture and Coding Design

## Stack

- FastAPI and SQLAlchemy backend.
- PostgreSQL with Alembic migrations.
- Next.js 15, React 19, TypeScript, Tailwind CSS, and existing UI primitives.
- Supervity Auto for Operator execution and event streaming.

## Backend Structure

- `app/models/` contains persistent database entities.
- `app/schemas/` contains validated API contracts.
- `app/services/` contains business operations and external-service clients.
- `app/routers/` contains thin HTTP adapters.
- `app/main.py` composes routers under `/api` and applies existing authorization and audit middleware.

AP human review uses the existing `Decision`, `WorkbenchItem`, and `RunEvent` models. The focused Workbench router owns the current state transition transaction and keeps decision-system fields separate from human-resolution fields. If this surface grows beyond the three actions, move that transaction into a dedicated service without changing the API contract.

### AP Workbench API

- `GET /api/ap/workbench?status=&priority=` returns queue summaries joined to their decisions and ordered critical-first.
- `GET /api/ap/workbench/{item_id}` returns the complete review context and immutable decision evidence.
- `POST /api/ap/workbench/{item_id}/resolve` accepts `approve`, `reject`, or `request_info` plus a mandatory note.
- Resolution locks both linked rows, updates human-owned fields, calculates the next run-event sequence, appends one `human_action` event, and commits once.
- Approve and Reject close the item. Request Information keeps it open and sets `PENDING_INFORMATION`.
- A second terminal resolution returns HTTP 409, preventing silent replacement of an existing human decision.

### AP Data Manager

- `app/services/integration_health.py` owns health calculation, safe diagnostics, connector measurement, passive-evidence queries, and persistence.
- `app/schemas/ap_data_manager.py` defines the public integration snapshot and refresh contracts without database IDs or credentials.
- `app/routers/ap_data_manager.py` remains a thin authenticated adapter: `GET /api/ap/data-manager` returns only persisted state, while `POST /api/ap/data-manager/refresh` measures, persists, and returns one authoritative snapshot.
- The global authorization map permits either the `admin` or `user` role. Missing or invalid authentication returns HTTP 401; an authenticated principal without either permitted role returns HTTP 403.
- Supabase and Supervity use active read-only probes. Outlook uses passive `ap_runs` evidence where `trigger_source = "outlook"`; Slack uses passive `ap_run_events` evidence with `event_type = "integration_activity"` and payload fields `integration_key = "slack"`, `outcome = "success | failure"`, and an optional safe `error_category`.
- A refresh measures external probes before opening database work, reads passive evidence, loads the integration registry once, updates existing rows in memory, flushes and detaches the ordered response rows, then commits as the final database operation. Unexpected failures roll back the refresh.

#### Measurement and Failure Semantics

- Outlook observes only matching-run count and latest start time: none is `unknown`, activity at or inside the freshness boundary is `healthy`, and older activity is `degraded`. It never returns `down` because it does not evaluate run outcome.
- Slack observes standardized delivery evidence: no attempt is `unknown`, a recent success is `healthy`, a stale success is `degraded`, and the latest failed attempt is `down`. Its supplied error category is retained only when it is one of the public safe categories below.
- Supabase missing URL or service key is `unknown`; HTTP 200/206 is `healthy`; HTTP 401/403 is `down` with `authentication_failure`; a typed timeout is `down` with `timeout`; all other HTTP responses and `httpx` transport failures are `down` with `connector_failure`. A malformed or absent `Content-Range` produces a safe zero count without exposing a response body.
- Supervity missing API key or active organization is `unknown`. A returned `healthy` result is `healthy`; the concrete client's returned `down` result is `down` with `connector_failure`. A directly raised typed timeout maps to `timeout`, a directly raised HTTP 401/403 maps to `authentication_failure`, and other `SupervityError` or HTTP failures map to `connector_failure`. Returned endpoint/sample/error detail is discarded.
- These expected connector and recorded-delivery outcomes become persisted integration measurements. Unexpected programming errors, invalid service-contract values such as timezone-naive timestamps, and database flush/commit failures propagate; the service rolls back instead of replacing them with fabricated health.

#### Public Diagnostic Contract

- Public statuses are exactly `healthy`, `degraded`, `down`, and `unknown`.
- Public measurement methods are exactly `read_only_endpoint_probe`, `recorded_run_activity`, and `recorded_delivery_activity`, or `null` when persisted data is not allowlisted.
- Public error categories are exactly `authentication_failure`, `timeout`, `rate_limited`, and `connector_failure`, or `null`. An unrecognized stored error on a `down` row is reduced to `connector_failure`; it is omitted for other statuses.
- Public `detail.message` is returned only when it exactly matches the router's code-owned allowlist of the 12 fixed messages emitted by `IntegrationHealthService`; an arbitrary stored string fails closed. Public `detail.http_status` is retained only when its runtime type is a true integer. The router drops every other stored key and value; internal database IDs, raw connector/event payloads, credentials, authorization headers, webhook URLs, response bodies, invoice identifiers, and complete bank data are not returned.

## Frontend Structure

- Route pages live under `frontend/src/app/`.
- Reusable AP components live under `frontend/src/components/ap/`.
- Typed API functions and view models live under `frontend/src/lib/`.
- Pages fetch live backend data through the existing API client and render explicit loading, empty, error, and success states.

The `/workbench` page uses a master/detail layout. Filters are sent to the backend, mutations require a note, and the page refetches authoritative server state after an action. Protected exposure is grouped by currency rather than combined into a misleading cross-currency total.

The `/data-manager` page loads the persisted API snapshot through typed helpers, renders API-provided counts and safe integration details, and sends an explicit refresh request. It keeps loading, refreshing, empty, partial-failure, initial-error, refresh-error, and last-successful-data states separate; it never invents health from registry presence or placeholder data.

## Coding Rules

- Keep routers thin and business state transitions in services.
- Use Pydantic schemas at API boundaries.
- Do not hardcode invoice identifiers, policy thresholds, health states, or demo metrics.
- Do not mutate immutable AI decision fields after insertion.
- Write tests before production behavior changes and verify full suites after each slice.
- Preserve existing naming, formatting, authorization, and error-response conventions.

## Workbench Design

The Workbench is a vertical full-stack slice:

1. Queue and detail reads come from `ap_workbench_items` and linked `ap_decisions`.
2. Resolution updates human-only columns transactionally.
3. Each action appends a `human_action` row to `ap_run_events`.
4. The UI refetches server state after mutation to avoid presenting uncommitted business state.

Detailed behavior is specified in `docs/superpowers/specs/2026-08-04-ap-workbench-design.md`.

## Verification Design

- Backend integration tests use a dedicated local PostgreSQL database and cover list, detail, all three actions, immutable AI fields, audit append, validation, and conflict handling.
- Frontend Vitest tests cover query construction, action payload validation, multi-currency aggregation, live rendering, and action submission.
- The Next.js production build is part of the acceptance gate.
- Data Manager backend tests cover status boundaries, safe redaction including arbitrary stored-message rejection, read-only probes, passive Outlook and Slack evidence, transaction rollback, authentication, and snapshot-versus-refresh behavior against PostgreSQL.
- Data Manager frontend tests cover typed API calls, summaries, loading, empty, error, refresh, partial-failure, and authoritative refreshed rendering; full Vitest, production build, and strict TypeScript checks form the automated gate.

The approved Data Manager design is documented in `docs/superpowers/specs/2026-08-04-ap-data-manager-design.md`.

