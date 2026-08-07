# AP Policies Console Design

**Date:** 2026-08-07  
**Status:** Approved for implementation  
**Route:** `/ai/policies`

## Purpose

Replace the generic demonstration-only AI Policies page with a focused Accounts
Payable policy console backed by the existing `ap_policies` and
`ap_policy_versions` tables. An authorized operator must be able to inspect the
active AP rules, change a supported policy value without editing code, and see
the append-only version history that makes later decisions reproducible.

This slice exposes and edits the policy engine that already exists in
`app/services/policies.py`. It does not redesign the runtime evaluation engine or
change the seeded policy vocabulary.

## Goals

- Replace all policy demo data and simulated loading with authoritative API data.
- Display every seeded AP policy with its key, description, current value, unit,
  value type, severity, active state, version, and last update metadata.
- Allow an authenticated `admin` or `user` to edit a policy value and record an
  optional change note.
- Validate edits according to the stored policy metadata before committing them.
- Append a `PolicyVersion` row only when the stored value actually changes.
- Show the selected policy's append-only change history.
- Refetch authoritative data after mutation instead of relying on optimistic
  business-state updates.
- Provide explicit loading, empty, error, saving, validation-error, and success
  states.

## Non-goals

- Creating or deleting policy definitions.
- Editing policy keys, names, descriptions, units, severity, or value types.
- Replacing the existing policy evaluation engine.
- Building natural-language policy generation, a generic structured-rule builder,
  permission matrices, or AI translation.
- Adding a database migration.
- Changing policy active/inactive state in this slice.
- Displaying or mutating invoice decisions or policy-evaluation records.

The existing generic `Create with AI`, `Structured Builder`, and `Permission
Matrix` experiences are unrelated to the AP policy model and will be removed from
this route rather than partially connected.

## Existing Domain Model

`Policy` is the current editable rule definition. Its `value_type` is one of
`number`, `enum`, `boolean`, or `date`; `options` constrains enum policies; `unit`
is display metadata; and `version` identifies the current revision.

`PolicyVersion` is append-only history containing the new value, previous value,
actor, note, version number, and timestamp. The existing `update_policy()` service
already handles version increments, history insertion, a single commit, and
no-op updates.

The API and UI will preserve these responsibilities. HTTP adapters will remain
thin, validation will be centralized before `update_policy()`, and the frontend
will not reproduce policy-engine verdict logic.

## API Contract

### List policies

`GET /api/ap/policies`

Returns:

```json
{
  "items": [
    {
      "key": "PRICE-TOLERANCE",
      "name": "Price tolerance",
      "description": "...",
      "value_type": "number",
      "value": 2,
      "options": null,
      "unit": "%",
      "severity": "escalate",
      "active": true,
      "version": 1,
      "updated_at": "2026-08-07T12:00:00Z",
      "updated_by": "user@example.com"
    }
  ],
  "total": 10,
  "snapshot_label": "v1.1.1.1.1.1.1.1.1.1"
}
```

Policies are ordered by key for stable rendering. The snapshot label is built
from the same active policy versions used by the runtime policy engine.

### Update one policy value

`PATCH /api/ap/policies/{key}`

Request:

```json
{
  "value": 3.5,
  "note": "Approved tolerance adjustment for the August close."
}
```

The response is the complete updated policy representation used by the list
endpoint. A same-value request succeeds without incrementing the version or
adding history. The authenticated principal is recorded as `changed_by`; a safe
development fallback may be used only when the existing authentication bypass is
active.

Failure semantics:

- `404` when the policy key does not exist.
- `422` when the value has the wrong type, is not finite, is an invalid date, or
  is not one of the stored enum options.
- Unexpected persistence failures remain server errors and rely on the existing
  session lifecycle for rollback; they are not converted into successful data.

### Read policy history

`GET /api/ap/policies/{key}/history`

Returns:

```json
{
  "policy_key": "PRICE-TOLERANCE",
  "items": [
    {
      "version": 2,
      "value": 3.5,
      "previous_value": 2,
      "changed_by": "user@example.com",
      "changed_at": "2026-08-07T12:05:00Z",
      "note": "Approved tolerance adjustment for the August close."
    }
  ],
  "total": 1
}
```

History is ordered newest first. An unknown policy returns `404`; a known policy
with no history returns an empty array.

## Validation Rules

Validation is driven by the persisted `Policy.value_type` and `Policy.options`:

- `number`: accept JSON integers or floats, reject booleans and non-finite values.
- `enum`: accept a string that exactly matches one of the stored options.
- `boolean`: accept only a JSON boolean.
- `date`: accept an ISO calendar date in `YYYY-MM-DD` form and preserve it as a
  string.
