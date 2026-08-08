# Supervity Auto — defects found by running 53 live invoices

**From:** Ku · **To:** Lim · **Date:** 8 Aug 2026
**Source of evidence:** 53 real Orchestrator runs (`AP Control Tower`,
`019fdb5f-a085-7000-ba58-acedb3f006dd`) executed through the Command Center backend
between 05:20 and 06:40 on 8 Aug, every decision persisted to `ap_decisions`.

Nothing here is theoretical. Every claim below names the invoice that proves it and
the query that reproduces it.

Ordered by scoring impact, not by effort.

---

## Summary

| # | Defect | Where | Impact |
|---|---|---|---|
| 1 | `fo_aware` GR policy ignored | Three Way Match | **Touchless 22.5% instead of ~50%** — Business Output is 30 pts |
| 2 | Reason-code vocabulary drift | All Operators | **Duplicate holds and GR policy silently disabled** — Policies is 20 pts |
| 3 | Non-PO invoices return `DATA_ERROR` | Intake / Entity | Operator 5 looks broken; 15 invoices affected |
| 4 | `PO Entity Resolver` breaks the §B1 contract | PO Entity Resolver | Cannot ever FAIL; gate compliance |
| 5 | Null keys stripped from `canonical_invoice` | Between steps | Downstream Operators receive a variable-shaped object |

Current measured state for reference: **52 invoices · 21.2% touchless ·
MYR 4,650,648.90 protected · 41 open exceptions.**

---

## Defect 1 — `gr_policy: "fo_aware"` is not being honoured

**Severity: highest.** This single defect is suppressing the headline business metric.

### What happens

Invoices on **framework purchase orders** (`EKKO.BSART = 'FO'`) are being flagged
`RECEIPT_VARIANCE` and routed to a human, even though the active policy exempts them
from goods-receipt matching.

### Evidence

Three framework orders that were flagged anyway:

| Invoice | PO | `BSART` | GR rows | GR qty | PO qty | Verdict |
|---|---|---|---|---|---|---|
| `5110000020` | 46200052 | **FO** | 0 | 0 | 420 | HUMAN_REVIEW · `RECEIPT_VARIANCE` |
| `5110000034` | 46200032 | **FO** | 0 | 0 | 312 | HUMAN_REVIEW · `RECEIPT_VARIANCE` |
| `5110000035` | 46200004 | **FO** | 2 | 249 | 702 | HUMAN_REVIEW · `RECEIPT_VARIANCE` |

Reproduce:

```sql
select i.belnr, h.bsart,
       (select coalesce(sum(g.menge),0) from goods_receipts g
         where btrim(g.ebeln)=btrim(i.ebeln)) gr_qty,
       (select coalesce(sum(p.menge),0) from po_items p
         where btrim(p.ebeln)=btrim(i.ebeln)) po_qty
from ap_invoices i join po_headers h on btrim(h.ebeln)=btrim(i.ebeln)
where i.belnr in ('5110000020','5110000034','5110000035');
```

### Why it matters

**164 of 450 invoices (36%) are on FO orders.** Round 1 measured 40.8% touchless
under `strict_require_gr` and 52.6% under `fo_aware`. We are currently at **22.5%**,
below even the strict figure — so the exemption is not being applied at all.

`RECEIPT_VARIANCE` is the single most common exception in the whole run (17 of 53).

### Expected behaviour

In **`AP - Three Way Match`**, before evaluating goods receipts, read
`policy_snapshot.gr_policy`:

- `gr_policy == "fo_aware"` **and** `EKKO.BSART == 'FO'`
  → skip goods-receipt matching entirely
  → emit reason code **`GR_EXEMPT_FRAMEWORK`**
  → this contributes `status: "PASS"`, not `REVIEW`

- `gr_policy == "fo_aware"` and `BSART != 'FO'` → normal GR matching
- `gr_policy == "strict_require_gr"` → normal GR matching for **every** order,
  framework or not

`GR_EXEMPT_FRAMEWORK` must be emitted even though it is not an error. The Command
Center's policy engine uses it to prove the policy is live: switching to
`strict_require_gr` withdraws the exemption and escalates the same invoice. Without
that code the 20-point "change a policy, see different behaviour" demo cannot run.

### Verification

Run `5110000020`. Expect `PAY_READY` with `GR_EXEMPT_FRAMEWORK` in `reason_codes`.
Then set `GR-POLICY` to `strict_require_gr` in the Command Center and re-run the
same invoice — expect `HUMAN_REVIEW`.

---

## Defect 2 — reason-code vocabulary drift

**Severity: high.** Two controls are silently switched off by this.

The Operators emit codes the Command Center policy engine has never heard of, and the
engine expects codes the Operators never emit. Unrecognised codes do not error — they
are simply carried through and ignored, so a control appears to work while doing
nothing.

### Codes Auto emits that the engine does not recognise

