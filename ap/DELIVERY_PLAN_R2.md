# AP Control Tower — Round 2 delivery plan + Auto build commands

**Team:** Lim (Member A) · Ku (Member B)
**Freeze:** 8 Aug 23:59 · **Finale:** 9 Aug, 10–12 min live showcase

This is the only file we need. **Part A** is the plan. **Part B** is the exact text to paste into
Supervity Auto.

---
---

# PART A — THE PLAN

## 0. Status — what is already finished

The Supervity token allowance ran out until 3 Aug, so the last two days went into everything that
does **not** need Auto. All of the below is done, tested, and in the repo.

| ✅ Done | Where | Notes |
|---|---|---|
| **Supabase schema + import CSVs** | `round2/supabase/` | 14 tables, indexes on every join key. `belnr` verified unique. |
| **450-invoice oracle** | `round2/oracle/` | independent answer key; mirrors all five Operator specs |
| **Data trap census** | `round2/analysis/DATA_PROFILE_R2.md` | every trap counted, with sample IDs |
| **DB models (9 tables)** | `app/models/ap.py` | runs, events, decisions, policies, evaluations, workbench, insights, integrations |
| **Alembic migration + seeds** | `alembic/versions/d4e5f6a7b8c9_*.py` | seeds 10 policies + 4 integration rows |
| **Supervity Auto client** | `app/services/supervity.py` | multipart execute, SSE parser, 55/min limiter, health check |
| **AI Policies engine** | `app/services/policies.py` | snapshot → gate-before-action → evaluation logging |
| **Tests** | `tests/test_ap_policies.py`, `tests/test_ap_supervity.py` | **31 passing** |
| **Setup guide** | `docs/AP_SETUP.md` | step-by-step, including the Supabase import order |

**Oracle results on the public pack** — our business-output baseline:

| GR policy | Touchless | PAY_READY / REVIEW / HOLD |
|---|---|---|
| `strict_require_gr` | 27.8% | 125 / 213 / 112 |
| `fo_aware` | **40.2%** | 181 / 157 / 112 |

Money protected **MYR 40.07M** + SGD 3.98M + INR 3.23M + EUR 1.63M + USD 1.63M.
Fraud: **4 invoices held across 3 spoofed bank-change attempts, 0 false positives** against
7 legitimate bank changes.

### Four bugs found during review, all fixed

1. **The Auto client was sending the wrong content type.** httpx only encodes
   `multipart/form-data` when `files` is truthy; `files={}` degrades to
   `application/x-www-form-urlencoded`, which Auto rejects with a 4xx. Verified empirically, fixed,
   regression test added.
2. **The auto-pay policy would have destroyed touchless rate.** It applied the DOA band to *every*
   invoice, and almost nothing in the pack is under MYR 5,000. Corrected: a clean three-way match
   **is** the authorization, so the DOA band applies only to non-PO spend.
3. **Three policies were read by the engine but never seeded** (`HIGH-VALUE-THRESHOLD`,
   `NEAR-DUP-TOLERANCE`, `DEFAULT-KOSTL`) — they would have silently used hardcoded defaults,
   breaking "all thresholds live in the policy store". Now seeded.
4. **`KONP` cannot be joined to a PO line.** No `knumh` on `po_items`, no `matnr`/`ebeln` on
   `pricing_conditions`. The expired-contract-price check is **not buildable** per invoice — it is
   an Insight instead. Do not spend time on it.

Design change: retroactive / out-of-validity POs were forcing 57 invoices to human review. That is a
process-control note, not a payment risk, so it is now a **policy toggle** (`RETRO-PO`:
`advisory` / `review`). Recovers ~12 points of touchless and gives us a second live knob.

---

## 1. The budget

We each have roughly **2 hours per evening** (both on internship), plus the on-site day on 8 Aug.
Lim is especially tight next week, so the split below puts the longer-running and harder items on
Ku, and gives Lim work that is self-contained and blocks nothing.

The original plan was a 120–200 person-hour build. It has been cut to fit. Two things make the rest
workable: Auto work is mostly *waiting* (describe, let it build, test — that parallelises across
browser tabs), and the specs, SQL, seed data and oracle are already written.

### Decision: the Auto layer is rebuilt from scratch

Round 1's Operators were unreliable and the PO match had been rolled back to header-only. Part B has
clean prompts for all six workflows. We keep the Supabase connection method, the reason codes and
the demo story — no old workgraphs.

---

## 2. Scope — five Operators

| # | Operator | Owner |
|---|---|---|
| 1 | AP · Intake & Normalize | **Ku** |
| 2 | AP · Duplicate & Fraud Screen | **Ku** |
| 3 | AP · Three-Way Match | **Ku** ← hardest, built from nothing |
| 4 | AP · Bank Change Verification | **Lim** |
| 5 | AP · Entity & Approval Control | **Lim** |
| — | AP Control Tower Orchestrator | **Ku** |

### Cut, with where the capability goes instead

| Cut | Where it goes |
|---|---|
| Discount Optimizer as an Operator | backend **Insight** — keeps the "cash optimized" story |
| Split-invoice detection as an Operator check | an **Insight** — it is a pattern across invoices |
| Expired contract price check | an **Insight** — not joinable per invoice |
| FX / intercompany allocation depth | convert for display with one as-of rate |
| Self-learning · 4th integration · real auth · statement recon · credit-memo handling · month-end accrual | dropped |
| AI Manager beyond thin grounded Q&A | 4 points of 100 — last item, drop without regret |

**If behind, cut in this order:** AI Manager → 3rd Insight → Operator 5 (fold the entity check into
Operator 3) → dashboard tiles beyond the four headline ones.
**Never cut:** anything in the gate checklist in §6.

---

## 3. Ownership

| | **Ku** | **Lim** |
|---|---|---|
| **Auto** | Operators 1, 2, 3 · **Orchestrator** | Operators 4, 5 |
| **Command Center** | Supervity wiring · run/event persistence · decisions · **Policies engine + UI** · Dashboard · **Insights** | **Data Manager** page + health checks · **Workbench** UI + resolution |
| **Data** | Supabase seeding · oracle validation | — |

---

## 4. Day-0 handoffs — everything is blocked on these

### Lim → Ku, as soon as the token allowance returns on 3 Aug

- [ ] **Invite Ku to the team Auto workspace.** Ku lost his session. Without this Ku cannot build
      Operators 1–3 or the Orchestrator and the whole split collapses onto Lim.
- [ ] **Workflow API key** — generate at `auto.supervity.ai/u/api-keys`. Send privately, never in the repo.
- [ ] **The `x-active-org` value** for our workspace.
- [ ] **The Orchestrator workflow ID**, once it exists.
- [ ] **One sample run output** (paste the JSON from a successful run) so the SSE parser can be tightened.

### Ku → Lim

- [x] ~~Seed the 14 Round 2 tables into Supabase~~ — schema + CSVs ready in `round2/supabase/`;
      the import itself takes ~20 minutes and happens before 3 Aug.
- [ ] Confirmed table and column names sent to Lim.

> **Auto lesson from Round 1:** use the **native Supabase OAuth "Query table" action**. Hand-rolled
> `SUPABASE_TOKEN` / `httpx` / `/rest/v1` queries did not work. If a native connector fails,
> time-box to 15 minutes, then raise it — do not grind.

---

## 5. Verified API facts

Checked against Supervity's live documentation and encoded in `app/services/supervity.py`:

- `POST /api/v1/workflow-runs/execute/stream` — exists, SSE: activity, status, AI reasoning traces,
  result, error.
- Headers: `Authorization: Bearer <key>` · `x-source: external` · `x-active-org: <org key>`
- ⚠️ **Body is `multipart/form-data`, not JSON.** Fields: `workflowId`, `inputs`, `envs`.
- ⚠️ **60 requests/minute per IP.** The client limits to 55/min. Do not bypass it.
- Also: `GET /api/v1/workflow-runs` · `GET /api/v1/workflow-runs/:runId` · `POST /api/v1/workflow-runs/cancel`

