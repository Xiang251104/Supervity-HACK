# Project Requirements

## Product Goal

Build an AP Control Tower in which a Supervity Orchestrator coordinates five specialist Operators and a live Command Center exposes activity, policies, insights, human review, integration health, and an immutable audit trail.

## Core Requirements

- Process invoices through at least five distinct specialist Operators.
- Keep business rules in editable policy data rather than hardcoded workflow prompts.
- Persist reproducible run context, Operator events, policy evaluations, and immutable AI decisions.
- Show live Command Center data through backend APIs; do not ship mock or oracle-derived decision rows.
- Route material exceptions to a human Workbench with complete context.
- Preserve AI verdicts while recording human resolution separately.
- Show at least Outlook, Supabase, and Slack as measured integrations in Data Manager.
- Redact sensitive bank information in notifications and user-facing surfaces where full values are unnecessary.

## Workbench Requirements

- List live AP Workbench items with status and priority filters.
- Show the linked invoice decision, reason codes, recommendation, protected value, and evidence.
- Support Approve, Reject, and Request Information with a mandatory reviewer note.
- Close items only for Approve or Reject; Request Information remains open.
- Append an auditable human-action event for every successful action.
- Never mutate the immutable AI verdict fields during human resolution.

## Quality Requirements

- Backend behavior is covered by automated tests.
- Frontend behavior is covered by focused component tests and a production build.
- Database writes are transactional and connector or integrity failures are explicit.
- Secrets and connection credentials remain environment-managed and are never committed.