| Code | Count | Consequence |
|---|---|---|
| `RECEIPT_VARIANCE` | 17 | **`GR-POLICY` never fires.** Engine expects `RECEIPT_MISSING` / `RECEIPT_PARTIAL`. |
| `NEAR_DUP_SUSPECT` | 2 | **Near-duplicates never trigger `PAYMENT_HOLD`.** Engine expects `DUP_LATER_COPY`. Money not counted as protected. |
| `GL_CODING_REQUIRED` | 4 | Unmapped (harmless, informational) |
| `MISSING_INPUT` | 4 | Unmapped, and drives Defect 3 |
| `VENDOR_MASTER_DUPLICATE` | 4 | Unmapped (genuinely new — good find by the Operator) |
| `CREDIT_MEMO` | 3 | Not a hold code; these held only coincidentally via `PO_LINE_NO_MATCH` |
| `DATE_AMBIGUOUS` | 2 | Unmapped (informational) |

### Codes the engine expects that Auto never emits

`GR_EXEMPT_FRAMEWORK` · `RECEIPT_MISSING` · `RECEIPT_PARTIAL` · `DUP_LATER_COPY` ·
`VENDOR_DELETED` · `BANK_CHANGE_UNVERIFIED` · `PO_LINE_AMBIGUOUS` · `DOA_BAND_NOT_FOUND`

### The two that actually cost us

**a. Goods receipt.** `RECEIPT_VARIANCE` collapses two different situations into one
word. Please split it:

- **`RECEIPT_MISSING`** — no goods receipt exists at all
- **`RECEIPT_PARTIAL`** — a receipt exists but received qty < invoiced/ordered qty
- **`GR_EXEMPT_FRAMEWORK`** — exempted under `fo_aware` (see Defect 1)

The distinction is real: partial receipt protects only the unsupported portion,
missing receipt holds the lot.

**b. Duplicates.** `NEAR_DUP_SUSPECT` is not treated as a payment hold, so
`5110000158` / `5110000159` (`INV273650` vs `INV27365O`) both came back
`HUMAN_REVIEW`. A duplicate that would cause a second payment should **hold**.
Please emit **`DUP_LATER_COPY`** on the copy that arrived later, keeping
`NEAR_DUP_SUSPECT` only for a genuine "these look similar, a human should judge"
case.

### Who fixes what

To avoid duplicated work: **Ku is adding aliases on the Command Center side** so the
engine also accepts `RECEIPT_VARIANCE`, `NEAR_DUP_SUSPECT`, `CREDIT_MEMO`,
`VENDOR_MASTER_DUPLICATE` and `DATE_AMBIGUOUS`. That makes the system work whatever
you do.

**Lim still needs to emit `GR_EXEMPT_FRAMEWORK`** — no alias can invent it, because it
carries information nothing else provides (that a framework exemption was applied).
The `RECEIPT_MISSING` / `RECEIPT_PARTIAL` split is desirable but not blocking.

---

## Defect 3 — every non-PO invoice returns `DATA_ERROR`

### What happens

All four non-PO invoices in the run returned `MISSING_INPUT` and were graded
`DATA_ERROR` — the worst possible verdict, and the one that says "we could not
evaluate this safely".

| Invoice | Amount | `bukrs_on_inv` | `gl_code` | `confidence` | Verdict |
|---|---|---|---|---|---|
| `5110000007` | `330,252.07` MYR | null | null | null | DATA_ERROR |
| `5110000011` | 626,630.55 MYR | null | null | 0.95 | DATA_ERROR |
| `5110000022` | 67,922.68 MYR | null | null | 0.83 | DATA_ERROR |
| `5110000033` | 330,252.07 MYR | null | null | 0.83 | DATA_ERROR |

Reason codes returned: `["MISSING_INPUT", "GL_CODING_REQUIRED", "NON_PO_APPROVAL"]`

### Why it is wrong

A non-PO invoice **has no purchase order and no GL code by definition** — that is
precisely why the Non-PO Coding & Approval Operator exists: propose a GL account,
resolve a DOA approver, route to a human. The Operator did most of its job
(`GL_CODING_REQUIRED` and `NON_PO_APPROVAL` are both present), but `MISSING_INPUT`
escalates the verdict to `DATA_ERROR`, which outranks `HUMAN_REVIEW` in precedence.

The trigger appears to be `bukrs_on_inv` being null. That is normal for these rows and
should not be fatal — the `DEFAULT-KOSTL` policy (`CC100`) exists exactly to supply a
fallback cost centre when the invoice does not carry one.

### Expected behaviour

For an invoice where `ebeln` is null:

1. Do **not** emit `MISSING_INPUT` for a null `bukrs_on_inv` or null `gl_code`
2. Fall back to `policy_snapshot.default_kostl` for the cost centre
3. Propose a GL account and a DOA approver
4. Return `status: "REVIEW"` with `["NON_PO_APPROVAL", "GL_CODING_REQUIRED"]`
5. Resulting verdict should be **`HUMAN_REVIEW`**, not `DATA_ERROR`

Reserve `MISSING_INPUT` for genuinely unusable input — no vendor, no amount, no
invoice number. **Never invent a value**; the fallback here is an explicit policy
value, not a guess.

### Scale