---

## 6. Day by day

### 1–2 Aug · before the token returns

| Ku | Lim |
|---|---|
| ✅ backend models, migration, Auto client, Policies engine, tests | Read Part B §B1 (contract) and §B6–B7 (his two Operators) |
| Import the 14 tables into Supabase | Confirm Auto workspace access and that Ku can be invited |
| `docker compose up` + `alembic upgrade head` green | |

**Both: freeze the shared contract (Part B §B1) before 3 Aug.** Five Operators built in parallel
only works if the interface is fixed first.

### 3 Aug · skeleton + first Operators — banks gate condition 2

| Ku | Lim |
|---|---|
| `POST /api/ap/runs` — snapshot → Auto → persist run + events → gate → decision | Build **Operator 4 · Bank Change Verification** |
| SSE passthrough; **one dashboard tile moves on a real run** | |
| Parallel tab: **Operator 1 · Normalize** | |

### 4 Aug · Operators + human loop — banks gate condition 4

| Ku | Lim |
|---|---|
| Start **Operator 3 · Three-Way Match** (the long pole) | **Workbench** UI + resolve endpoint |
| Parallel tab: **Operator 2 · Duplicate & Fraud Screen** | |

### 5 Aug · Policies — banks gate condition 3

| Ku | Lim |
|---|---|
| Finish Operator 3; Policies CRUD + UI (editable with no code) | Build **Operator 5 · Entity & Approval Control** |

### 6 Aug · close the gate — banks gate conditions 1 and 5

| Ku | Lim |
|---|---|
| **Orchestrator**: fan-out, fan-in, PO/non-PO branch, retry once | **Data Manager** page + live health checks |

**End of 6 Aug: all five gate conditions green. Nothing new is added after this point.**

### 7 Aug · score

| Ku | Lim |
|---|---|
| **Insights** — 3 computed: bank-change fraud anomalies · near-duplicate clusters · discount at risk | Regression-run all five Operators |
| Dashboard tiles | Audit every prompt for sample-specific logic — **there must be none** |

### 8 Aug · on-site, freeze 23:59

Batch-run the pack (respect 60/min) and **diff against `EXPECTED_ORACLE_R2.csv`** · purge every
`oracle_backfill` decision row · **clean-clone test** · rehearse the demo twice out loud ·
AI Manager only if everything above is green.

---

## 7. Gate checklist — all five, or the build is not scored

| # | Condition | Owner | Green by |
|---|---|---|---|
| 1 | Orchestrator + **≥5 distinct Operators** on Auto, parallel / branching / stateful | Ku | 6 Aug |
| 2 | Command Center wired via the backend API, showing **live** activity, not demo data | Ku | 3 Aug |
| 3 | **≥3 active policies**, editable with no code, applied **before** the agent acts, every evaluation logged | Ku | 5 Aug |
| 4 | **≥1 real exception** routed to the Workbench with full context and **resolved there** | Lim | 4 Aug |
| 5 | **≥3 live integrations**, 2 categories (Outlook channel · Supabase system of record · Slack), **healthy in the Data Manager** | Lim | 6 Aug |

Ten policies are already seeded, named to match the dataset's own `Approval_Log.POLICY_REF`
vocabulary: `PRICE-TOLERANCE`, `BANK-CHANGE-FREEZE`, `DOA-BAND`, `GR-POLICY`, `RETRO-PO`,
`MIN-CONFIDENCE`, `AS-OF-DATE`, `HIGH-VALUE-THRESHOLD`, `NEAR-DUP-TOLERANCE`, `DEFAULT-KOSTL`.

**The live policy demo:** flip `GR-POLICY` and touchless moves **27.8% → 40.2%**.

---

## 8. Two traps that would otherwise kill the demo

**The discount window is nearly closed.** Most invoices are Apr–Jul 2026 and `DISC_DAYS` is 15–20.
As of 9 Aug, **one** invoice is still inside its window. Every date-relative calculation reads the
`AS-OF-DATE` policy (seeded at 2026-07-15), never today's real date. Defensible because it is a
visible, editable policy — and it is another knob a judge can turn.

**FX rates stop on 27 Jul 2026.** Anything later — including a row a judge submits live on the 9th —
has no rate. Use nearest-prior-date fallback and record which rate date was applied.

---

## 9. Demo — 8 beats, ~9 minutes

1. Invoice **`5110000152`** (Summit Steelworks, MYR 1,234,293.69) → **Bank Change Verification**
   freezes it. Four signals: lookalike sender `accounts@summit-billing.com` vs master
   `ap@summit.com` · SPF/DKIM/DMARC all fail · new account added by `EXTERNAL` via `EMAIL` · the
   bank change dated **the same day as the invoice**. Then show that vendor's three other invoices
   clearing untouched. Say it out loud: **3 attempts, 4 invoices held, 0 false positives against
   7 legitimate bank changes.**
2. The Orchestrator fanning out to five Operators, live.
3. Command Center updates from that run — tiles move.
4. Judge edits `GR-POLICY` in the UI, re-run: **27.8% → 40.2% touchless**, evaluation logged.
5. An Insight and its action path.
6. Resolve the exception in the Workbench; the initial AI verdict stays immutable.
7. Data Manager — three integrations, healthy.
8. Audit trail for the whole decision.

---

## 10. Standing rules

- **Never hardcode to sample rows.** Judges may run a record we did not prepare. Sample IDs are
  runtime test inputs only and must never appear in a prompt, condition or mapping.
- **All thresholds live in the policy store**, never in Operator prose or code.
- **Never invent a value for a missing field** — pause and route to the Workbench.
- **`ap_decisions.source` must be `auto_run` before submission.** Rows backfilled from the oracle
  for development are marked `oracle_backfill` and must be purged.
- **Never commit the dataset or the API key.** The build must run from a clean clone.

---
---

# PART B — SUPERVITY AUTO BUILD COMMANDS

## How to use Part B

1. Build each Operator as **its own separate workflow**. Use the exact name given.
2. For each Operator: paste **§B1 (the contract)** first, press enter, wait for Auto to acknowledge,
   then paste that Operator's command.
3. Auto builds a workgraph of cards. Each command below names the cards explicitly. **After Auto
   finishes, check the workgraph against the "REJECT THE BUILD IF" list at the end of that command.**
   If anything on that list is true, paste the fix instruction and rebuild that card only.
4. Test each Operator on its own with the runtime inputs in §B8 before wiring anything together.
5. Build the **Orchestrator last**, only once all five Operators pass on their own.
6. Ku and Lim build in parallel tabs. That works only if **§B1 is frozen before 3 Aug**.

### Why these commands are written this way

Auto generates a workflow from a description. Vague descriptions produce cards that quietly invent
values, skip branches, or query the wrong table. So every command below states: the exact card name,
the exact action type, the exact table, the exact filter, the exact row limit, what to do for zero
rows and for many rows, and the exact output field names. Do not shorten them.

---

## §B1 · The shared contract — paste this FIRST, every time

