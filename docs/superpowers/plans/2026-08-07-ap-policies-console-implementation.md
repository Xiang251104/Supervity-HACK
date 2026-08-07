# AP Policies Console Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the demonstration-only `/ai/policies` route with an authenticated Accounts Payable policy console backed by the existing policy tables and versioning service.

**Architecture:** Add a thin FastAPI router and Pydantic contracts over `Policy`, `PolicyVersion`, `build_snapshot()`, and `update_policy()`. Centralize persisted-metadata value normalization in `app/services/policies.py`, then expose typed frontend helpers and focused React components that always refetch authoritative list data after a mutation. The existing migration already contains every required column, so this slice adds no migration.

**Tech Stack:** Python 3, FastAPI, Pydantic, SQLAlchemy, PostgreSQL, pytest, Next.js 15, React 19, TypeScript, Tailwind CSS, Radix UI, Testing Library, and Vitest.

---

### Task 1: Lock the persisted policy validation contract

**Files:**
- Modify: `tests/test_ap_policies.py`
- Modify: `app/services/policies.py`

- [x] **Step 1: Write failing tests for all persisted value types**

Add parameterized tests that call the wished-for pure API and assert normalized output:

```python
from datetime import date
from math import inf, nan

from app.services.policies import normalize_policy_value


@pytest.mark.parametrize(
    ("value_type", "options", "candidate", "expected"),
    [
        ("number", None, 3, 3),
        ("number", None, 3.5, 3.5),
        ("enum", ["advisory", "review"], "review", "review"),
        ("boolean", None, True, True),
        ("date", None, "2026-08-07", "2026-08-07"),
    ],
)
def test_normalize_policy_value_accepts_supported_values(
    value_type, options, candidate, expected
):
    assert normalize_policy_value(value_type, options, candidate) == expected


@pytest.mark.parametrize(
    ("value_type", "options", "candidate"),
    [
        ("number", None, True),
        ("number", None, "3.5"),
        ("number", None, nan),
        ("number", None, inf),
        ("enum", ["advisory", "review"], "Review"),
        ("boolean", None, 1),
        ("date", None, "2026-02-30"),
        ("date", None, date(2026, 8, 7)),
        ("unknown", None, "anything"),
    ],
)
def test_normalize_policy_value_rejects_invalid_values(
    value_type, options, candidate
):
    with pytest.raises(ValueError):
        normalize_policy_value(value_type, options, candidate)
```

- [x] **Step 2: Run the new tests and verify RED**

Run:

```powershell
& 'C:\Users\User\Documents\AP-Control-Tower-Round2\.worktrees\ap-workbench\.venv\Scripts\python.exe' -m pytest tests\test_ap_policies.py -q
```

Expected: collection fails because `normalize_policy_value` does not exist.

- [x] **Step 3: Implement minimal persisted-metadata normalization**

Add `normalize_policy_value(value_type: str, options: list[Any] | None, candidate: Any) -> Any` using `math.isfinite`, `datetime.date.fromisoformat`, exact enum membership, and explicit `type(candidate) is bool` checks. Reject unknown value types with `ValueError`. Keep `update_policy()` responsible for its existing no-op and transaction behavior.

- [x] **Step 4: Run the focused engine tests and verify GREEN**

Run the Step 2 command.

Expected: all original 12 tests plus the new validation cases pass.

### Task 2: Add AP Policies API contracts and integration behavior

**Files:**
- Create: `app/schemas/ap_policies.py`
- Create: `app/routers/ap_policies.py`
- Create: `tests/test_ap_policies_api.py`
- Modify: `app/routers/__init__.py`
- Modify: `app/main.py`
- Modify: `app/authz.map.json`

- [x] **Step 1: Write failing API tests against an isolated policy database**

Create fixtures that build only `Policy.__table__` and `PolicyVersion.__table__` in an isolated SQLAlchemy test database, override `get_db` and `get_current_user`, and restore dependency overrides after each test. Seed deterministic records for the four value types without reusing product demo records.

Cover these exact tests and assertions:

