# Handoff — Ku → Lim, 7 Aug 2026

Lim, I'm unavailable from here. This is everything: what works, what's broken, what's
left, and the traps that cost me most of today so you don't pay for them twice.

**Freeze: 8 Aug 23:59. Finale: 9 Aug.**

Read §1 and §7 first. §7 is the important one — the Auto builder behaves in ways that
will waste hours if you don't know them going in.

---

## 1. Where we are — the five mandatory items

| # | Mandatory item | State | What's missing |
|---|---|---|---|
| 1 | Orchestrator + ≥5 Operators on Auto, parallel/branching | **done** | publish it |
| 2 | Command Center wired via backend API, live activity | **endpoint written, never run** | `.env` credentials + one real run |
| 3 | ≥3 policies editable no-code, evaluated before action, logged | **engine done, UI not built** | the Policies page |
| 4 | ≥1 real exception in the Workbench, resolved there | **plumbing done** | one real run |
| 5 | ≥3 live integrations healthy in Data Manager | **2 of 3** | Outlook |

Nothing here is a rebuild. Item 3 is the only genuinely unbuilt thing.

**Important finding about item 4:** the Workbench is a **Template** component, not a
Supervity feature. The problem statement's "WHAT RUNS WHERE" table (page 2) lists
Command Center, AI Policies, AI Insights, AI Manager, Data Manager and **Workbench**
all under "Template". So item 4 means *your* Workbench page, which is already built.
Do **not** spend time connecting Auto's own Workbench integration — I went down that
road and it's a dead end that buys nothing.

---

## 2. The Auto layer — what exists

### The Orchestrator

**Name: `AP Control Tower`** — not `AP Control Tower Orchestrator`. That older one is
broken beyond repair (hardcoded fake invoices in its input mappings). Ignore it; don't
delete it yet in case we need to look at something.

Eight steps:

```
                    ┌─ Duplicate Screen ────┐
                    ├─ Bank Screen ─────────┤
Start → Intake ─────┼─ PO Resolver → Entity Approval ─┼──→ Decide Verdict → Send Slack Alert
                    └─ Three Way Match ─────┘
                        (only when is_po)
```

Workflow-level outputs:

```
canonical_invoice, intake_status, intake_result, duplicate_result,
po_entity_result, match_result, entity_result, bank_result,
verdict, reason_codes
```

### Operators and helpers

| Artifact | State | Notes |
|---|---|---|
| AP - Intake and Normalize | **works** | 24-field canonical_invoice, verified against real rows |
| AP - Duplicate and Fraud Screen | **works** | scans full vendor population (11 for vendor 4110000) |
| AP - Three Way Match | **works** | verified: matched 943,523.28 to PO line 30 within 2%, GR found |
| AP - PO Entity Resolver | **works, v13** | input is `canonical_invoice` (JSON), native Supabase connector |
| AP - Bank Change Verification | **partial** | see §4.2 |
| AP - Entity and Approval Control | **broken** | see §4.1 — **do not open its chat** |

### The selector syntax (this took three hours to find)

Reference a previous step's output as:

```
step_<step_name_lowercased_with_underscores>.<output_name>
```

Working example on every Operator input:

```
canonical_invoice = step_intake.canonical_invoice
```

**Whole objects map fine. Single fields pulled out of an object into a Text input do
not.** I tried three times to map `canonical_invoice.ebeln` into the resolver's old
`ebeln` Text input and it resolved to nothing every time. That's why the resolver was
rebuilt to take the whole `canonical_invoice` and read `ebeln` internally. If you hit
the same wall on any new step, change the Operator's interface rather than fighting
the mapping.

### The verdict expression, as saved

```
(step_duplicate_screen.duplicate_result.status == "FAIL" || step_bank_screen.bank_result.status == "FAIL"
 || step_three_way_match.match_result.status == "FAIL" || step_entity_approval.entity_result.status == "FAIL"
 || step_intake.intake_result.status == "FAIL") ? "PAYMENT_HOLD"
: (... same five, == "ERROR") ? "DATA_ERROR"
: (... same five, == "REVIEW") ? "HUMAN_REVIEW"
: "PAY_READY"
```