```text
CONTEXT. Read all of this before building anything. This is the shared contract for every
AP Control Tower Operator. Do not deviate from it.

=== WHERE THE DATA LIVES ===
All business data is in Supabase, schema "public". You must read it using the NATIVE
Supabase OAuth "Query table" action.

You must NOT use, request, read, generate or reference any of the following:
  SUPABASE_TOKEN, SUPABASE_URL, an API key, a bearer token, /rest/v1, a generic HTTP
  action, Python code, httpx, requests, curl, or a custom script.
If you cannot complete a step with the native Supabase "Query table" action, stop and say
so. Do not substitute any other method.

=== TABLES AND COLUMNS ===
ap_invoices        belnr, gjahr, xblnr, lifnr, ebeln, bldat, budat, waers, wrbtr, mwskz,
                   source_channel, bank_on_inv, gl_code, status, submit_ts, confidence,
                   gst_amt, bukrs_on_inv, po_waers
vendor_master      lifnr, name1, bankn, waers, zterm, sperr, loevm, land1, last_bank_chg, email
po_headers         ebeln, bukrs, bsart, lifnr, waers, zterm, aedat, kdatb, kdate, netwr
po_items           ebeln, ebelp, txz01, matnr, menge, meins, netpr, netwr, uebto, untto
goods_receipts     mblnr, ebeln, ebelp, bwart, budat, menge, shkzg
gl_master          saknr, txt50, kostl_allowed
doa_matrix         role, approver, email, min_amt, max_amt, kostl
company_codes      bukrs, butxt, land1, waers
fx_rates           gdatu, fcurr, tcurr, ukurs
bank_master        lifnr, bank_seq, bankn, valid_from, valid_to, is_current, change_source, changed_by
email_headers      email_id, belnr, lifnr, from_addr, subject, recv_ts, spf, dkim, dmarc, msg_type
discount_schedule  lifnr, zterm, disc_pct, disc_days, net_days
approval_log       log_id, belnr, wrbtr, role, approver, action, decision_ts, policy_ref

IMPORTANT: the column "wrbtr" in ap_invoices is TEXT, not a number. The column "bldat" is
TEXT, not a date. They contain deliberately messy values. You must parse them yourself
using the rules given in each command. Do not assume the database has cleaned them.

=== THE policy_snapshot INPUT ===
Every Operator receives an input named policy_snapshot. It is a JSON object with these
fields. You must read thresholds from it. You must NEVER write a number directly into a
condition. If you find yourself typing a number into a comparison, you are doing it wrong.

  policy_version                 text    e.g. "v1.1.1"
  as_of_date                     date    the operational "today". NEVER use the real
                                         current date anywhere. Always use this field.
  price_tolerance_pct            number  e.g. 2
  gr_policy                      text    "strict_require_gr" or "fo_aware"
  bank_change_freeze_days        number  e.g. 30
  high_value_threshold           number  e.g. 500000
  min_confidence                 number  e.g. 0.70
  auto_pay_limit                 number  e.g. 5000
  near_dup_amount_tolerance_pct  number  e.g. 0.1
  default_kostl                  text    e.g. "CC100"
  retro_po_policy                text    "advisory" or "review"

=== THE OUTPUT EVERY OPERATOR MUST RETURN ===
Return exactly one JSON object with exactly these keys. Do not add keys. Do not rename keys.

{
  "operator_name": "<this Operator's exact name>",
  "status": "PASS" | "FAIL" | "REVIEW" | "NOT_APPLICABLE" | "ERROR",
  "reason_codes": ["CODE_ONE", "CODE_TWO"],
  "explanation": "one plain sentence a finance person would understand",
  "evidence": { "field_compared": "value", "...": "..." },
  "retryable": true | false,
  "protected_value_candidate": <number, 0 if none>,
  "protected_value_currency": "<the invoice currency>"
}

What each status means:
  PASS            the check passed, no concern
  FAIL            a hard risk. The Orchestrator will hold the payment.
  REVIEW          a human must look at it, but it is not a hard block
  NOT_APPLICABLE  this check does not apply to this invoice at all
  ERROR           a connector or data failure. Set "retryable" to true.

reason_codes must be an array of strings, even when there is only one, even when empty.
protected_value_candidate must be a number, never a string, never null. Use 0 when there
is nothing to protect.

=== FIVE ABSOLUTE RULES ===
1. NEVER invent, guess, default or substitute a value for a missing field. If a required
   value is missing, return REVIEW (or ERROR for a connector failure) and say in
   "explanation" exactly what was missing.
2. NEVER write a specific invoice number, vendor number, PO number or company code into a
   prompt, a condition, a filter value, or a mapping. Every such value must come from an
   input variable at runtime. Judges will test records we did not prepare.
3. NEVER use today's real date. Always use policy_snapshot.as_of_date.
4. Every Supabase query must have an explicit filter AND an explicit row limit.
5. Put every value you actually compared into "evidence", so a human can verify the decision
   without opening the database.

Acknowledge that you have read this contract. Do not build anything yet.
```

---

## §B2 · Operator 1 — `AP - Intake and Normalize` · owner: Ku

```text
Build a new Supervity Auto Operator workflow. Name it exactly:  AP - Intake and Normalize

WHAT THIS OPERATOR IS FOR
It turns one raw invoice row into a clean, canonical record that every other Operator will
use. It makes NO business judgement. It only reads, parses, normalizes and classifies.

DEFINE THESE INPUTS
  invoice_ref      text  required  the belnr of the invoice to process
  policy_snapshot  JSON  required  see the contract
  run_id           text  required  correlation id, pass through to the output

BUILD THESE CARDS, IN THIS EXACT ORDER

CARD 1 — name it "Query Invoice Row"
  Action: native Supabase "Query table"
  Schema: public
  Table:  ap_invoices
  Filter: belnr equals the input invoice_ref
  Limit:  2
  Branch on the number of rows returned:
    0 rows      -> go to CARD 9 with status ERROR, reason_codes ["INVOICE_NOT_FOUND"],
                   retryable false
    2 rows      -> go to CARD 9 with status ERROR, reason_codes ["AMBIGUOUS_SOURCE_ROW"],
                   retryable false
    exactly 1   -> continue to CARD 2

CARD 2 — name it "Normalize Identifiers"
  No external action. Pure text handling on the row from CARD 1.
  For each of lifnr, xblnr and ebeln:
    remove leading and trailing spaces, then convert to UPPERCASE.
  If ebeln is empty, or contains only spaces, treat it as ABSENT (null), not as "".
  Output: lifnr_clean, xblnr_clean, ebeln_clean, is_po (true when ebeln_clean is present).

CARD 3 — name it "Parse Amount"
  No external action. The source column wrbtr is TEXT and is deliberately messy.
  Apply these rules IN THIS ORDER and stop at the first one that matches:

    Rule A: the text contains BOTH a comma and a dot.
            The comma is a thousands separator, the dot is the decimal point.
            Remove every comma. Example: "330,252.07"  ->  330252.07
    Rule B: the text is digits, then exactly one comma, then exactly two digits.
            The comma IS the decimal point. Replace it with a dot.
            Example: "327845,70"  ->  327845.70
    Rule C: anything else. Remove every comma as a thousands separator.
            Example: "1,234"  ->  1234        Example: "9305.97"  ->  9305.97

  A leading minus sign means a credit memo. KEEP the value negative, do not drop the sign.
  Example: "-326571.29"  ->  -326571.29
  If after all three rules the text still cannot be read as a number, go to CARD 9 with
  status FAIL and reason_codes ["AMOUNT_UNPARSEABLE"].
  Output: amount (a number), amount_raw (the original text, for evidence).

CARD 4 — name it "Parse Dates"
  No external action. Parse bldat and budat. Both are TEXT and use MIXED formats.
  Accept exactly these three formats:
    Format 1: "YYYY-MM-DD" or "YYYY-MM-DD HH:MM:SS"    example "2026-06-07 00:00:00"
    Format 2: "Mon DD YYYY"                             example "Apr 29 2026"
    Format 3: "DD/MM/YYYY"  — this is DAY FIRST         example "19/04/2026" = 19 April 2026

  For Format 3 ONLY, apply this test:
    - if the FIRST number is greater than 12, it must be the day. Accept it as day-first.
      Example: "19/04/2026" -> 19 April 2026.  "22/06/2026" -> 22 June 2026.
    - if the FIRST number is 12 or less AND the SECOND number is 12 or less, the date is
      genuinely ambiguous. It could be day/month or month/day and there is no way to know.
      DO NOT GUESS. DO NOT PICK ONE. Add reason_code "DATE_AMBIGUOUS" and set status REVIEW.
      Example: "09/06/2026" is ambiguous. "02/07/2026" is ambiguous.
  If the field is empty, add reason_code "DATE_MISSING" and set status REVIEW.
  Output: bldat_parsed, budat_parsed, date_format_detected (put this in evidence).

CARD 5 — name it "Check Extraction Confidence"
  No external action.
  Read the confidence column. It is a number between 0 and 1, and it may be empty.
  If confidence is present AND confidence is less than policy_snapshot.min_confidence:
    add reason_code "LOW_CONFIDENCE" and set status REVIEW.
  If confidence is empty, do not add a code and do not guess a value.

CARD 6 — name it "Check Credit Memo"
  No external action.
  If amount from CARD 3 is less than zero:
    add reason_code "CREDIT_MEMO" and set status REVIEW.
  A credit memo must never clear automatically.

CARD 7 — name it "Build Matching Keys"
  No external action. Build these two strings EXACTLY as described. Other Operators rebuild
  them the same way, so any difference breaks duplicate detection.

  duplicate_fingerprint =
      lifnr_clean + "|" + xblnr_clean + "|" + UPPERCASE(waers) + "|" +
      amount rounded to exactly 2 decimal places
    Example: "4110017|INV889740|MYR|134257.5"

  near_duplicate_key =
      lifnr_clean + "|" + X
    where X is built from the ORIGINAL xblnr by:
      step 1: remove every character that is not a letter or a digit
      step 2: convert to UPPERCASE
      step 3: replace every letter O with the digit 0
    Example: xblnr "INV27365O " -> "INV273650",  so X = "INV273650"
    Example: xblnr "INV273650"  -> "INV273650",  so X = "INV273650"
    (These two must produce the SAME key. That is the whole point.)

CARD 8 — name it "Assemble Canonical Invoice"
  No external action. Build an object named canonical_invoice with exactly these fields:
    belnr, gjahr, xblnr (cleaned), lifnr (cleaned), ebeln (cleaned or null), is_po,
    bldat_parsed, budat_parsed, waers, amount, amount_raw, is_credit_memo, mwskz,
    source_channel, bank_on_inv, gl_code, submit_ts, confidence, gst_amt, bukrs_on_inv,
    po_waers, duplicate_fingerprint, near_duplicate_key, run_id

CARD 9 — name it "Return Result"
  Return the standard output object from the contract, PLUS the canonical_invoice object.
  operator_name is "AP - Intake and Normalize".
  protected_value_candidate is ALWAYS 0 for this Operator — it makes no money decisions.
  Set status PASS only if no card above set FAIL or REVIEW.

REJECT THE BUILD IF any of these are true, and fix that card:
  - any card references SUPABASE_TOKEN, /rest/v1, httpx, requests, or a generic HTTP action
  - CARD 1 has no row limit, or filters on anything other than the invoice_ref input
  - CARD 3 turns "327845,70" into 32784570 or 327845 (the comma rule is backwards)
  - CARD 4 picks a date for "09/06/2026" instead of flagging DATE_AMBIGUOUS
  - CARD 4 uses today's real date anywhere
  - CARD 5 substitutes a default confidence when the column is empty
  - CARD 7 lowercases anything, or forgets the O-to-zero replacement
  - any specific invoice number appears anywhere in the workflow
```

