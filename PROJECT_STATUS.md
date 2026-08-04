# Project Status

**Updated:** 2026-08-04

## Completed Foundation

- AP database models and migration for policies, runs, events, decisions, Workbench items, insights, and integrations.
- Supervity client and policy-engine foundation.
- Round 2 delivery plan and verified dataset/oracle documentation.
- Local backend and frontend runtime proven during project setup.
- AP Bank Change Verification hero flow implemented in Supervity and verified with `BANK_MISMATCH` plus `BEC_SUSPECTED` evidence.

## In Progress

- Lim-owned Workbench UI and resolution API.
- Final standalone regression checks for Bank Change Verification.

## Pending

- AP Entity and Approval Control Operator.
- Data Manager page with live Outlook, Supabase, and Slack health.
- Remaining Operators and final Orchestrator integration owned according to `ap/DELIVERY_PLAN_R2.md`.
- Full five-Operator regression against the expected oracle.
- Final clean-clone, integration-health, and demo rehearsal checks.

## Known Issues

- The existing `frontend/src/app/workbench/page.tsx` is template placeholder content and is not connected to AP data.
- AP Workbench API routes are not yet implemented or registered.
- Windows Docker startup previously required a runtime line-ending workaround; no permanent tracked startup-script change has been made.

## Current Next Step

Implement the approved AP Workbench human-review design with API tests, frontend tests, and immutable-decision verification.

