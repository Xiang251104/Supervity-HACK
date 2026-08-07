# Project Status

**Updated:** 2026-08-07

## Completed Foundation

- AP database models and migration for policies, runs, events, decisions, Workbench items, insights, and integrations.
- Supervity client and policy-engine foundation.
- Round 2 delivery plan and verified dataset/oracle documentation.
- Local backend and frontend runtime proven during project setup.
- AP Bank Change Verification hero flow implemented in Supervity and verified with `BANK_MISMATCH` plus `BEC_SUSPECTED` evidence.
- Live AP Workbench API for queue, detail, and transactional human resolution.
- AP Workbench Command Center page with filtering, evidence inspection, protected-value visibility, and Approve/Reject/Request Information actions.
- Reviewer actions preserve the AI verdict and append a separate `human_action` audit event.
- AP Data Manager service, authenticated snapshot/refresh API, and persisted integration-health page for Outlook, Supabase, Slack, and Supervity.
- Tracked Git EOL policy for Linux shell entrypoints; `start_gunicorn.sh` is stored and checked out as LF on Windows clean clones.

## Automated Verification

- Backend `pytest -q` with the local PostgreSQL test database and `AUTH_BYPASS=true`: 142 passed with five existing dependency/deprecation warnings. This includes the Data Manager redaction regression and repository-hygiene checks for the tracked LF policy.
- Frontend full Vitest: four files and 24 tests passed.
- Next.js production build and subsequent `tsc --noEmit`: passed sequentially; the known warnings below remain.
- `git diff --check`: passed. The filename-only high-confidence secret scan excluding `node_modules` and `.next` returned no matches.
- Final unrelated-change review found no credentials, webhook URLs, sample identifiers, fake/demo health, or hardcoded live integration status. No implementation files were staged or committed.

## In Progress

- Final standalone regression checks for Bank Change Verification.

## Pending

- AP Entity and Approval Control Operator.
- Real Outlook-triggered run evidence for passive health measurement.
- Real Slack `integration_activity` producer evidence from Ku's notification path.
- Real Supabase credentials and successful read-only health probe.
- Real Supervity credentials and successful read-only health probe.
- Final live integration-gate proof and Workbench Auto-run acceptance test.
- Remaining Operators and final Orchestrator integration owned according to `ap/DELIVERY_PLAN_R2.md`.
- Full five-Operator regression against the expected oracle.
- Final clean-clone, integration-health, and demo rehearsal checks.

## Live Acceptance and Evidence Checklist

Task 8 in `docs/superpowers/plans/2026-08-04-ap-data-manager-implementation.md` records the same live workflow. All evidence below is owned by Lim; Outlook depends on the external Orchestrator run producer, and Slack depends on Ku's notification path emitting the standardized event.

- [ ] From the repository root in Windows PowerShell, create local configuration only when absent, set the required local secrets without copying their values into documentation or chat, start the stack, and migrate:

  ```powershell
  if (-not (Test-Path .env)) { Copy-Item .env.example .env }
  # Set local NEXTAUTH, Supabase, and Supervity values in the ignored .env.
  # If clean-clone database defaults conflict locally, adjust only the ignored .env without printing secret values.
  .\scripts\start.ps1
  docker compose exec backend alembic upgrade head
  ```

- [ ] Open `http://localhost:3001/auth/signin`, sign in as an `admin` or `user`, then open `http://localhost:3001/data-manager`. Retain the initial persisted snapshot and select the exact `Refresh health` action.
- [ ] Have the external Orchestrator producer create a real Outlook-triggered AP run. Refresh and record the card plus safe `ap_runs` count/latest-time evidence. A recent run is `healthy`, a stale run is `degraded`, and no run is `unknown`; Outlook has no `down` transition in this observer.
- [ ] Have Ku's notification path record a real Slack `integration_activity` delivery event. Refresh and record the card plus safe `ap_run_events` delivery evidence. Recent success is `healthy`, stale success is `degraded`, latest failure is `down`, and no evidence is `unknown`; Data Manager must not send a test message.
- [ ] With real Supabase configuration, select `Refresh health` and record a `healthy` read-only invoice probe with measured latency and safe count. Missing configuration is `unknown`; expected request failure is `down` with an allowlisted category.
- [ ] With real Supervity configuration, select `Refresh health` and record a `healthy` read-only list-runs probe with safe latency. Missing configuration is `unknown`; expected probe failure is `down`. Confirm no run sample or connector error text is returned. A Supervity Orchestrator workflow ID is not required for this health probe.
- [ ] Capture redacted Data Manager screenshots and corresponding safe `ap_integrations`, Outlook-run, and Slack-event database evidence. Confirm credentials, raw payloads, invoice identifiers, and complete bank data are absent.
- [ ] Record only the following safe database evidence; these commands exclude integration detail, event payloads, run identifiers, invoice identifiers, and credentials:

  ```powershell
  docker compose exec -T postgres sh -c 'psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" -c "SELECT key, category, status, last_checked_at, latency_ms, records_seen, last_activity_at, last_error FROM ap_integrations ORDER BY key;"'
  docker compose exec -T postgres sh -c 'psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" -c "SELECT count(*) AS outlook_run_count, max(started_at) AS latest_outlook_activity_at FROM ap_runs WHERE trigger_source = ''outlook'';"'
  docker compose exec -T postgres sh -c 'psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" -c "SELECT count(*) FILTER (WHERE payload ->> ''outcome'' = ''success'') AS slack_success_count, max(ts) FILTER (WHERE payload ->> ''outcome'' = ''success'') AS latest_slack_success_at FROM ap_run_events WHERE event_type = ''integration_activity'' AND payload ->> ''integration_key'' = ''slack'';"'
  docker compose exec -T postgres sh -c 'psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" -c "SELECT ts, payload ->> ''outcome'' AS outcome, payload ->> ''error_category'' AS error_category FROM ap_run_events WHERE event_type = ''integration_activity'' AND payload ->> ''integration_key'' = ''slack'' ORDER BY ts DESC LIMIT 1;"'
  ```