15 of 450 invoices are non-PO. All are currently `DATA_ERROR`.

---

## Defect 4 — `AP - PO Entity Resolver` breaks the §B1 contract

### What happens

Its `Return Result` step returns:

```json
{ "status": "SUCCESS", ... }
```

with only **5 of the 8** required keys.

### Why it is wrong

`status` is a closed set: **`PASS` | `FAIL` | `REVIEW` | `NOT_APPLICABLE` | `ERROR`**.
`SUCCESS` is not a member.

The Command Center computes protected value from Operators whose status is `FAIL`.
A status of `SUCCESS` is not `FAIL`, so this Operator **can never hold a payment or
contribute protected value**, whatever it finds. Today that is harmless because it
only resolves entities — but it is a live gate-compliance issue and a judge reading
the audit trail will see a non-conforming Operator.

### Expected

All eight keys, every time:

```json
{
  "operator_name": "AP - PO Entity Resolver",
  "status": "PASS",
  "reason_codes": [],
  "explanation": "Resolved company code MY20 from PO 46200048.",
  "evidence": { "ebeln": "46200048", "bukrs": "MY20" },
  "retryable": false,
  "protected_value_candidate": 0,
  "protected_value_currency": "MYR"
}
```

Every other Operator already conforms — this is the only one.

---

## Defect 5 — null-valued keys are dropped from `canonical_invoice`

### What happens

`canonical_invoice` is specified as exactly **24 keys**. When a value is null, the key
disappears entirely rather than being carried as null, so downstream Operators receive
an object of varying shape.

Observed missing when null: `bank_on_inv`, `gl_code`, `confidence`,
`bukrs_on_inv`.

### Observed consequence

`5110000021` and `5110000031` both returned `LOW_CONFIDENCE` while
`canonical_invoice.confidence` arrived as null. The Command Center therefore stored a
decision with no confidence value, and the `MIN-CONFIDENCE` policy has no number to
test against — it has to fall back to trusting the Operator's flag, so **lowering or
raising that threshold cannot change those invoices**.

```sql
select belnr, verdict, confidence, reason_codes
from ap_decisions where belnr in ('5110000021','5110000031');
-- confidence is NULL despite LOW_CONFIDENCE being raised
```

### Expected

Emit all 24 keys always, with explicit `null` where there is no value. A missing key
and a null value must not be interchangeable — downstream code cannot distinguish
"not applicable" from "absent".

---

## Please also confirm (not yet verified either way)

`policy_snapshot` is passed into every Operator. We have confirmed `gr_policy` is
**not** being read (Defect 1). Please confirm each of these is actually read and used,
because if any are ignored the corresponding policy is decoration:

| Snapshot key | Should be used by | Confirmed? |
|---|---|---|
| `price_tolerance_pct` | Three Way Match — line match window | ❓ |
| `min_confidence` | Intake — confidence check | ❓ |
| `bank_change_freeze_days` | Bank Change Verification | ❓ |
| `high_value_threshold` | Bank Change Verification — 4th fraud signal | ❓ |
| `near_dup_amount_tolerance_pct` | Duplicate Screen | ❓ |
| `default_kostl` | Entity and Approval — fallback cost centre | ❓ |
| `retro_po_policy` | handled in the Command Center gate — no action needed | n/a |
| `as_of_date` | ageing / freeze-window arithmetic | ❓ |

A one-line answer per row is enough.

---

## Verification checklist

Run these through the Command Center after the fixes and compare:

| Invoice | Expected after fix | Tests |
|---|---|---|
| `5110000020` | `PAY_READY` + `GR_EXEMPT_FRAMEWORK` | Defect 1 |
| `5110000034` | `PAY_READY` + `GR_EXEMPT_FRAMEWORK` | Defect 1 |
| `5110000011` | `HUMAN_REVIEW` + `NON_PO_APPROVAL`, `GL_CODING_REQUIRED` | Defect 3 |
| `5110000022` | `HUMAN_REVIEW`, proposed GL + approver | Defect 3 |
| `5110000159` | `PAYMENT_HOLD` + `DUP_LATER_COPY` | Defect 2b |
| `5110000021` | `confidence` present in `canonical_invoice` | Defect 5 |
| `5110000002` | `PAY_READY`, unchanged | regression |
| `5110000150` | `PAYMENT_HOLD`, MYR 1,234,293.69 protected | regression |
| `5110000164` | `PAYMENT_HOLD`, `VENDOR_BLOCKED` + `ENTITY_MISMATCH` | regression |

The last three must not change. If they do, something regressed.

**Expected headline movement:** touchless from **22.5%** to roughly **45–55%**, driven
almost entirely by Defect 1.

---

## Notes

- Do not hardcode any invoice, vendor or PO id into an Operator. Judges will run rows
  we have not prepared. Every id above is for testing only.
- Never invent a value for a missing field — pause and escalate. The `default_kostl`
  fallback in Defect 3 is an explicit policy value, not an invention.
- The API host is `auto-workflow-api.supervity.ai`. `auto.supervity.ai` is the web
  app and returns a generic 400 to every API call with or without a valid key.