Correct precedence, no `"SUCCESS"` comparisons, `NOT_APPLICABLE` correctly neutral.

**Untested branch:** the `step_intake.intake_result.*` references. Every test invoice
so far passes Intake, so those five conditions have never actually fired. If you want
to verify, run a low-confidence invoice (see §6) — Intake should return REVIEW and the
verdict should come out HUMAN_REVIEW. If it comes out PAY_READY, the `intake_result`
reference isn't resolving and needs to point at the Intake step's status the same way
`step_intake.canonical_invoice` resolves.

---

## 3. The Command Center — what I added today

### `POST /api/ap/runs` — the seam between Auto and the Command Center

New files:

- `app/routers/ap_runs.py`
- `app/schemas/ap_runs.py`
- registered in `app/main.py` (line ~155) and `app/routers/__init__.py`

Three routes:

```
POST /api/ap/runs           run the Orchestrator for one invoice
GET  /api/ap/runs           list recent runs
GET  /api/ap/runs/{run_id}  one run with events, decision, policy evaluations
```

What one POST does, in order:

1. `build_snapshot(db)` — captures active policies **before** anything runs
2. calls the Auto Orchestrator with `{invoice_ref, policy_snapshot, run_id}`
3. streams each SSE frame into `ap_run_events` as it arrives (item 2's live activity)
4. `evaluate()` gates the proposed verdict **before** any action (item 3)
5. `record_evaluations()` writes one `ap_policy_evaluations` row per policy, fired or not
6. writes the immutable `ap_decisions` row with `source="auto_run"`
7. opens an `ap_workbench_items` row when the gate requires a human (item 4 → your UI)

Two deliberate design points:

- **Money is computed here, not in Auto.** Protected value is the single largest
  candidate among Operators that returned FAIL — never the sum. Smoke-tested: three
  Operators each flagging 230,681.50 yields 230,681.50, not 692,044.50. `HUMAN_REVIEW`
  yields 0 protected and the invoice amount as `spend_under_review`.
- **An empty result is a failure.** If the Orchestrator returns no result frame, the
  run is marked failed and nothing is written. No invented verdict, ever.

### Status of it

It imports cleanly and the routes appear in the OpenAPI schema. **It has never run
against a live database or a live Auto call.** The part most likely to need adjustment
is parsing Auto's terminal SSE frame — its shape isn't documented, so `_find()` searches
for keys anywhere in the payload rather than assuming a path. If the first run returns
a 502 saying "produced no result", that's the parser, and the fix is to look at the raw
`ap_run_events.payload` of the last frame and adjust.

There are **no tests for this router yet.** If you have time, `tests/test_ap_runs.py`
following the pattern in `tests/test_ap_workbench.py` would be worth it.

---

## 4. Known defects

### 4.1 `AP - Entity and Approval Control` — DO NOT OPEN ITS CHAT

This is the one that needs the most care.

**Symptom:** returns `status: ERROR`, `reason_codes: ["MISSING_INPUT"]` on every run,
which makes the Orchestrator produce `DATA_ERROR` instead of `PAY_READY`.

**Cause:** it calls `AP - PO Entity Resolver` internally, pinned to an old version (v8)
that expects a Text input named `ebeln`. That internal call receives nothing and errors,
and the error propagates out. Confirmed twice in the audit — on the 23:09 run, v11 ran
at 11:09:10 and returned `bukrs: MY20`, then v8 ran at 11:09:25 with an empty input and
failed, and Entity Approval started at 11:09:26. The second call is inside Entity, not
the Orchestrator.

**Why you must not open its chat:** its published version is fine (4 inputs, 14 outputs)
and that's what the Orchestrator runs. But its **draft** is clobbered — when I opened it
it reported 2 inputs, `Purchase Order (EBELN)` and `SUPABASE_URL`, and 2 outputs. That's
leftover damage from when a resolver rebuild command was pasted into its tab. **If you
save or publish from that chat, you replace the working Operator with the broken draft
and the Orchestrator loses it.**

**If you want to fix it** — and it's worth ~real points, because it's the difference
between a PAY_READY demo and a DATA_ERROR demo — the only safe route I can see is:

1. Confirm first, without saving anything: ask its chat to report name, inputs, output
   count. If it says 4 inputs / 14 outputs you're on the good version. If it says 2
   inputs / SUPABASE_URL, back out immediately.
2. If you're on the good version, the change is: remove the internal subworkflow call to
   `AP - PO Entity Resolver` entirely, and read `bukrs` from the `po_entity_context`
   input instead (the Orchestrator already passes it correctly). If `po_entity_context`
   is missing or its `bukrs` is null, skip the entity check neutrally — do not return
   ERROR.
3. Publish, then re-run `5110000002`. Expect PAY_READY.

If it regresses, stop. DATA_ERROR still routes to the Workbench, which is a legitimate
demo: *"the agent found something it couldn't resolve safely and escalated it with full
evidence rather than inventing a value."* That's literally what the brief asks for.

### 4.2 `AP - Bank Change Verification` — no result on the no-bank path

When an invoice has no bank details, the Operator correctly decides no comparison is
needed — and then just stops. Its audit ends at `Condition: Bank Comparison Not Required
→ True` with no terminal card, so it never emits the 8-key contract object. Result:
`bank_result: null` in the verdict step.

Doesn't change any verdict (null isn't FAIL/ERROR/REVIEW), so it's cosmetic. The fix is
a terminal "Return Result" card that fires on **all** branches, like Entity Approval's
CARD 6 does. Low priority.