- [ ] Gate 5 passes only when Outlook (`channel`), Supabase (`system_of_record`), and Slack (`channel`) are all live and `healthy`, matching Gate 5 at lines 217-221 and demo step 7 at line 256 of `ap/DELIVERY_PLAN_R2.md`. `degraded`, `down`, and `unknown` remain valid diagnostics but fail and keep Gate 5 pending. Supervity evidence is required by this checklist but is not one of the three Gate 5 integrations.

### Workbench Auto-run Acceptance

- [ ] Run a real Auto workflow that creates a pending Workbench exception with an immutable AI verdict of `REVIEW` or `BLOCK`.
- [ ] Open `http://localhost:3001/workbench` and verify the pending item exposes its linked decision, reason codes, recommendation, protected value, and evidence without changing the AI verdict.
- [ ] Resolve the item with one supported terminal action, `Approve` or `Reject`, and a mandatory reviewer note. Confirm the item closes, the AI verdict remains unchanged, and a separate `human_action` audit event records the human resolution.
- [ ] Repeat the terminal resolution request and confirm it returns a conflict rather than overwriting the existing human decision. (`Request Information` is also supported but intentionally leaves the item open.)

### Clean-clone Verification

- [ ] Use a separate disposable clone or worktree; do not clean, reset, or reuse this intentionally dirty worktree. Substitute unused paths in the following PowerShell commands:

  ```powershell
  git clone <repository-url> <new-disposable-path>
  Set-Location <new-disposable-path>
  if (-not (Test-Path .env)) { Copy-Item .env.example .env }
  # Set local values only in the ignored .env; adjust clean-clone database defaults there if needed and never print or paste secret values into evidence.
  .\scripts\start.ps1
  docker compose exec backend alembic upgrade head
  # Run once for this fresh clone; skip only if ap_control_tower_test already exists.
  docker compose exec postgres createdb -U user ap_control_tower_test
  python -m venv .venv
  .\.venv\Scripts\python.exe -m pip install -r packages/requirements.txt
  $env:DATABASE_URL='postgresql://user:password@127.0.0.1:5432/ap_control_tower_test'
  $env:AUTH_BYPASS='true'
  .\.venv\Scripts\python.exe -m alembic upgrade head
  .\.venv\Scripts\python.exe -m pytest -q
  Set-Location frontend
  npm.cmd ci
  npm.cmd run test:run -- --reporter=dot
  npm.cmd run build
  npx.cmd tsc --noEmit
  Set-Location ..
  ```

- [ ] In that disposable environment, sign in and smoke-test both `http://localhost:3001/data-manager` and `http://localhost:3001/workbench`; confirm persisted reads, refresh, navigation, and authorized access work without sample data.

### Demo Rehearsal

- [ ] Perform the relevant Gate 4 Workbench and Gate 5 Data Manager sequence twice. Each pass must use redacted real evidence, no demo/fake/oracle-derived rows, all three Gate 5 integrations `healthy`, and one real pending Workbench exception resolved with its separate audit event.
- [ ] Pass the rehearsal only when both sequences complete without credential or complete-bank-data exposure; otherwise record the failed step and keep the demo gate pending.

## Known Issues

- Windows clean-clone shell startup is fixed by the tracked `*.sh text eol=lf` Git policy; the startup script no longer needs a runtime line-ending workaround.
- The frontend production dependency tree reports four transitive Socket.IO/WebSocket advisories (two moderate, two high). They predate the Workbench runtime path and require a controlled dependency upgrade rather than a forced audit rewrite.
- The production build reports two pre-existing unused-variable warnings in AI pages and a chart container-size warning outside the Workbench route.

## Current Next Step

Finish the standalone Bank Change Verification regression, collect the real Outlook, Slack, Supabase, and Supervity evidence above, then complete Workbench Auto-run acceptance and the clean-clone/demo rehearsal.

