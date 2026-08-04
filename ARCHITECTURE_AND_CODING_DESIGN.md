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

AP human review uses the existing `Decision`, `WorkbenchItem`, and `RunEvent` models. The Workbench service owns state transitions and keeps decision-system fields separate from human-resolution fields.

## Frontend Structure

- Route pages live under `frontend/src/app/`.
- Reusable AP components live under `frontend/src/components/ap/`.
- Typed API functions and view models live under `frontend/src/lib/`.
- Pages fetch live backend data through the existing API client and render explicit loading, empty, error, and success states.

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