### 4.3 Platform flakiness — don't debug this

The same workflow, run twice with no changes, sometimes shows `No output data generated`
on a step that worked the run before. It moves around between runs — Bank Screen one
time, Duplicate Screen the next. **Re-run before investigating.** I lost time treating
this as a real bug more than once.

---

## 5. What to do, in priority order

### Tonight / first thing (≈30 min) — unblocks everything

1. ~~Run the Slack test.~~ **Done, 7 Aug 23:10.** `Send Slack Alert` fired:
   `status: ALERT_SENT` to the configured channel, carrying invoice 5110000002, vendor
   4110000, verdict DATA_ERROR, reason MISSING_INPUT. Channel integration is proven and
   your Data Manager should now have its Slack `integration_activity` evidence.
   - **Untested:** the bank-account masking path. That invoice has no bank details, so
     Slack printed "Not Provided". To prove `****9571` masking before the demo, run
     `5110000332` — same vendor, carries a real account number.

2. **Publish `AP Control Tower`** and copy its workflow id from the URL.

3. **Create `.env`** (copy from `.env.example`) with:
   ```
   SUPERVITY_API_KEY=<generate at auto.supervity.ai/u/api-keys>
   SUPERVITY_ACTIVE_ORG=<our org key>
   SUPERVITY_ORCHESTRATOR_WORKFLOW_ID=<from step 2>
   ```
   Never commit these, never paste them into any doc.

4. **First real run:**
   ```powershell
   .\scripts\start.ps1
   docker compose exec backend alembic upgrade head
   curl.exe -X POST http://localhost:8000/api/ap/runs -H "Content-Type: application/json" -d '{\"invoice_ref\":\"5110000002\"}'
   ```
   A 201 with a verdict and a `workbench_item_id` means Auto → backend → decision →
   human queue all works. **That single response closes mandatory items 2 and 4.**
   Then open `http://localhost:3001/workbench`, find the item, resolve it with a note.

### Next (the only unbuilt thing) — the Policies page

`frontend/src/app/ai/policies/page.tsx` is still the template's demo content — it
contains the words `demo` and `placeholder` and makes no API calls. Mandatory item 3
says policies must be *editable without code*, and the brief's DON'Ts explicitly name
*"policy or insight pages that only show the template's static demo data"*. A judge
clicking that page today sees exactly the failure mode the brief calls out.