---

## §B3 · Operator 2 — `AP - Duplicate and Fraud Screen` · owner: Ku

```text
Build a new Supervity Auto Operator workflow. Name it exactly:  AP - Duplicate and Fraud Screen

WHAT THIS OPERATOR IS FOR
Decide whether this invoice is the original or a later copy of one we have already seen, and
detect near-duplicates that differ only by OCR noise, rounding, or arriving on a different
channel. Fraudsters resubmit the same invoice through a second channel hoping it gets paid twice.

DEFINE THESE INPUTS
  canonical_invoice  JSON  required  the output of AP - Intake and Normalize
  policy_snapshot    JSON  required
  run_id             text  required

BUILD THESE CARDS, IN THIS EXACT ORDER

CARD 1 — name it "Query Vendor Invoice Population"
  Action: native Supabase "Query table"
  Schema: public
  Table:  ap_invoices
  Filter: lifnr equals canonical_invoice.lifnr
  Limit:  200
  This is the comparison population. Compare against ALL of it, not only invoices from the
  current run. If the query fails, return status ERROR, reason ["CONNECTOR_ERROR"],
  retryable true.

CARD 2 — name it "Rebuild Fingerprints For Population"
  No external action.
  For EVERY row returned by CARD 1, rebuild duplicate_fingerprint using EXACTLY the same
  rules Operator 1 used:
    - parse wrbtr with the same three amount rules (comma-and-dot, comma-decimal, plain)
    - trim and uppercase lifnr and xblnr
    - round the amount to 2 decimal places
    - join as: lifnr + "|" + xblnr + "|" + UPPERCASE(waers) + "|" + amount
  If you use different rules here than Operator 1 used, duplicate detection will silently fail.

CARD 3 — name it "Detect Exact Duplicate"
  No external action.
  Collect every row whose rebuilt fingerprint equals canonical_invoice.duplicate_fingerprint.
  Branch:
    exactly 1 match (this invoice only) -> no finding, continue to CARD 4
    2 or more matches -> choose the PRIMARY as follows:
         first, the row with the EARLIEST parseable bldat
         if two rows tie on date, the row with the LOWEST belnr
       Then:
         if the primary IS this invoice           -> no finding, continue to CARD 4
         if the primary is a DIFFERENT invoice    -> this one is a later copy:
              status FAIL
              reason_codes ["DUP_LATER_COPY"]
              protected_value_candidate = the absolute invoice amount
              evidence must include: primary_belnr, this_belnr, both source_channel values,
              and the shared fingerprint

CARD 4 — name it "Detect Near Duplicate"
  No external action.
  For EVERY row from CARD 1, build near_duplicate_key using EXACTLY Operator 1's rules
  (strip non-alphanumerics from xblnr, uppercase, replace letter O with digit 0).
  Find rows where BOTH of these are true:
    (a) the row's near_duplicate_key EQUALS canonical_invoice.near_duplicate_key
    (b) the row's duplicate_fingerprint is DIFFERENT from this invoice's
  For each such row, compare the two amounts:
    let bigger = the larger of the two absolute amounts
    if  absolute(amount_a - amount_b)  is less than or equal to
        bigger * policy_snapshot.near_dup_amount_tolerance_pct / 100
    then:
       status REVIEW
       reason_codes ["NEAR_DUP_SUSPECT"]
       protected_value_candidate = the absolute invoice amount
       evidence must include: the other belnr, BOTH raw xblnr values exactly as stored,
       both amounts, and both source_channel values.
       In "explanation", if the two source_channel values are different, say so explicitly.
       A near-duplicate arriving on a different channel is the strongest signal.

  Worked example of what this must catch:
    invoice A: xblnr "INV273650",  amount 33353.94, channel EMAIL
    invoice B: xblnr "INV27365O ", amount 33354.00, channel DRIVE
    Both normalize to key "...|INV273650". Amounts differ by 0.06, which is well within
    0.1% of 33354. This IS a near duplicate and must be flagged.

CARD 5 — name it "Return Result"
  Return the standard contract output. operator_name is "AP - Duplicate and Fraud Screen".
  If neither CARD 3 nor CARD 4 fired, status is PASS and protected_value_candidate is 0.
  evidence must always include population_size_checked, so a human can see the comparison
  was real and not skipped.

REJECT THE BUILD IF:
  - CARD 1 filters by run, batch, or date instead of by vendor, or has no limit
  - CARD 2 parses amounts differently from Operator 1
  - CARD 3 picks the primary by highest belnr, or by the order rows came back
  - CARD 4 compares raw xblnr instead of the normalized key
  - the tolerance in CARD 4 is a typed-in number instead of coming from policy_snapshot
  - evidence omits the source_channel values
```

