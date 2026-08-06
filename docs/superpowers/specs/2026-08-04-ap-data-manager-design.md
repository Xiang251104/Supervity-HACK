# AP Data Manager Integration-Health Design

**Date:** 2026-08-04

**Owner:** Lim

**Status:** Approved for implementation planning

## Goal

Deliver a live Data Manager page that measures and explains the health of Microsoft Outlook,
Supabase, Slack, and Supervity Auto without hardcoded statuses, synthetic activity, secret
exposure, or unwanted external messages.

The Round 2 scoring gate requires at least three live integrations across at least two categories.
The required integrations are Outlook (`channel`), Supabase (`system_of_record`), and Slack
(`channel`). Supervity Auto (`agent_platform`) remains visible as the fourth seeded integration.

## Scope

This slice includes:

- Persisted integration-health summaries backed by `ap_integrations`.
- A safe, read-only Supabase probe with measurable latency.
- Passive Outlook health derived from real AP runs.
- Passive Slack health derived from recorded delivery attempts.
- Reuse of the existing read-only Supervity health check.
- List and refresh API endpoints.
- A responsive `/data-manager` page with explicit loading, empty, refreshing, partial-failure,
  and error states.
- Backend and frontend tests plus updates to the three mandatory project documents.

This slice excludes:

- Sending test email or Slack messages.
- Modifying Supervity Operators or the Orchestrator.
- Creating synthetic integration events or demo health data.
- Managing credentials in the UI.
- Changing policies, Workbench behavior, dashboard metrics, or Insights.

## Chosen Approach

Use a hybrid active/passive model:

- Probe Supabase and Supervity with safe read-only requests because availability can be measured
  without business side effects.
- Derive Outlook and Slack health from real recorded activity because direct probes would require
  additional connector credentials or could generate unwanted external actions.
- Label the measurement method in every response so operators can distinguish endpoint
  availability from observed workflow activity.

A passive-only design would not detect a Supabase outage until another workflow failed. An
active-probe design for all connectors would add credentials and side-effect risk without improving
the required demo evidence.

## Backend Architecture

### Service

Create `app/services/integration_health.py`. It owns measurement, status calculation, sanitization,
and persistence. Routers do not perform health logic.

The service receives external clients and the current time through injectable dependencies. Tests
therefore use fake clients and a fixed clock rather than real network calls.

The configurable freshness window is read from:

```text
INTEGRATION_HEALTH_MAX_AGE_HOURS=24
```

The value must be positive. A successful Outlook or Slack activity remains healthy while its age
is less than or equal to this window; it becomes degraded only when its age exceeds the window.

### Schemas

Create `app/schemas/ap_data_manager.py` with:

- An integration summary containing key, name, category, purpose, status, measurement method,
  last check, latency, records seen, last activity, safe detail, and safe last error.
- A list response containing integration summaries, status counts, and the configured freshness
  window.
- A refresh response with the refreshed snapshot and an indication that one or more measurements
  failed when applicable.

No schema includes credentials, authentication headers, webhook URLs, full external payloads, or
complete bank information.

### Router

Create `app/routers/ap_data_manager.py` with two authenticated endpoints:

- `GET /api/ap/data-manager` returns the last persisted measurements without contacting external
  services.
- `POST /api/ap/data-manager/refresh` runs safe measurements, persists their results, and returns
  the refreshed snapshot.

Register the router through `app/routers/__init__.py` and `app/main.py` using the existing API
composition pattern.

## Measurement Rules

### Supabase

The backend uses `SUPABASE_URL` and `SUPABASE_SERVICE_KEY` from the environment. These variables are
for backend health checks and Insights only; Supervity Operators continue to use Auto's native
Supabase OAuth action.

The probe performs a read-only request for at most one `ap_invoices.belnr` value and requests an
exact row count. It records:

- `measurement_method = "read_only_endpoint_probe"`
- Round-trip latency.
- The total row count as `records_seen` when provided by Supabase.
- The check time as `last_activity_at` only when the read succeeds.

Status rules:

- Missing configuration: `unknown`, with safe detail stating that the health probe is not
  configured.
- Successful read: `healthy`.
- Timeout, authentication failure, connector error, or unexpected response: `down`.

Stored diagnostics may contain an HTTP status code or sanitized error category. They must not
contain the request URL, service key, authorization header, response body, or returned invoice
identifier.

### Outlook

Outlook is measured from `ap_runs` rows where `trigger_source = "outlook"`:

- `records_seen` is the count of matching runs.
- `last_activity_at` is the latest matching `started_at`.
- `measurement_method = "recorded_run_activity"`.
- No matching run: `unknown` with `Awaiting real Outlook activity`.
- Latest run within the configured freshness window: `healthy`.
- Latest run older than the window: `degraded`.

