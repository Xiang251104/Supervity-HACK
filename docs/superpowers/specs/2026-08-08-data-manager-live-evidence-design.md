# Data Manager Live-Evidence Design

## Goal

Make existing Data Manager Outlook and Slack indicators reflect durable evidence emitted by real AP runs, without altering the Data Manager UI or its probes.

## Approved behaviour

After canonical invoice output is collected, a run whose trigger source remains the default `api` is changed to `outlook` exactly when `canonical_invoice.source_channel`, after trimming and uppercasing, is `EMAIL`. An explicitly supplied non-default trigger source wins.

After policy evaluation, only a decision that opens a Workbench item sends an automatic exception alert. The alert identifies the actual run, invoice, vendor (or safe fallback), amount, verdict, and reason codes. Account-shaped values are redacted before posting.

The completed run, decision, and Workbench item are committed before the best-effort Slack operation. Successful, failed, and unconfigured sends are then recorded and committed as `integration_activity` run events with `integration_key: slack`, actual outcome, a redacted safe detail, and safe correlation metadata. An unexpected send exception is likewise recorded as `failed`; none of these outcomes can roll back the already durable decision or Workbench item. Pay-ready runs create no automatic Slack event. Exception logs use fixed safe text and an exception type only, never transport detail or traceback.

## Data flow and ordering

Auto output -> canonical invoice -> default-source derivation -> policy gate -> decision + Workbench item + completed run commit -> Slack send -> integration event commit.

The integration event uses the next run-local sequence after existing events, preserving normal event order. No migration is in scope to enforce sequence uniqueness at the database level.

## Scope boundaries

No schema migration, Data Manager endpoint/UI/probe changes, fabricated health signals, test or production credential additions, or hardcoded invoice/vendor identities are part of this work.