---

## §B4 · Operator 3 — `AP - Three Way Match` · owner: Ku

```text
Build a new Supervity Auto Operator workflow. Name it exactly:  AP - Three Way Match

WHAT THIS OPERATOR IS FOR
For an invoice that cites a purchase order, check three things agree: the invoice, the
purchase order, and the goods receipt.

THE SINGLE MOST IMPORTANT RULE IN THIS ENTIRE BUILD
The invoice carries only the PO HEADER number. It does not say which PO line it is for.
You must match the invoice amount against an individual PO LINE value (po_items.netwr).
You must NOT compare the invoice amount to the PO header total (po_headers.netwr).
On our data, comparing to the header total wrongly flags 77% of invoices as price variances.
Matching against a line resolves 93% of invoices to exactly one line.
If you find yourself comparing the invoice amount to po_headers.netwr, you have made the
worst possible mistake in this workflow.

DEFINE THESE INPUTS
  canonical_invoice  JSON  required
  policy_snapshot    JSON  required
  run_id             text  required

BUILD THESE CARDS, IN THIS EXACT ORDER

CARD 1 — name it "Check PO Number Present"
  No external action.
  If canonical_invoice.ebeln is absent or empty:
    return immediately with status NOT_APPLICABLE, reason_codes [],
    protected_value_candidate 0. Do not run any query. Stop here.
  Otherwise continue to CARD 2.

CARD 2 — name it "Query PO Header"
  Action: native Supabase "Query table"
  Schema: public
  Table:  po_headers
  Filter: ebeln equals canonical_invoice.ebeln
  Limit:  2
  Branch:
    0 rows -> status REVIEW, reason_codes ["PO_NOT_FOUND"],
              protected_value_candidate = absolute invoice amount.
              explanation: the invoice cites a purchase order that does not exist.
              Stop here.
    2 rows -> status ERROR, reason_codes ["CONNECTOR_ERROR"], retryable true. Stop here.
    1 row  -> continue to CARD 3.

CARD 3 — name it "Compare Vendor"
  No external action.
  If canonical_invoice.lifnr is NOT equal to the PO header lifnr:
    status FAIL
    reason_codes ["PO_VENDOR_MISMATCH"]
    protected_value_candidate = absolute invoice amount
    evidence: invoice_lifnr and po_lifnr, both values
    Stop here. Someone is billing us against another company's purchase order.

CARD 4 — name it "Compare Currency"
  No external action.
  The PO HEADER currency is authoritative.
  If canonical_invoice.waers is NOT equal to the PO header waers:
    status FAIL
    reason_codes ["PO_CURRENCY_MISMATCH"]
    protected_value_candidate = absolute invoice amount
    evidence: invoice_currency and po_currency
    Stop here.
  Do NOT compare against vendor_master.waers. The vendor master currency is advisory only
  and comparing against it produces a large number of false positives.

CARD 5 — name it "Check PO Dates"
  No external action. These are warnings about process, not payment risks.
  Compare using policy_snapshot.as_of_date logic, never today's real date.
    if canonical_invoice.bldat_parsed is EARLIER than the PO header aedat
       -> add reason_code "RETRO_PO"        (the invoice predates the purchase order)
    if canonical_invoice.bldat_parsed is EARLIER than the PO header kdatb
       -> add reason_code "PO_OUT_OF_VALIDITY"
  Then check policy_snapshot.retro_po_policy:
    if it is "review"    -> set status REVIEW
    if it is "advisory"  -> record the reason codes but DO NOT change the status
  Continue to CARD 6 either way.

CARD 6 — name it "Query PO Lines"
  Action: native Supabase "Query table"
  Schema: public
  Table:  po_items
  Filter: ebeln equals canonical_invoice.ebeln
  Limit:  50
  Return all lines for this purchase order.

CARD 7 — name it "Match Invoice To A PO Line"
  No external action.
  Let tol = policy_snapshot.price_tolerance_pct.
  A PO line is a CANDIDATE when:
      absolute( canonical_invoice.amount  -  line.netwr )
      is less than or equal to  line.netwr * tol / 100
  Count the candidates and branch:

    exactly 1 candidate -> that is the matched line. Remember its ebelp, netwr, menge and
                           untto. Continue to CARD 8.

    0 candidates        -> this is a real price variance.
                           status FAIL
                           reason_codes ["PO_LINE_NO_MATCH"]
                           Find the line whose netwr is CLOSEST to the invoice amount.
                           protected_value_candidate =
                               invoice amount  -  ( closest_line_netwr * (1 + tol/100) )
                           If that result is negative, use 0 instead.
                           evidence: closest ebelp, closest netwr, tolerance applied.
                           Stop here.

    2 or more candidates -> we cannot tell which line this invoice is for.
                           status REVIEW
                           reason_codes ["PO_LINE_AMBIGUOUS"]
                           protected_value_candidate = 0
                           evidence: the ebelp of every candidate line.
                           NEVER silently pick the nearest one. Stop here.

CARD 8 — name it "Query Goods Receipts For The Matched Line"
  Action: native Supabase "Query table"
  Schema: public
  Table:  goods_receipts
  Filter: ebeln equals canonical_invoice.ebeln AND ebelp equals the matched line's ebelp
  Limit:  50
  Query the matched line ONLY, not the whole purchase order.

CARD 9 — name it "Reconcile Received Quantity"
  No external action. Compute a SIGNED received quantity from the rows in CARD 8:
      start at 0
      for each row: if bwart is "101"                       -> ADD menge
                    if bwart is "102", or shkzg is "H"      -> SUBTRACT menge
  Let ordered   = the matched line's menge
  Let under_tol = the matched line's untto        (a percentage, may be 0 or empty; empty means 0)
  Let required  = ordered * (1 - under_tol/100)

  Branch on the received quantity:

    received >= required        -> the receipt is complete. No code. Continue to CARD 10.

    received > 0 but < required -> status REVIEW
                                   reason_codes ["RECEIPT_PARTIAL"]
                                   protected_value_candidate =
                                       absolute invoice amount * (ordered - received) / ordered
                                   evidence: ordered, received, required.

    received <= 0               -> nothing has been received at all. Now read
                                   policy_snapshot.gr_policy:

         if gr_policy is "strict_require_gr":
              status REVIEW
              reason_codes ["RECEIPT_MISSING"]
              protected_value_candidate = 0
              (Nothing is protected here. We are holding spend for review, not stopping a
               bad payment. Do not put the invoice amount here.)

         if gr_policy is "fo_aware":
              look at the PO header bsart from CARD 2.
              if bsart equals "FO", this is a framework order and is exempt from goods
                 receipt. Add reason_code "GR_EXEMPT_FRAMEWORK" and DO NOT change the status.
              if bsart is anything else:
                 status REVIEW, reason_codes ["RECEIPT_MISSING"],
                 protected_value_candidate = 0

CARD 10 — name it "Return Result"
  Return the standard contract output. operator_name is "AP - Three Way Match".
  If no card set FAIL or REVIEW, status is PASS and protected_value_candidate is 0.
  evidence MUST include: matched_ebelp, line_netwr, tolerance_pct_applied, ordered_qty,
  received_qty, gr_policy_used, bsart. A judge will ask how the match was made.

DO NOT BUILD THIS — IT IS IMPOSSIBLE WITH OUR DATA
Do not try to check whether a pricing condition has expired. The pricing_conditions table
cannot be joined to a purchase order or a PO line: po_items has no knumh column, and
pricing_conditions has no matnr and no ebeln column. There is no key connecting them.
Expired conditions are reported separately in the Command Center, not here.

REJECT THE BUILD IF:
  - any card compares the invoice amount to po_headers.netwr  (the single worst error)
  - CARD 7 auto-selects the nearest line when several are within tolerance
  - CARD 8 queries goods receipts for the whole PO instead of the matched line
  - CARD 9 treats bwart 102 as an addition, or ignores shkzg
  - CARD 9 sets protected_value_candidate to the invoice amount for RECEIPT_MISSING
  - the tolerance or the gr_policy is typed in rather than read from policy_snapshot
  - any card queries pricing_conditions
```