What's needed:

- A `GET /api/ap/policies` + `PATCH /api/ap/policies/{key}` router. The engine already
  exists — `app/services/policies.py` has `update_policy()` with version history and
  validation against `options`. It just has no HTTP surface. `ap_workbench.py` is a good
  pattern to copy.
- Replace the page with a table of the 10 seeded policies rendering the right control
  per `value_type` (number / enum / boolean / date), plus each policy's `version`.
- The demo moment: change `GR-POLICY` from `fo_aware` to `strict_require_gr`, re-run the
  same invoice, show the verdict change. That's item 3 proven live in ten seconds.

The 10 seeded policies are in `alembic/versions/d4e5f6a7b8c9_*.py`:
`PRICE-TOLERANCE` 2 · `BANK-CHANGE-FREEZE` 30 · `DOA-BAND` 5000 · `GR-POLICY` fo_aware ·
`RETRO-PO` advisory · `MIN-CONFIDENCE` 0.70 · `AS-OF-DATE` 2026-07-15 ·
`HIGH-VALUE-THRESHOLD` 500000 · `NEAR-DUP-TOLERANCE` 0.1 · `DEFAULT-KOSTL` CC100

### After that, if time

- Dashboard tiles reading real `ap_decisions` (touchless rate, money protected)
- Outlook as the second channel for item 5
- AI Insights (15 points, but scoring not gating)
- The Entity fix in §4.1

### Cut without regret

AI Manager (~4 points). The money/policy-gate/formal-output steps in the Orchestrator —
the endpoint does that work now.

---

## 6. Test data

**Policy snapshot** (paste into any Auto run panel):

```json
{
  "policy_version": "v1.1.1.1.1.1.1.1.1.1",
  "as_of_date": "2026-07-15",
  "price_tolerance_pct": 2.0,
  "gr_policy": "fo_aware",
  "bank_change_freeze_days": 30,
  "high_value_threshold": 500000.0,
  "min_confidence": 0.7,
  "auto_pay_limit": 5000.0,
  "near_dup_amount_tolerance_pct": 0.1,
  "default_kostl": "CC100",
  "retro_po_policy": "advisory"
}
```

**Invoices worth knowing** (all verified against the seeded Supabase pack):

| Invoice | What it is | Expected |
|---|---|---|
| `5110000002` | clean PO invoice, vendor 4110000, MYR 943,523.28, PO 46200048 line 30 exact match, fully received, MY20 both sides | PAY_READY once Entity is fixed; DATA_ERROR today |
| `5110000371` / `5110000372` | identical pair — same vendor, same ref `INV889013`, same amount, same channel | exact duplicate, PAYMENT_HOLD |
| `5110000164` / `5110000165` / `5110000166` | invoice entity ≠ PO entity (MY20/TH50, MY20/IN40, MY10/MY20) | ENTITY_MISMATCH, PAYMENT_HOLD |
| `5110000007` | non-PO — exercises the GL coding + DOA path, skips Three Way Match | HUMAN_REVIEW |
| `5110000009` | SGD — exercises FX conversion in the Entity Operator | — |

Other counts from the data profile: 52 comma-decimal amounts, 44 `DD/MM/YYYY` + 44
`Mon DD YYYY` dates (15 genuinely ambiguous), 12 invoices below the 0.70 confidence
floor, 27 with null confidence, 64 `fo_aware` exemption candidates, 3 near-duplicate
pairs (5110000158/159, 160/161, 162/163).

Supabase: the Round 2 project (ref is in the shared credentials, not recorded here).
All 14 tables seeded — 450 invoices, 80
vendors, 153 PO headers, 276 PO items, 135 goods receipts, 894 FX rates.

---

## 7. Lessons about the Auto builder — read this before touching Auto

These cost me most of 7 Aug. Every one is from direct evidence.