- `test_list_policies_is_key_ordered_and_returns_snapshot_label`: assert HTTP 200, ascending keys, every public field, total count, and an active-only `v<version>...` label.
- `test_patch_number_policy_increments_version`: PATCH `3.5`, assert HTTP 200, persisted numeric value, version `2`, and one matching history row.
- `test_patch_enum_policy_records_actor_and_trimmed_note`: PATCH an exact stored option with surrounding note whitespace, then assert the response and database history use the authenticated email and trimmed note.
- `test_patch_boolean_policy_accepts_json_boolean_only`: accept `false`; reject `0`, `1`, and string forms with HTTP 422.
- `test_patch_date_policy_accepts_valid_calendar_date`: accept `2026-08-07`; reject malformed and impossible calendar dates with HTTP 422.
- `test_patch_rejects_invalid_values_without_history`: parameterize wrong numeric types, non-finite numeric candidates passed directly to normalization, invalid enum case/value, and unknown stored value types; assert the policy/version-history counts are unchanged.
- `test_patch_unknown_policy_returns_404`: assert HTTP 404 and the stable `Policy not found` detail.
- `test_patch_same_value_is_a_no_op`: assert HTTP 200 while value, version, `updated_by`, and history-row count remain unchanged.
- `test_history_is_newest_first`: seed versions `2` and `3`, assert response versions `[3, 2]` plus previous/new value, actor, timestamp, and note fields.
- `test_known_policy_with_no_history_returns_empty_items`: assert HTTP 200 with the key, `items: []`, and `total: 0`.
- `test_history_unknown_policy_returns_404`: assert HTTP 404 and the stable `Policy not found` detail.

The list assertion must check all public fields (`key`, `name`, `description`, `value_type`, `value`, `options`, `unit`, `severity`, `active`, `version`, `updated_at`, and `updated_by`) plus `total` and the active-only snapshot label. Mutation assertions must query `PolicyVersion` directly to prove append-only history, actor, note, ordering, and no-op behavior.

- [x] **Step 2: Run API tests and verify RED**

Run:

```powershell
$env:DATABASE_URL='sqlite:///./.pytest-ap-policies.db'
$env:AUTH_BYPASS='true'
& 'C:\Users\User\Documents\AP-Control-Tower-Round2\.worktrees\ap-workbench\.venv\Scripts\python.exe' -m pytest tests\test_ap_policies_api.py -q
```

Expected: collection or requests fail because the schema/router/registration do not exist.

- [x] **Step 3: Add exact Pydantic response and request schemas**

Define these models in `app/schemas/ap_policies.py`:

```python
PolicyValue = int | float | str | bool

class APPolicyResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    key: str
    name: str
    description: str
    value_type: Literal["number", "enum", "boolean", "date"]
    value: PolicyValue
    options: list[str] | None
    unit: str | None
    severity: Literal["block", "escalate", "advise"]
    active: bool
    version: int
    updated_at: datetime | None
    updated_by: str | None

class APPolicyListResponse(BaseModel):
    items: list[APPolicyResponse]
    total: int
    snapshot_label: str

class APPolicyUpdateRequest(BaseModel):
    value: PolicyValue
    note: str = Field(default="", max_length=1000)

class APPolicyVersionResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    version: int
    value: PolicyValue
    previous_value: PolicyValue | None
    changed_by: str | None
    changed_at: datetime | None
    note: str | None

class APPolicyHistoryResponse(BaseModel):
    policy_key: str
    items: list[APPolicyVersionResponse]
    total: int
```

Use a field validator to trim `note` while retaining the empty-string default.

- [x] **Step 4: Implement the thin router and registration**

Add `router = APIRouter(prefix="/ap/policies", tags=["AP Policies"])`. The list endpoint orders `Policy.key.asc()`, builds the active snapshot with `build_snapshot(db)`, and returns the full list. The PATCH endpoint loads the policy or raises 404, calls `normalize_policy_value()` before `update_policy()`, maps its validation `ValueError` to 422, derives the actor as `email`, `preferred_username`, `sub`, then `unknown-actor`, and returns the refreshed policy. The history endpoint first proves the policy exists, then orders `PolicyVersion.version.desc(), PolicyVersion.changed_at.desc()`.

Export `ap_policies_router` from `app/routers/__init__.py`, include it in `app/main.py`, and add:

```json
"/api/ap/policies.*": {
  "description": "AP Policies - requires approved user",
  "ANY": ["admin", "user"]
}
```

Do not add a migration: the inspected migration already has all required fields.

- [x] **Step 5: Run API and engine tests and verify GREEN**

Run:

```powershell
$env:DATABASE_URL='sqlite:///./.pytest-ap-policies.db'
$env:AUTH_BYPASS='true'
& 'C:\Users\User\Documents\AP-Control-Tower-Round2\.worktrees\ap-workbench\.venv\Scripts\python.exe' -m pytest tests\test_ap_policies.py tests\test_ap_policies_api.py -q
```

Expected: all focused policy tests pass with no failed assertions.

### Task 3: Add typed frontend API and validation helpers