---

## §B5 · Operator 4 — `AP - Bank Change Verification` · owner: Lim

```text
Build a new Supervity Auto Operator workflow. Name it exactly:  AP - Bank Change Verification

WHAT THIS OPERATOR IS FOR
Two jobs. First, check the vendor is not blocked or deleted. Second, and more importantly,
detect payment-redirection fraud, also called business email compromise.

THE HARD PART, READ THIS CAREFULLY
A criminal emails us pretending to be a supplier and says "our bank details have changed".
If we believe them, the next large payment goes to the criminal.
BUT legitimate suppliers also change their bank details, and that is normal and fine.
In our data there are 10 bank-change requests. Only 3 are fraud. 7 are genuine.
An Operator that freezes all 10 is a FAILURE, not a success. Blocking every bank change
would be easy and useless. The whole value of this Operator is telling them apart.
You do that by correlating FOUR independent signals, defined in CARD 7.

DEFINE THESE INPUTS
  canonical_invoice  JSON  required
  policy_snapshot    JSON  required
  run_id             text  required

BUILD THESE CARDS, IN THIS EXACT ORDER

CARD 1 — name it "Query Vendor Master"
  Action: native Supabase "Query table"
  Schema: public
  Table:  vendor_master
  Filter: lifnr equals canonical_invoice.lifnr
  Limit:  2
  Branch:
    0 rows -> status REVIEW, reason_codes ["VENDOR_NOT_FOUND"]. Stop here.
    2 rows -> the vendor master has two conflicting records, so we cannot tell which bank
              account is the real one. Add reason_code "VENDOR_MASTER_DUPLICATE" and set
              status REVIEW, but CONTINUE to CARD 2 using the first row.
    1 row  -> continue to CARD 2.
  Remember this row's email column. You need it in CARD 5.

CARD 2 — name it "Check Vendor Block"
  No external action.
  If the vendor_master sperr column is not empty:
    status FAIL, reason_codes ["VENDOR_BLOCKED"],
    protected_value_candidate = absolute invoice amount.
  If the vendor_master loevm column is not empty:
    status FAIL, reason_codes ["VENDOR_DELETED"],
    protected_value_candidate = absolute invoice amount.
  Even if one of these fires, CONTINUE through the remaining cards so the evidence is
  complete. Do not stop early here.

CARD 3 — name it "Check Whether Invoice States A Bank Account"
  No external action.
  If canonical_invoice.bank_on_inv is empty, skip CARD 4 and go straight to CARD 5.
  Otherwise continue to CARD 4.

CARD 4 — name it "Compare Invoice Bank To Approved Accounts"
  Action: native Supabase "Query table"
  Schema: public
  Table:  bank_master
  Filter: lifnr equals canonical_invoice.lifnr
  Limit:  20
  From the rows returned, build two sets:
    CURRENT  = the bankn values of rows where is_current equals "Y"
    ALL      = the bankn values of every row returned
  Then:
    if canonical_invoice.bank_on_inv is NOT in ALL
       -> add reason_code "BANK_ACCOUNT_UNKNOWN" and set status REVIEW.
          This is the stronger signal: the account has never been approved for this vendor.
    else if canonical_invoice.bank_on_inv is NOT in CURRENT
       -> add reason_code "BANK_MISMATCH" and set status REVIEW.
          The account exists in our records but is not the current one.

CARD 5 — name it "Inspect Bank Change Emails"
  Action: native Supabase "Query table"
  Schema: public
  Table:  email_headers
  Filter: lifnr equals canonical_invoice.lifnr AND msg_type equals "bank_change_request"
  Limit:  20
  For EVERY row returned, work out two things:

    (a) DID EMAIL AUTHENTICATION FAIL?
        It failed if ANY of these is true:
            spf   is not exactly "pass"
            dkim  is not exactly "pass"
            dmarc is exactly "fail"
        Note "softfail" is NOT "pass". Treat it as a failure.

    (b) DOES THE SENDER DOMAIN MATCH THE VENDOR?
        Take the text AFTER the "@" in from_addr.
        Take the text AFTER the "@" in the vendor_master email from CARD 1.
        If those two are different, that is a domain mismatch.
        Worked example: from_addr "accounts@summit-billing.com" gives "summit-billing.com".
        Vendor master email "ap@summit.com" gives "summit.com".
        These are different, so it IS a mismatch. A lookalike domain is a classic
        impersonation technique.

  The recv_ts column may be empty, or in an unusual format. If you cannot read it, record
  it as unknown and carry on. DO NOT GUESS A TIMESTAMP.

CARD 6 — name it "Check For Externally Sourced Bank Changes"
  Action: native Supabase "Query table"
  Schema: public
  Table:  bank_master
  Filter: lifnr equals canonical_invoice.lifnr
  Limit:  20
  Look for any row where change_source equals "EMAIL" OR changed_by equals "EXTERNAL".
  A bank account added by an outside party, rather than through our own portal or
  onboarding process, is suspicious on its own.
  Remember each such row's valid_from date. You need it in CARD 7.

CARD 7 — name it "Correlate The Four Fraud Signals"
  No external action. This card is the point of the whole Operator.
  Work out whether each of these four signals is TRUE or FALSE:

    SIGNAL A — a bank-change email exists for this vendor whose authentication FAILED
               (from CARD 5, test a)
    SIGNAL B — that email's sender domain does NOT match the vendor master domain
               (from CARD 5, test b)
    SIGNAL C — a bank_master row exists for this vendor with change_source "EMAIL" or
               changed_by "EXTERNAL"  (from CARD 6)
    SIGNAL D — the invoice is high value AND the timing is suspicious. Both must hold:
                 absolute invoice amount is greater than or equal to
                     policy_snapshot.high_value_threshold
                 AND the number of days between the bank change valid_from and the invoice
                     date is within policy_snapshot.bank_change_freeze_days

  Count how many of A, B, C, D are TRUE, then decide:

    3 or 4 signals true -> status FAIL
                           reason_codes ["BEC_SUSPECTED"]
                           protected_value_candidate = absolute invoice amount
                           This is a critical fraud hold.

    1 or 2 signals true -> status REVIEW
                           reason_codes ["BANK_CHANGE_UNVERIFIED"]
                           protected_value_candidate = absolute invoice amount

    0 signals true      -> no fraud finding. Keep whatever status CARD 2 and CARD 4 set.

  DO NOT add any extra rule that flags a vendor merely for having changed bank details at
  some point. The codes above already cover every case where a bank change touches a real
  payment. A broader rule would sweep in invoices that state no bank account at all, and
  would cost us touchless rate for no extra protection.

CARD 8 — name it "Return Result"
  Return the standard contract output. operator_name is "AP - Bank Change Verification".
  evidence MUST list all four signals with their true/false value AND the actual values
  compared: the sender address, the vendor master email, the spf/dkim/dmarc values, the
  bank account stated on the invoice, the current approved account, the change_source, and
  the days between the bank change and the invoice.
  This evidence block is what we put on screen for the judges. It must stand on its own.

REJECT THE BUILD IF:
  - the workflow freezes every bank change instead of correlating the four signals
  - "softfail" is treated as a pass
  - the domain comparison compares whole email addresses instead of the part after "@"
  - CARD 7 uses a typed-in amount instead of policy_snapshot.high_value_threshold
  - the workflow invents a timestamp when recv_ts is empty
  - evidence does not show all four signals separately
```

---

## §B6 · Operator 5 — `AP - Entity and Approval Control` · owner: Lim

