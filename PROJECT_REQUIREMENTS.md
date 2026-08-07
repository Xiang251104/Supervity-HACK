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
- Keep protected-exposure totals separated by currency in the queue summary.
- Return a conflict for repeated attempts to resolve an already closed item.

## Data Manager Requirements

- Measure Outlook, Supabase, and Slack across the channel and system-of-record categories, with Supervity Auto also visible as the agent platform.
- Report passive Outlook and Slack health as Unknown until real activity evidence exists.
- Classify Outlook only as `unknown`, `healthy`, or `degraded` from run presence and freshness; Data Manager does not inspect Outlook run outcome and therefore does not assign Outlook `down`.
- Apply a configurable activity-freshness window that defaults to 24 hours.
- Probe Supabase and Supervity with read-only requests only.
- Never send test email or Slack notifications during a health refresh.
- Persist refresh measurements and show explicit loading, empty, refreshing, partial-failure, and error states in the UI.
- Redact credentials, webhook details, connector payloads, invoice identifiers, and complete bank data from stored and returned diagnostics.
- Return a diagnostic message only when it exactly matches the code-owned, service-generated safe-message vocabulary; arbitrary stored strings must fail closed.
- Restrict both Data Manager endpoints to authenticated users with the `admin` or `user` role.

## AP Policies Console Requirements

- Replace `/ai/policies` generic demonstration content with a focused AP Policies Console backed by live policy API data.
- Restrict policy listing, updates, and history to authenticated principals with the `admin` or `user` role.
- Display the current AP policy list with its stable policy fields and active-policy snapshot label, including key, description, value, unit, value type, severity, active state, version, and update metadata.
- Validate edits against the persisted policy type: `number`, `enum`, `boolean`, or `date`; enum values must match the stored options.
- Return HTTP 404 for an unknown policy key. Return HTTP 422 for an invalid typed value, non-finite number, invalid date, or enum value outside the stored options.
- Record the authenticated actor and an optional change note for a real value change; a same-value update succeeds without a version increment or history row.
- Preserve append-only, newest-first version history with previous and new values, actor, timestamp, note, and version.
- Provide loading, empty, error/retry, filtering, type-specific editing, saving, validation feedback, and on-demand history states in the UI.
- Close an edit dialog only after a successful authoritative PATCH response and refetch the list; history remains isolated from list failures and refetches when reopened.
- Do not add policy creation, deletion, or metadata editing. Do not retain the generic builder, AI creation, or permission-matrix content on this route.

## Quality Requirements

- Backend behavior is covered by automated tests.
- Frontend behavior is covered by focused component tests and a production build.
- Database writes are transactional and connector or integrity failures are explicit.
- Secrets and connection credentials remain environment-managed and are never committed.
- Reviewer actions must commit the human-owned state and append-only audit event atomically.