**Files:**
- Create: `frontend/src/types/ap-policies.ts`
- Create: `frontend/src/lib/ap-policies.ts`
- Create: `frontend/src/lib/ap-policies.test.ts`

- [x] **Step 1: Write failing helper tests**

Mock `apiClient` and assert:

```typescript
expect(apiClient.get).toHaveBeenCalledWith('/api/ap/policies')
expect(apiClient.patch).toHaveBeenCalledWith('/api/ap/policies/PRICE-TOLERANCE', {
  value: 3.5,
  note: 'August close',
})
expect(apiClient.get).toHaveBeenCalledWith('/api/ap/policies/PRICE-TOLERANCE/history')
```

Add pure validation assertions for number, enum, boolean, and date values, including blank/non-finite numbers, exact enum matching, boolean-only input, and impossible calendar dates. Add formatting assertions that preserve server values and append units only for display.

- [x] **Step 2: Run helper tests and verify RED**

Run:

```powershell
npm.cmd run test:run -- src/lib/ap-policies.test.ts --reporter=dot
```

Expected: the test fails because `ap-policies.ts` helpers and types do not exist.

- [x] **Step 3: Implement types and minimal helpers**

Define discriminated policy value types and the list/update/history contracts in `frontend/src/types/ap-policies.ts`. In `frontend/src/lib/ap-policies.ts`, implement `getAPPolicies`, `updateAPPolicy`, `getAPPolicyHistory`, `validatePolicyValue`, `formatPolicyValue`, and a date check that round-trips year/month/day rather than accepting JavaScript date rollover.

- [x] **Step 4: Run helper tests and verify GREEN**

Run the Step 2 command.

Expected: all helper tests pass.

### Task 4: Build the live console shell and explicit list states

**Files:**
- Create: `frontend/src/components/ap/policies/policy-list.tsx`
- Create: `frontend/src/components/ap/policies/policy-summary.tsx`
- Create: `frontend/src/app/ai/policies/page.test.tsx`
- Replace: `frontend/src/app/ai/policies/page.tsx`

- [x] **Step 1: Write failing page tests for live rendering and states**

Mock only the typed policy helpers. Test initial loading with an unresolved promise, live rendering of API-supplied key/description/value/unit/type/severity/active/version/update metadata, truthful empty and initial-error states, retry, text search, and the All/Block/Escalate/Advise filters. Assert the route does not render `Create with AI`, `Structured Builder`, `Permission Matrix`, `Expense Approval Policy`, or `Data Access Control`.

- [x] **Step 2: Run page tests and verify RED**

Run:

```powershell
npm.cmd run test:run -- src/app/ai/policies/page.test.tsx --reporter=dot
```

Expected: assertions fail against the existing demonstration page.

- [x] **Step 3: Implement the console shell and focused list components**

Replace the page with a client component that owns authoritative `items`, `total`, `snapshot_label`, loading/error/success state, search, and severity filter state. Use the approved information hierarchy: AP governance header and refresh, four summary cells, search/filter controls, and accessible policy articles. Keep the project's navy/cornflower visual language, data-first typography, keyboard focus, and reduced-motion behavior. Do not import or mutate the old generic AI policy components.

- [x] **Step 4: Run page tests and verify GREEN**

Run the Step 2 command.

Expected: loading, live, empty, error, filtering, and removal assertions pass.

### Task 5: Add type-specific editing and authoritative refetch

**Files:**
- Create: `frontend/src/components/ap/policies/policy-edit-dialog.tsx`
- Modify: `frontend/src/app/ai/policies/page.test.tsx`
- Modify: `frontend/src/app/ai/policies/page.tsx`

- [x] **Step 1: Write failing interaction tests**

Test that number policies use `input[type=number]`, enum policies use only server options, boolean policies use the existing switch, and date policies use `input[type=date]`. Test optional note submission, local validation that prevents PATCH, disabled saving state, server validation error while the dialog remains open, success feedback, and a second `getAPPolicies()` call after PATCH before displaying refreshed data.

- [x] **Step 2: Run the focused page tests and verify RED**

Run the Task 4 Step 2 command.

Expected: edit-control and mutation tests fail because editing is not implemented.

- [x] **Step 3: Implement the edit dialog and mutation flow**

Render immutable metadata plus the correct control from `policy.value_type`. Convert number input text only after pure validation; pass booleans and enum/date strings without coercion. Trim the optional note in the helper payload. Disable duplicate submission, keep the dialog open on failure, close after successful PATCH, then await an authoritative list refetch and expose a concise success status.