```text
Build a new Supervity Auto Operator workflow. Name it exactly:  AP - Entity and Approval Control

WHAT THIS OPERATOR IS FOR
Three jobs. Confirm the invoice is booked to the right legal entity. Convert the amount to
our group currency (MYR). Then pick the correct approver from the delegation-of-authority
matrix.

DEFINE THESE INPUTS
  canonical_invoice  JSON  required
  policy_snapshot    JSON  required
  run_id             text  required

BUILD THESE CARDS, IN THIS EXACT ORDER

CARD 1 — name it "Check Booking Entity"
  Only run this card when BOTH canonical_invoice.bukrs_on_inv is present AND
  canonical_invoice.ebeln is present. Otherwise skip to CARD 2.
  Action: native Supabase "Query table"
  Schema: public
  Table:  po_headers
  Filter: ebeln equals canonical_invoice.ebeln
  Limit:  1
  Compare the PO header bukrs with canonical_invoice.bukrs_on_inv.
  If they are different:
    status FAIL
    reason_codes ["ENTITY_MISMATCH"]
    protected_value_candidate = absolute invoice amount
    evidence: entity_on_invoice and entity_on_po, both values
    This means the invoice is being booked to the wrong legal company. Stop here.

CARD 2 — name it "Convert Amount To MYR"
  If canonical_invoice.waers equals "MYR":
    amount_myr = the absolute invoice amount, fx_rate = 1, fx_rate_date = null.
    Skip to CARD 3.
  Otherwise:
  Action: native Supabase "Query table"
  Schema: public
  Table:  fx_rates
  Filter: fcurr equals canonical_invoice.waers
          AND tcurr equals "MYR"
          AND gdatu is LESS THAN OR EQUAL TO policy_snapshot.as_of_date
  Sort:   gdatu DESCENDING
  Limit:  1
  This is a nearest-earlier-date lookup. The rate table does NOT have a row for every date,
  and it stops on 27 July 2026, so an exact-date lookup will fail for many invoices.
  Branch:
    0 rows -> status REVIEW, reason_codes ["FX_RATE_MISSING"].
              DO NOT INVENT A RATE. DO NOT USE 1. DO NOT USE THE NEAREST LATER DATE.
              Leave amount_myr empty and skip to CARD 5.
    1 row  -> amount_myr = absolute invoice amount * ukurs
              Record ukurs and the gdatu you actually used. A human must be able to see
              which rate date was applied.

CARD 3 — name it "Select The Approver"
  Action: native Supabase "Query table"
  Schema: public
  Table:  doa_matrix
  Filter: kostl equals the invoice cost centre if one is known, otherwise
          policy_snapshot.default_kostl
  Limit:  20
  From the rows returned, choose the ONE row where:
       min_amt is less than or equal to amount_myr
       AND max_amt is greater than or equal to amount_myr
  Branch:
    no row matches -> status REVIEW, reason_codes ["DOA_BAND_NOT_FOUND"]
    one row matches -> record its role, approver and email as the proposed approver.

CARD 4 — name it "Check Auto Pay Eligibility"
  No external action.
  auto_pay_eligible is TRUE only when amount_myr is less than or equal to
  policy_snapshot.auto_pay_limit.
  Report this as a true/false value in evidence. Do not change the status here.
  The Orchestrator decides what to do with it.

CARD 5 — name it "Handle Non PO Invoices"
  No external action, unless a GL code is present.
  If canonical_invoice.ebeln is present, skip this card entirely.
  If canonical_invoice.ebeln is ABSENT, this is spend with no purchase order behind it:
    status REVIEW
    add reason_code "NON_PO_APPROVAL"
    A non-PO invoice never clears automatically. It always needs a person.
  Then try to propose a general ledger account:
    if canonical_invoice.gl_code is present:
       Action: native Supabase "Query table"
       Schema: public
       Table:  gl_master
       Filter: saknr equals canonical_invoice.gl_code
       Limit:  1
       if 0 rows -> add reason_code "GL_CODING_REQUIRED"
       if 1 row  -> also check that the invoice cost centre appears in the kostl_allowed
                    column of that row. If it does not, add "GL_CODING_REQUIRED".
    if canonical_invoice.gl_code is absent:
       add reason_code "GL_CODING_REQUIRED"
  DO NOT INVENT A GL CODE. Do not pick a plausible one. Do not pick the most common one.

CARD 6 — name it "Return Result"
  Return the standard contract output. operator_name is "AP - Entity and Approval Control".
  Also include: amount_myr, fx_rate, fx_rate_date, proposed_approver_role,
  proposed_approver_email, auto_pay_eligible.
  If no card set FAIL or REVIEW, status is PASS, protected_value_candidate is 0.

REJECT THE BUILD IF:
  - CARD 2 uses an exact date match instead of nearest-earlier-date
  - CARD 2 falls back to a rate of 1, or to a later date, when no rate is found
  - CARD 2 uses today's real date instead of policy_snapshot.as_of_date
  - CARD 3 has typed-in amount bands instead of reading doa_matrix
  - CARD 5 proposes a GL code that did not come from gl_master
  - any card writes to the database. This Operator only reads.
```

---

## §B7 · The Orchestrator — `AP Control Tower Orchestrator` · owner: Ku · BUILD LAST