- Unknown value types fail closed with a validation error rather than accepting an
  arbitrary JSON value.

The note is optional, trimmed, and length-limited by the request schema. Metadata
validation happens before the transactional version update. Enum validation in
`update_policy()` remains as a second line of defense.

## Backend Structure

- Add `app/schemas/ap_policies.py` for public list, detail, update, and history
  contracts.
- Add `app/routers/ap_policies.py` for the three endpoints.
- Extend `app/services/policies.py` with a focused value-normalization helper while
  preserving the existing pure evaluation functions.
- Register the router in `app/routers/__init__.py` and `app/main.py`.
- Add `/api/ap/policies.*` to the authorization map for `admin` or `user`.

The list route calls `build_snapshot()` after loading the displayed policies so
the label has exactly the same semantics as a runtime snapshot. The update route
loads metadata, validates the candidate value, invokes `update_policy()`, and
returns the refreshed row. The history route reads only `PolicyVersion` rows.

## Frontend Design

The `/ai/policies` route becomes a single-purpose AP console using the project's
existing layout, typography, cards, buttons, dialogs, and toast primitives.

### Page regions

1. Header: `AP Policies`, a concise governance explanation, and a refresh action.
2. Summary: total policies, active policies, current snapshot label, and the most
   recently updated policy when available.
3. Search/filter bar: text search plus `All`, `Block`, `Escalate`, and `Advise`
   severity filters.
4. Policy list: accessible rows/cards showing current value, unit, severity,
   active state, version, and last update.
5. Edit dialog: immutable policy description and metadata, type-specific value
   control, optional change note, validation feedback, cancel, and save.
6. History panel/dialog: newest-first version entries with previous/new value,
   actor, timestamp, and note.

### Type-specific editing

- Number policies use a number input and retain decimal values.
- Enum policies use a select populated only from `options`.
- Boolean policies use the existing switch component.
- Date policies use a date input.

The page never invents values, options, versions, actors, or timestamps. A save
calls PATCH, closes only after success, then reloads the authoritative list. The
history view loads on demand and can be refreshed after an edit.

### Frontend data layer

- Add `frontend/src/types/ap-policies.ts` for the API contracts.
- Add `frontend/src/lib/ap-policies.ts` for list, update, history, formatting, and
  pure validation helpers.
- Add focused reusable components under `frontend/src/components/ap/policies/`.
- Replace `frontend/src/app/ai/policies/page.tsx` without modifying unrelated demo
  policy components unless removal of now-unused imports requires it.

## State and Error Handling

- Initial load shows a labelled loading state.
- Initial failure shows the API error and a retry action.
- An empty response shows a truthful no-policies state.
- Saving disables duplicate submission and keeps the dialog open on error.
- Validation errors appear beside the relevant control before a request is sent.
- History loading and history failure are isolated from the main policy list.
- A successful update produces confirmation and then displays server-returned
  version/value data after refetch.

## Security and Audit

- No credentials, connector metadata, invoice identifiers, or policy evaluation
  payloads are returned by these endpoints.
- Existing authentication and authorization middleware protects all three routes.
- The server, not the browser, supplies `changed_by`.
- Policy history is append-only through the existing service.
- No secrets or environment values are introduced.

## Test Strategy

Implementation follows test-driven development.

Backend tests cover:

- stable policy listing and snapshot label;
- all four value types;
- invalid type, boolean-as-number, non-finite number, malformed date, and invalid
  enum rejection;
- unknown policy handling;
- version increment and append-only history;
- same-value no-op behavior;
- authenticated actor and note recording;
- history ordering and empty history.

Frontend tests cover:

- typed API helper paths and PATCH payload;
- pure value validation and formatting;
- loading, live list, empty, and initial-error states;
- search/severity filtering;
- type-specific editor rendering;
- successful edit, failed edit, validation feedback, and authoritative refetch;
- history loading, entries, and error isolation;
- absence of the generic demo policy-builder tabs and demo records.

Final verification runs focused policy tests, the complete backend suite with the
required test database, the complete frontend Vitest suite, strict TypeScript,
the Next.js production build, `git diff --check`, and a targeted secret/demo-data
scan.

## Acceptance Criteria

- `/ai/policies` contains no simulated or generic demonstration policy data.
- At least the 10 seeded AP policies are visible from the live database.
- A judge can change a threshold or enum value without code and see the new value
  and incremented version.
- The change appears in append-only history with actor, timestamp, previous value,
  new value, and optional note.
- Invalid values are rejected without changing the stored policy or history.
- Existing policy-engine tests continue to pass.
- All required project documentation reflects the new API, UI, verification, and
  remaining live-policy acceptance work.