**1. Read the Execution Logs, never the chat summary.** The summary contradicted the
actual JSON roughly a dozen times — claiming "all steps processed including Three Way
Match" when that step had been skipped, reporting `doa_rows_scanned: 5` when the log
said `0`, inventing `line_netwr` values. Treat the chat as marketing copy.

**2. Adding steps works. Editing steps breaks things.** Every additive command
("add exactly ONE new step") landed first time. Almost every edit command ("change this
one mapping") silently damaged something else. When something needs changing, consider
deleting and re-adding rather than editing.

**3. It fabricates data into input mappings.** Told to wire step A's output into step
B, it will often paste a plausible JSON literal instead:
`{"invoice_number":"INV-12345","vendor_name":"Test Vendor","amount":1000}`. It looks
like it works. It isn't. **After any mapping change, open the subworkflow audit and
check the input block shows the real invoice number.** This is also a
disqualification risk — the brief's DON'Ts name "hardcode to these rows" explicitly.

**4. Version numbers in the Orchestrator chat are not published versions.** It reported
the resolver as "version 5" while the resolver's own chat said latest published was 2.
Different counters. Only trust the Operator's own chat, and even then the timestamps
are fabricated (it reported "2024-05-15" for a project that didn't exist then).

**5. Native connectors only.** If any step asks for `SUPABASE_URL`, `SLACK_CHANNEL_ID`,
an API key, a bearer token, `/rest/v1`, or a generic HTTP action — the build is wrong.
Rebuilding the resolver silently swapped its native Supabase connector for an
environment-variable lookup and it took a run to notice.

**6. The orange "Connect" badge on an Operator card can be a lie.** Two Operators showed
it while working perfectly against live data. Test the Operator rather than trusting the
badge.

**7. Use a fresh `run_id` for every run.** Auto doesn't care, but `ap_runs.run_id` is
unique in the backend — reusing one makes `POST /api/ap/runs` return 409.

**8. Keep commands small.** A 250-line command with a 16-point review checklist made the
builder loop forever — twelve subworkflow re-selections, never saving. Small, single-
purpose commands with a fixed 3-4 line reply format land reliably.

---

## 8. Answering "which core path did we choose"

The brief says *"Round 1 covered the core path"* and then offers six optional business
functions, each naturally its own Operator, explicitly noting you need not build all.

We chose **two of the six**:

- **Vendor onboarding and bank verification** → `AP - Bank Change Verification`
- **FX and intercompany allocation** → `AP - Entity and Approval Control` (converts to
  MYR via `fx_rates`, books to the correct legal entity)

Not built: payment run / discount capture (became an Insight), vendor statement
reconciliation, dispute and credit memo handling, month-end accrual and close.

Our five Operators map almost one-to-one onto the brief's own example diagram — Extract
& Classify, Duplicate & Fraud Screen, Three-Way Match, Bank-Change Verification, GL
Coding — and the brief calls that diagram "one example, not a required design". Worth
saying out loud in the demo.

---

## 9. Pre-submission checklist

- [ ] `AP Control Tower` published
- [ ] Slack alert fired with real data at least once
- [ ] One real `POST /api/ap/runs` completed, `ap_decisions` row exists with
      `source = "auto_run"`
- [ ] `SELECT count(*) FROM ap_decisions WHERE source = 'oracle_backfill'` returns **0** —
      shipping computed demo data as agent output is disqualifying
- [ ] One Workbench item resolved, with the separate `human_action` audit event
- [ ] Policies page edits a real policy and the change alters a re-run
- [ ] No `SUPABASE_URL` / API key / webhook anywhere in an Auto workflow
- [ ] No invoice number, vendor, PO, company code or amount hardcoded in any workflow
- [ ] `.env` not committed; clean clone still builds
- [ ] Data Manager shows Supabase + Slack + one more, all healthy

---

Sorry to hand this over mid-flight. The hard part — five Operators running in parallel
on live data with nothing fabricated — is done and proven. What's left is wiring and one
page.

— Ku