```text
Build a new Supervity Auto ORCHESTRATOR workflow. Name it exactly:
AP Control Tower Orchestrator

WHAT AN ORCHESTRATOR IS
It is a manager. It decides which Operators run, in what order, passes information between
them, retries when one fails, combines their answers into one decision, and escalates to a
human. It does NOT do the detailed work itself.

THE ORCHESTRATOR MUST NOT QUERY ANY BUSINESS TABLE ITSELF.
Every Supabase read happens inside an Operator. If you find yourself adding a "Query table"
card for ap_invoices, po_headers or any other business table here, that is wrong.

DEFINE THESE INPUTS
  invoice_ref      text  required
  policy_snapshot  JSON  required
  run_id           text  required

BUILD THESE STEPS, IN THIS EXACT ORDER

STEP 1 — "Normalize The Invoice"
  Trigger the Operator Agent named: AP - Intake and Normalize
  Pass it: invoice_ref, policy_snapshot, run_id.
  Keep its canonical_invoice output. This is the shared context for every later Operator.
  Branch on its status:
    FAIL or ERROR -> the verdict is DATA_ERROR. Skip STEP 2, STEP 3 and STEP 4.
                     Go straight to STEP 5.
    anything else -> continue to STEP 2.

STEP 2 — "Run The Screening Operators In Parallel"
  Trigger these three Operator Agents AT THE SAME TIME, not one after another. They do not
  depend on each other, and running them in parallel is a scored part of the architecture.
      AP - Duplicate and Fraud Screen
      AP - Bank Change Verification
      AP - Entity and Approval Control
  Pass each of them: canonical_invoice, policy_snapshot, run_id.
  Wait until all three have returned before continuing.

STEP 3 — "Branch On Purchase Order"
  Look at canonical_invoice.is_po.
    if it is TRUE  -> trigger the Operator Agent named: AP - Three Way Match
                      Pass it canonical_invoice, policy_snapshot, run_id.
    if it is FALSE -> do NOT trigger it. Skip this step entirely. The non-PO approval path
                      is handled inside AP - Entity and Approval Control.

STEP 4 — "Collect All Results"
  Wait for every Operator triggered above to return.
  Store each Operator's whole result object under its OWN key, named after the Operator.
  Do not merge them together. Do not overwrite one with another. A human must be able to
  see what each Operator concluded on its own.

  RETRY RULE: if any Operator returns status ERROR with retryable true, trigger that ONE
  Operator again, once, after a short delay. If it fails a second time, record reason_code
  "CONNECTOR_FAILURE" for that Operator and carry on with the others.

STEP 5 — "Decide One Verdict"
  Combine every Operator's status into exactly ONE verdict, using this precedence.
  Check them in this order and take the FIRST one that applies:
      1. any Operator returned FAIL                       -> PAYMENT_HOLD
      2. any Operator returned ERROR, or STEP 1 failed    -> DATA_ERROR
      3. any Operator returned REVIEW                     -> HUMAN_REVIEW
      4. every Operator returned PASS or NOT_APPLICABLE   -> PAY_READY
  Also collect every reason_code from every Operator into one combined list, removing
  duplicates but keeping all distinct codes.

STEP 6 — "Calculate Money Protected"
  Be conservative and be able to defend the number.
    - Only a PAYMENT_HOLD verdict protects money.
    - Take the SINGLE LARGEST protected_value_candidate among the Operators that returned
      FAIL. Take ONE number, the largest.
    - DO NOT ADD THEM TOGETHER. One invoice, held once, is one amount protected. Adding two
      flags on the same invoice double counts and is indefensible if a judge asks.
    - Report it in the invoice's own currency.
    - If the verdict is HUMAN_REVIEW, the amount is spend_under_review, NOT money protected.
      These are different numbers and must not be mixed.
    - If the verdict is PAY_READY or DATA_ERROR, money protected is 0.

STEP 7 — "Apply The Policy Gate"
  Before ANY external action, compare the proposed verdict against policy_snapshot.
  Record which policies were evaluated, which ones fired, and the policy_version.
  Nothing is sent and nothing is written before this step finishes.

STEP 8 — "Take Action"
  Only after STEP 7.
    If the verdict is NOT PAY_READY:
       send a Slack message containing: invoice number, vendor, amount, verdict, the reason
       codes, and the run_id.
       REDACT the bank account number. Never post a full bank account number to a channel.
       Show at most the last four characters.
    If the verdict is PAYMENT_HOLD, HUMAN_REVIEW or DATA_ERROR:
       create a Workbench task containing the FULL evidence from every Operator plus the
       recommended action, so the reviewer needs no other system to decide.

STEP 9 — "Return The Decision"
  Return: run_id, verdict, the combined reason_codes, the per-Operator evidence, money
  protected, spend_under_review, the policies evaluated, and the Workbench task id.

TWO RULES THAT MUST HOLD
  - The verdict this Orchestrator produces is IMMUTABLE. When a human later resolves the
    exception, their decision is recorded separately and must never overwrite this verdict,
    these reason codes, or this evidence.
  - Never write a specific invoice number, vendor number or PO number anywhere in this
    workflow.

REJECT THE BUILD IF:
  - STEP 2 runs the three Operators one after another instead of at the same time
  - STEP 3 runs the Three Way Match for an invoice with no purchase order
  - STEP 4 merges the Operator results into one flat object
  - STEP 5 lets HUMAN_REVIEW override PAYMENT_HOLD
  - STEP 6 adds protected values together
  - STEP 8 fires Slack or the Workbench before STEP 7 has run
  - STEP 8 posts a full bank account number
  - the Orchestrator queries any business table directly
```

---

## §B8 · Runtime test inputs — NEVER put these in a prompt

Type these into the run panel when testing. They must never appear in a workflow prompt,
condition or mapping. Every row was verified against the Round 2 pack.

| Test | Input | Expected | Co-flags to expect |
|---|---|---|---|
| **Clean PO invoice** | `5110000002` | `PAY_READY` | none — verified fully clean |
| **BEC fraud — the hero** | `5110000152` | `PAYMENT_HOLD` · `BEC_SUSPECTED` | low confidence 0.66 only |
| Legit bank change — must **NOT** be fraud | any invoice for vendor `4110023` | not `BEC_SUSPECTED` | SPF/DKIM/DMARC all pass, domain matches |
| PO vendor mismatch | `5110000017` | `PAYMENT_HOLD` · `PO_VENDOR_MISMATCH` | also carries `bank_on_inv` |
| Exact duplicate, cross-channel | `5190000040` | `PAYMENT_HOLD` · `DUP_LATER_COPY` | `RECEIPT_MISSING` (BSART=NB) |
| Near-duplicate, OCR variance | `5110000159` | `HUMAN_REVIEW` · `NEAR_DUP_SUSPECT` | pairs with `5110000158`; low conf 0.67 + `RECEIPT_PARTIAL` |
| Ambiguous date | `5110000118` | `HUMAN_REVIEW` · `DATE_AMBIGUOUS` | none — clean single signal |
| Orphan PO reference | `5110000260` | `HUMAN_REVIEW` · `PO_NOT_FOUND` | none — clean single signal |
| Currency mismatch | `5110000009` | `PAYMENT_HOLD` · `PO_CURRENCY_MISMATCH` | SGD vs MYR; `RECEIPT_MISSING` (FO) |
| Credit memo | `5110000174` | `HUMAN_REVIEW` · `CREDIT_MEMO` | negative amount also fails line match |
| Wrong entity | `5110000164` | `PAYMENT_HOLD` · `ENTITY_MISMATCH` | also `VENDOR_BLOCKED` |
| Comma-decimal amount | `5110000001` | parses to `327845.70` | verdict `HUMAN_REVIEW` (`RECEIPT_MISSING`) |
| Blocked vendor | any invoice for a vendor with `sperr` set | `PAYMENT_HOLD` · `VENDOR_BLOCKED` | |
| Non-PO | any invoice with blank `ebeln` | `HUMAN_REVIEW` · `NON_PO_APPROVAL` | |

### Why `5110000152` is the hero

Vendor **4110053, Summit Steelworks**. All four fraud signals line up and nothing else muddies it:

| Signal | Evidence |
|---|---|
| Spoofed sender, lookalike domain | `accounts@summit-billing.com` vs master `ap@summit.com` |
| Email authentication failed | SPF `softfail` · DKIM `fail` · DMARC `fail` (`MSG000005`) |
| New account added by an external party | `5379-5008-9571`, `change_source=EMAIL`, `changed_by=EXTERNAL`, `is_current=N` |
| High value, damning timing | MYR 1,234,293.69 — bank change `valid_from` is **2026-06-29, the same day as the invoice** |

The same vendor has three other invoices (`5110000098`, `5110000210`, `5110000016`) carrying none of
these signals. Show the agent clearing those and holding only this one. That is the precision story.

### The policy demo

Run the same PO invoice twice with `gr_policy` set to `strict_require_gr`, then `fo_aware`.
On the public pack this moves touchless from **27.8% to 40.2%**.

---

## §B9 · Troubleshooting

| Symptom | Fix |
|---|---|
| A card references `SUPABASE_TOKEN`, `/rest/v1`, `httpx`, `requests`, or a generic HTTP action | Reject it. Paste: *"Rebuild this card using the native Supabase OAuth Query table action only. Do not use tokens, URLs, HTTP actions or code."* This exact failure cost Round 1 a day. |
| An Operator invents a value for a blank field | Paste: *"If this field is empty, return status REVIEW with reason_code MISSING_EVIDENCE. Do not substitute a default, do not guess, do not use the most common value."* |
| The Orchestrator runs Operators one after another | Paste: *"Change STEP 2 so all three Operator Agents are triggered at the same time, then wait for all three to return before continuing."* |
| A sample invoice number appears in a condition | Remove it and replace with the runtime input variable. Hardcoding to sample rows is grounds for disqualification. |
| Amounts are wrong by a factor of 100 or 1000 | The comma rule is backwards. Re-paste CARD 3 of Operator 1 and check `"327845,70"` gives `327845.70`. |
| The three-way match flags almost everything as a variance | It is comparing against the PO header total. Re-paste CARD 7 of Operator 3 — it must compare against `po_items.netwr`, one line at a time. |
| Every bank change gets frozen | Operator 4 is not correlating the four signals. Re-paste CARD 7 of Operator 5 and check "softfail" counts as a failure but a passing, domain-matching change scores zero signals. |
| A connector fails mid-build | Time-box to 15 minutes, then move to the next Operator and raise it. Do not grind. |