- [x] **Step 4: Run the focused page tests and verify GREEN**

Run the Task 4 Step 2 command.

Expected: all editing, validation, PATCH, and refetch tests pass.

### Task 6: Add append-only history with isolated error handling

**Files:**
- Create: `frontend/src/components/ap/policies/policy-history-dialog.tsx`
- Modify: `frontend/src/app/ai/policies/page.test.tsx`
- Modify: `frontend/src/app/ai/policies/page.tsx`

- [x] **Step 1: Write failing history tests**

Test on-demand loading, newest-first rendered entries, previous/new values, actor, timestamp, optional note, an empty-history message, isolated history failure, retry, and history refresh after a successful edit of the currently selected policy.

- [x] **Step 2: Run the focused page tests and verify RED**

Run the Task 4 Step 2 command.

Expected: history assertions fail because no history component exists.

- [x] **Step 3: Implement the history dialog**

Load `getAPPolicyHistory(policy.key)` only when opened. Keep history loading/error state separate from list state, render the server's entry order without client-side invention, format values through `formatPolicyValue`, and provide retry. Clear stale history when the selected key changes and refresh open history after an update.

- [x] **Step 4: Run focused frontend tests and verify GREEN**

Run:

```powershell
npm.cmd run test:run -- src/lib/ap-policies.test.ts src/app/ai/policies/page.test.tsx --reporter=dot
```

Expected: all AP Policies frontend tests pass.

### Task 7: Update mandatory project documentation

**Files:**
- Modify: `PROJECT_REQUIREMENTS.md`
- Modify: `ARCHITECTURE_AND_CODING_DESIGN.md`
- Modify: `PROJECT_STATUS.md`

- [x] **Step 1: Update requirements**

Add an `AP Policies Console Requirements` section covering authenticated list/update/history, metadata-driven validation, no-op semantics, actor/note history, authoritative refetch, explicit UI states, and create/delete non-goals.

- [x] **Step 2: Update architecture and coding design**

Document the three endpoints, schema/router/service responsibilities, validation and transaction boundaries, authorization rule, frontend file boundaries, no-migration decision, and backend/frontend test strategy.

- [x] **Step 3: Update project status with evidence, not predictions**

Record completed AP Policies work and only the verification commands that actually pass. Preserve the explicit limitation that the complete backend suite is not claimed when no real PostgreSQL `DATABASE_URL` is configured. Update the date to `2026-08-07` and keep unrelated Workbench/Data Manager status intact.

### Task 8: Run final verification and review the diff

**Files:**
- Verify: all changed files

- [x] **Step 1: Run focused backend policy tests**

Run the engine and API commands from Tasks 1 and 2. Expected: zero failures.

- [x] **Step 2: Check complete-backend-suite availability**

If `DATABASE_URL` is non-empty and points at the dedicated test database, run:

```powershell
& 'C:\Users\User\Documents\AP-Control-Tower-Round2\.worktrees\ap-workbench\.venv\Scripts\python.exe' -m pytest -q
```

Otherwise record the suite as blocked by missing configuration, not passed. Verified 2026-08-07: no real `DATABASE_URL` was configured, so this command was not run and is not claimed as passing.

- [x] **Step 3: Run focused and complete frontend tests**

Run:

```powershell
Set-Location frontend
npm.cmd run test:run -- src/lib/ap-policies.test.ts src/app/ai/policies/page.test.tsx --reporter=dot
npm.cmd run test:run -- --reporter=dot
```

Expected: zero failed files and zero failed tests.

- [x] **Step 4: Run strict TypeScript and the production build sequentially**

Run:

```powershell
npx.cmd tsc --noEmit
npm.cmd run build
```

Expected: both commands exit 0.

- [x] **Step 5: Run repository hygiene checks**

From the worktree root run:

```powershell
git diff --check
rg -n --hidden -g '!frontend/node_modules/**' -g '!frontend/.next/**' -g '!docs/superpowers/specs/**' -g '!docs/superpowers/plans/**' "Create with AI|Structured Builder|Permission Matrix|Expense Approval Policy|Data Access Control|api[_-]?key\s*[:=]|client[_-]?secret\s*[:=]|password\s*[:=]" app frontend/src PROJECT_REQUIREMENTS.md ARCHITECTURE_AND_CODING_DESIGN.md PROJECT_STATUS.md
git status --short
git diff --stat
git diff
```

Expected: no whitespace errors; no generic demo policy content or credential assignments in the implemented route/files; only AP Policies and mandatory documentation changes appear in the final diff.
