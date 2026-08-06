# AP Workbench Human-Review Design

**Date:** 2026-08-04  
**Owner:** Lim  
**Status:** Approved for implementation planning

## Goal

Replace the placeholder Workbench with a live human-review queue that displays complete AP exception context and lets an authenticated reviewer approve, reject, or request information without changing the AI's original decision.

## Scope

This slice includes:

- A live queue backed by `ap_workbench_items`.
- A detail view containing the linked immutable `ap_decisions` verdict and the Workbench item's stored context.
- Priority and status filters.
- Reviewer actions: `approve`, `reject`, and `request_info`.
- Append-only `human_action` run events for every reviewer action.
- A responsive split-view Workbench page with loading, empty, success, and failure states.

This slice excludes:

- Creating Workbench items from the Orchestrator.
- Data Manager integration-health screens.
- Policy editing, insights, batch processing, and AI Manager behavior.
- Any mutation of an AI decision's verdict, reason codes, evidence, protected value, or policy snapshot.

## Architecture

### Backend boundaries

Create a dedicated AP Workbench router, schemas, and service:

- `app/routers/ap_workbench.py` owns HTTP validation and response codes.
- `app/schemas/ap_workbench.py` defines queue, detail, and resolution contracts.
- `app/services/workbench.py` owns database queries and transactional resolution behavior.
- `app/main.py` registers the router under the existing `/api` router.

The API surface is:

- `GET /api/ap/workbench` lists items and accepts optional `status` and `priority` filters.
- `GET /api/ap/workbench/{item_id}` returns the Workbench item, its review context, and its linked AI decision.
- `POST /api/ap/workbench/{item_id}/resolve` accepts `action` and `note`.

The service reads the authenticated reviewer identity from the existing authorization dependency. It updates only human-review columns on `ap_workbench_items` and `ap_decisions`. It also inserts one `ap_run_events` row with `event_type = "human_action"`.

### Resolution semantics

- `approve`: Workbench status becomes `resolved`; decision `human_status` becomes `APPROVED`.
- `reject`: Workbench status becomes `resolved`; decision `human_status` becomes `REJECTED`.
- `request_info`: Workbench status stays `open`; decision `human_status` becomes `PENDING_INFORMATION`.
- A non-empty reviewer note is required for every action.
- Approve or reject on an already resolved item returns HTTP 409.
- Missing Workbench items return HTTP 404.

The following AI fields are immutable and must never be written by the resolution service:

- `verdict`
- `reason_codes`
- `evidence`
- `money_protected`
- `spend_under_review`
- `policy_version_label`
- `confidence`

### Frontend boundaries

Replace `frontend/src/app/workbench/page.tsx` and keep the page focused on review operations:

- Queue pane: exception title, invoice number, primary reason, priority, age, assignee, and status.
- Filters: open/resolved and priority.
- Detail pane: invoice/vendor identifiers, immutable AI verdict, reason codes, recommendation, protected value, and stored evidence.
- Resolution panel: action selector, mandatory note, confirmation, and result feedback.

Create focused components under `frontend/src/components/ap/workbench/` and API types/helpers under `frontend/src/lib/ap-workbench.ts`. The page refetches queue and detail after a successful action instead of mutating cached business state optimistically.

## Data Flow

1. The page requests `GET /api/ap/workbench?status=open`.
2. Selecting an item requests its detail endpoint.
3. The reviewer selects an action and enters a note.
4. The page posts the resolution request.
5. The backend validates item state and writes Workbench, human-decision, and run-event changes in one transaction.
6. The page refreshes the queue and selected detail from the API.

## Error Handling

- Network and server errors remain visible in the relevant pane with a retry action.
- Invalid actions or blank notes return HTTP 422.
- Concurrent resolution conflicts return HTTP 409 without overwriting the first reviewer.
- If the linked decision is absent, the item can still be displayed, but resolution returns a clear integrity error rather than inventing decision data.
- Database failures roll back all resolution writes.

## Testing Strategy

Backend tests cover:

- Unfiltered and filtered queue results.
- Item detail with linked immutable decision data.
- Approve, reject, and request-information state transitions.
- Mandatory notes, missing items, and duplicate resolution conflicts.
- Proof that immutable AI decision fields do not change.
- One append-only `human_action` event per successful action.

Frontend tests cover:

- Queue rendering from API data.
- Loading, empty, and error states.
- Detail selection.
- Mandatory reviewer note validation.
- Correct request payload and post-action refresh.

The final verification runs the Python test suite, frontend tests, lint, and the production frontend build.

## Acceptance Criteria

- At least one real AP exception is visible from live backend data.
- A reviewer can approve or reject it in the Workbench.
- Request Information keeps the item open.
- The human action is visible after refresh and in `ap_run_events`.
- The AI's initial verdict and supporting evidence remain byte-for-byte unchanged.
- No sample queue data remains in the Workbench page.

