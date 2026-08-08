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

### AP Policies API

- `Policy` and append-only `PolicyVersion` remain the persistent AP policy model. `app/services/policies.py` owns policy-engine operations and the existing transactional `update_policy()` path, which increments the version, records history, and commits only when the normalized value changes.
- `app/schemas/ap_policies.py` defines the public list, update, and history contracts. `app/routers/ap_policies.py` is a thin HTTP adapter: it loads policy metadata, validates and normalizes the requested value, reuses `update_policy()`, and serializes authoritative persisted rows.
- `GET /api/ap/policies` returns key-ordered policy items and an active-policy snapshot label built with the same snapshot semantics as the runtime policy engine. `PATCH /api/ap/policies/{key}` returns the updated representation, records the authenticated actor and optional note, and treats a same-value request as a successful no-op. `GET /api/ap/policies/{key}/history` returns append-only history newest first; known policies without history return an empty collection.
- An unknown key returns HTTP 404. A value that fails the four-type contract, is non-finite, is an invalid date, or is not an allowed enum option returns HTTP 422. Authentication failures return HTTP 401 and authenticated principals outside `admin` or `user` return HTTP 403 through the existing authorization map.
- No migration was required: the existing AP policy and policy-version migration schema supports this slice. The API does not create or delete definitions or edit policy metadata.

### AP Policies Frontend

- `frontend/src/types/ap-policies.ts` contains API types and `frontend/src/lib/ap-policies.ts` contains typed API helpers, display formatting, and pure client-side validation. The `/ai/policies` route is implemented by `frontend/src/app/ai/policies/page.tsx` with focused list, summary, edit-dialog, and history-dialog components in `frontend/src/components/ap/policies/`.
- The page renders live list and summary data, search and severity filtering, explicit loading/empty/error/retry states, and editors selected by policy type. It has no generic policy-builder, AI creation, or permission-matrix surface.
- A successful PATCH closes the editor only after receiving the server response and then refetches the list; it does not maintain optimistic business state. Save errors and validation errors leave the editor open.
- History is loaded on demand and is intentionally isolated from the main list state, with its own empty, error, retry, and reopen-refetch behavior.
- Focused backend tests cover list/snapshot, all four types, validation, authorization behavior, actor/note, no-op/version/history, and history ordering. Focused frontend tests cover helpers and page behavior including list states, filtering, type-specific editing, authoritative refetch, and history isolation.

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
- Enforce `*.sh text eol=lf` in `.gitattributes` so Docker can execute Linux shell entrypoints from Windows clean clones without runtime conversion.
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
- Repository-hygiene tests enforce the tracked shell-script LF policy and verify that the Linux startup entrypoint contains no CRLF bytes.

The approved Data Manager design is documented in `docs/superpowers/specs/2026-08-04-ap-data-manager-design.md`.

# 2026-08-08 — Live-evidence design

`app.routers.ap_runs.start_run` derives the persisted default trigger source only after Auto's canonical invoice is available. It treats normalized `EMAIL` as Outlook-originated, but preserves an explicitly non-default source. After policy gating, the router creates a Workbench item first and then performs the Slack notification as a best-effort side effect. It appends a `RunEvent(event_type="integration_activity")` with the next available sequence number and a standardized Slack outcome payload, so integration health is based on real run activity rather than a synthetic probe.

`app.services.slack.build_exception_alert` is the narrowly-scoped formatter for this automatic exception alert. It applies the existing account-number redactor across every composed field. The router catches unexpected notification exceptions and records a safe `failed` outcome, preserving the already-created decision and Workbench item.