The Data Manager does not create Outlook runs and does not call Microsoft APIs.

### Slack

Slack is measured from standardized `ap_run_events` rows:

```json
{
  "event_type": "integration_activity",
  "payload": {
    "integration_key": "slack",
    "outcome": "success | failure",
    "error_category": "optional safe category"
  }
}
```

The Orchestrator or notification producer owns emitting this event after a real delivery attempt;
this Data Manager slice only reads it. That producer change is an external integration dependency
and is not implemented on Lim's Workbench/Data Manager branch.

- `records_seen` is the count of successful Slack delivery events.
- `last_activity_at` is the timestamp of the latest recorded attempt.
- `measurement_method = "recorded_delivery_activity"`.
- No delivery attempt: `unknown` with `Awaiting real Slack activity`.
- Latest attempt succeeded within the freshness window: `healthy`.
- Latest attempt succeeded but is older than the window: `degraded`.
- Latest attempt failed: `down` with only its safe error category.

The refresh endpoint never sends a Slack message.

### Supervity Auto

Reuse `SupervityClient.health()`, which performs a read-only list-runs request and measures latency.
Data Manager maps missing API-key or active-organization configuration to `unknown`; a configured
request that fails maps to `down`; success maps to `healthy`.

The Orchestrator workflow ID is not required for this health check because it does not execute a
workflow.

## Persistence and Failure Handling

Each refresh updates every seeded `Integration` row with the measured:

- `status`
- `last_checked_at`
- `latency_ms`
- safe `detail`
- safe `last_error`
- `records_seen`
- `last_activity_at`

Measurements are independent. An expected connector failure is stored as that integration's health
result and does not discard successful measurements for other integrations. The refresh response
still returns the complete registry and marks the snapshot as partially failed when at least one
integration is `down`. An `unknown` integration is awaiting evidence or configuration and does not
by itself mark the refresh as failed.

An unexpected database or service-level failure rolls back the refresh transaction and returns an
API error. Previously persisted health remains unchanged. The frontend keeps the last visible
snapshot and presents a retry action.

## Frontend Design

Create `frontend/src/app/data-manager/page.tsx`, typed models under `frontend/src/types/`, and API
helpers under `frontend/src/lib/`. Add Data Manager to both desktop and mobile navigation.

The page contains:

- Summary counts for Healthy, Degraded, Down, and Unknown.
- One integration card for Outlook, Supabase, Slack, and Supervity.
- Name, category, purpose, current status, measurement method, last check time, latency when
  measurable, records seen, last activity, and safe diagnostics.
- A `Refresh health` action that is disabled and visibly busy while a refresh is running.
- Explicit initial loading, empty registry, partial-failure, complete-error, and normal states.

The UI must not infer health from the presence of a registry row. It renders only persisted service
results and labels Unknown as `Awaiting activity` or `Not configured` based on safe detail.

## Testing Strategy

Backend tests cover:

- Supabase healthy, missing configuration, timeout, and connector failure.
- Outlook unknown, healthy, degraded, and the exact 24-hour boundary.
- Slack unknown, recent success, stale success, and latest-attempt failure.
- Supervity configured and unconfigured mappings.
- Persistence of every health field.
- Safe diagnostic redaction.
- Partial connector failures and transaction rollback on database failure.
- `GET` returning persisted values without probing and `POST` refreshing values.

Frontend tests cover:

- Rendering all status summaries and integration fields.
- Loading, empty, partial-failure, and complete-error states.
- Refresh submission, disabled state, and authoritative post-refresh rendering.
- Multi-category display and omission of latency when it is not measurable.

Final verification runs the complete backend suite, complete frontend suite, strict TypeScript
checking, Next.js production build, `git diff --check`, a secret scan, and a final unrelated-change
review.

## Acceptance Criteria

- Outlook, Supabase, and Slack appear with honest measured status across two integration categories.
- No integration is healthy merely because its registry row or credentials exist.
- Outlook and Slack remain Unknown until real activity is recorded.
- Successful Outlook and Slack activity remains healthy for a configurable 24-hour window.
- Supabase health is based on a successful read-only query with measured latency.
- Refresh persists results and never sends email or Slack notifications.
- Diagnostics expose no secrets, webhook URLs, external response bodies, invoice identifiers, or
  complete bank information.
- The page visibly supports loading, empty, refresh, partial-failure, and error states.
- Automated tests and production verification pass.

## External Integration Dependency

The Slack card cannot become healthy until the Orchestrator or its notification producer records
the standardized `integration_activity` event after a real Slack delivery. The missing Orchestrator
workflow ID does not block implementing or testing Data Manager, but it does block proving this
live Slack activity and the final Round 2 integration gate.
