# AP Workbench Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Deliver a live AP exception queue where a reviewer can inspect a linked immutable AI decision and record Approve, Reject, or Request Information actions with an append-only audit event.

**Architecture:** Add a focused FastAPI router over the existing `WorkbenchItem`, `Decision`, and `RunEvent` tables. Resolution is transactional: it updates only human-owned columns on the workbench item and decision, then appends one `human_action` run event. Replace the placeholder Next.js workbench page with a client-side master/detail queue backed by these endpoints.

**Tech Stack:** FastAPI, SQLAlchemy, Pydantic v2, PostgreSQL, pytest/httpx, Next.js 15, React 19, TypeScript, Tailwind CSS.

---

## Task 1: Lock the backend API contract with failing tests

- [x] Create `tests/test_ap_workbench.py` with fixtures that insert one `Run`, linked `Decision`, and `WorkbenchItem` into the existing PostgreSQL test database and remove only those fixture rows afterward.
- [x] Add a test for `GET /api/ap/workbench` returning the open queue with its linked verdict summary and honoring `status` and `priority` filters.
- [x] Add a test for `GET /api/ap/workbench/{id}` returning full decision evidence and a 404 for an unknown item.
- [x] Add parameterized tests for `POST /api/ap/workbench/{id}/resolve` actions `approve`, `reject`, and `request_info`, requiring a non-blank note.
- [x] Assert approve/reject resolve the item, while request_info keeps it open and sets decision `human_status` to `PENDING_INFORMATION`.
- [x] Assert immutable AI fields (`verdict`, `reason_codes`, `evidence`, policy label, money protected) remain unchanged.
- [x] Assert exactly one `RunEvent(event_type="human_action")` is appended with the reviewer and action payload.
- [x] Assert repeated approve/reject attempts return HTTP 409.
- [x] Run the focused test and confirm RED because the router does not exist.

## Task 2: Implement the FastAPI workbench API

- [x] Create `app/schemas/ap_workbench.py` with list/detail/decision/resolve response models and a resolve request validator for the three allowed actions and non-blank note.
- [x] Create `app/routers/ap_workbench.py` with list, detail, and resolve endpoints under `/ap/workbench`.
- [x] Resolve the reviewer identity from authenticated user claims (`email`, `preferred_username`, or `sub`).
- [x] Perform the resolution updates and `RunEvent` insert in one transaction; roll back on exceptions.
- [x] Compute the next event sequence as `max(seq) + 1` for the run.
- [x] Export the router from `app/routers/__init__.py` and include it from `app/main.py`.
- [x] Run the focused workbench tests and confirm GREEN.
- [x] Run the complete backend suite and confirm no regression.

## Task 3: Add a testable frontend data layer

- [x] Add `frontend/src/types/ap-workbench.ts` for queue, decision detail, and resolution types.
- [x] Add `frontend/src/lib/ap-workbench.ts` with pure query-string construction and API functions for list, detail, and resolve.
- [x] Add Vitest and Testing Library configuration only if required for focused component tests.
- [x] Write failing tests for filter query construction and resolution action payloads before implementing the data functions.
- [x] Implement the smallest data-layer code that passes those tests.

## Task 4: Build the AP Workbench interface

- [x] Replace `frontend/src/app/workbench/page.tsx` with a client-side queue/detail layout.
- [x] Add status and priority filters, queue counts, and selectable exception cards.
- [x] Show invoice identity, amount/currency, AI verdict, reason codes, recommendation, evidence, money protected, and current human status.
- [x] Add Approve, Reject, and Request Information controls with a mandatory reviewer note.
- [x] Disable actions while submitting and show success/error feedback.
- [x] Refetch queue and detail after a successful action so the UI reflects the database state.
- [x] Provide accessible loading, empty, and error states and keyboard-visible controls.
- [x] Run focused frontend tests and a production build.

## Task 5: Update project documentation and verify end to end

- [x] Update `PROJECT_REQUIREMENTS.md` with the implemented Workbench behaviors and action semantics.
- [x] Update `ARCHITECTURE_AND_CODING_DESIGN.md` with endpoints, transaction boundaries, immutable fields, and frontend data flow.
- [x] Update `PROJECT_STATUS.md` with completed scope, verification commands, and remaining Round 2 tasks.
- [x] Run the full backend test suite with the documented local PostgreSQL connection.
- [x] Run the full frontend test suite and production build.
- [x] Inspect `git diff --check`, `git status`, and the final diff for unrelated changes or secrets.
