# Round 2 data pack — trap census

Computed directly from `round2/data/csv/` (14 tables, 450 invoices). Numbers are for **our own
testing and demo selection only** — judging runs on a hidden pack, so never branch on these IDs.

## Shape

| Table | Rows | Note |
|---|---|---|
| RBKP_Invoice | 450 | the trigger. 435 PO / 15 non-PO |
| EKKO_PO_Header | 153 | BSART: 89 `NB`, 64 `FO` (framework) |
| EKPO_PO_Item | 276 | line-level `NETWR`, `UEBTO`/`UNTTO` tolerances |
| MSEG_Goods_Receipt | 135 | |
| LFA1_Vendor_Master | 80 | |
| KONP_Conditions | 135 | |
| SKA1_GL_Master | 14 | |
| DOA_Matrix | 10 | **5 bands × 2 cost centres (CC100/CC200)** — approver is band + KOSTL |
| **Company_Codes** | 6 | MY10/MY20 MYR · SG30 SGD · IN40 INR · TH50 THB · ID60 IDR |
| **FX_Rates** | 894 | 6 pairs × 149 days, all `→ MYR` |
| **Bank_Master** | 114 | approved accounts + change history, `CHANGE_SOURCE`, `IS_CURRENT` |
| **Email_Headers** | 78 | SPF/DKIM/DMARC, `MSG_TYPE`, sender address |
| **Discount_Schedule** | 79 | `DISC_PCT` 1.0–2.5%, `DISC_DAYS`, `NET_DAYS` |
| **Approval_Log** | 141 | 111 approved / 21 escalated / 9 pending — **ground truth for our verdicts** |

New invoice columns: `SUBMIT_TS`, `CONFIDENCE`, `GST_AMT`, `BUKRS_ON_INV`, `PO_WAERS`.

## The organizer's own policy vocabulary

`Approval_Log.POLICY_REF` tells us what the pack expects the policy engine to be called:

| POLICY_REF | Rows |
|---|---|
| `DOA-BAND` | 100 |
| `FX-RECONCILE` | 14 |
| `PRICE-TOLERANCE` | 12 |
| `VENDOR-BLOCK` | 6 |
| `BANK-CHANGE-FREEZE` | 4 |
| `ENTITY-CONSISTENCY` | 3 |
| `MATCH-EXCEPTION` | 2 |

Name our AI Policies exactly these. `Approval_Log` then doubles as a validation set.

## Trap census

### Carried over from Round 1
| Trap | Count | Sample |
|---|---|---|
| Comma-decimal amounts (`327845,70`) | 52 | |
| Exact duplicates (fingerprint groups) | 24 groups / 24 extra copies | `5110000040` ↔ `5190000040` (EMAIL vs EDI) |
| Blocked vendors (`SPERR`) | 3 vendors → 25 invoices | |
| Deleted vendors (`LOEVM`) | 0 | rule still needed for hidden pack |
| Duplicate vendor-master rows | 1 vendor | `4110005` |
| Bank on invoice ≠ current `Bank_Master` | 12 of 12 carrying `BANK_ON_INV` | 2 not in `Bank_Master` at all: `5110000017`, `5110000050` |
| PO invoices whose PO has **no** goods receipt | 154 | `fo_aware` toggle still swings touchless hard |
| Non-PO (blank `EBELN`) | 15 | |

### New in Round 2
| Trap | Count | Sample / note |
|---|---|---|
| **BEC bank-change (spoofed)** | **3** | see below — the hero case |
| Legitimate bank-change requests | 7 | SPF/DKIM/DMARC all pass, correct domain — **must not be frozen** |
| Near-duplicate OCR variance | 3 groups | `INV273650` vs `INV27365O ` (O→0, trailing space, 33353.94 → 33354.00, EMAIL vs DRIVE) |
| Wrong entity (`BUKRS_ON_INV` ≠ PO `BUKRS`) | 3 | `5110000164` MY20≠TH50 · `5110000165` MY20≠IN40 · `5110000166` MY10≠MY20 |
| FX mismatch (`WAERS` ≠ `PO_WAERS`) | 43 | `5110000009` SGD vs MYR |
| Invoice currency ≠ entity local currency | 269 | needs FX conversion for any MYR-denominated KPI |
| Split invoices under a DOA band | 11 | same vendor + same day, sum crosses band — e.g. `5110000237`+`5110000238` → Team Lead→Manager |
| Expired contract price (`KONP.DATBI` past) | 18 conditions | |
| **Credit memos (negative `WRBTR`)** | **3** | `5110000174/175/176` — will break naive matching + money-protected maths |
| **Retroactive PO** (invoice date < PO create) | **42** | `5110000013` inv 2026‑04‑26, PO created 2026‑05‑24 |
| Invoice before PO validity start (`KDATB`) | 24 | |
| **Orphan PO ref** (EBELN not in EKKO) | **5** | `5110000260`, `5110000319`, `5110000347`, `5110000360`, `5110000445` |
| **Mixed date formats in `BLDAT`** | **88** | 44 × `Apr 29 2026`, 44 × `19/04/2026` |
| ⤷ of which genuinely ambiguous (both ≤12) | **15** | `02/07/2026`, `09/06/2026`… → must escalate, not guess |
| `SUBMIT_TS` with no timezone | 246 of 450 | 162 carry `+08:00` |
| Low extraction `CONFIDENCE` | <0.70: 12 · <0.80: 30 · <0.85: 115 | range 0.55–0.99 |
| `GST_AMT` anomalies | **0** | tax is clean — do not spend time here |

### The BEC chain (hero demo)

Three fraud attempts are fully traceable across four tables:

| Email | Vendor | Sender | Vendor master domain | SPF/DKIM/DMARC | New account |
|---|---|---|---|---|---|
| `MSG000001` | 4110006 | `highland.remittance@outlook.com` | `ap@highland.com` | softfail/fail/fail | `6406-8941-4832` |
| `MSG000003` | 4110029 | `sunrise.remittance@outlook.com` | `ap@sunrise.com` | fail/fail/fail | `3617-4140-3183` |
| `MSG000005` | 4110053 | `accounts@summit-billing.com` | `ap@summit.com` | softfail/fail/fail | `5379-5008-9571` |

All three land in `Bank_Master` with `CHANGE_SOURCE=EMAIL`, `CHANGED_BY=EXTERNAL`, `IS_CURRENT=N` —
then large invoices follow (`Approval_Log` shows `5110000150`/`5110000151` escalated on
`BANK-CHANGE-FREEZE`, ≈MYR 1.2M each).

**Four-signal correlation:** sender domain ≠ vendor master domain · email auth fails · new bank
account sourced `EMAIL`/`EXTERNAL` · large invoice within N days. That is what separates the 3 fraud
attempts from the 7 legitimate bank changes. A naive "any bank change → freeze" rule produces 7 false
positives; the precision story is the demo.

## Core matching behaviour on the 450-invoice pack

### Line-level vs header-total — the Round 1 locked decision holds, harder

| Tolerance | Header-total comparison | Line-level comparison |
|---|---|---|
| 2% | flags **330/427 (77.3%)** as price variance | 398 match exactly one line (93.2%) · 26 zero (6.1%) · 3 ambiguous (0.7%) |
| 5% | flags 322/427 (75.4%) | 393 exactly one (92.0%) · 26 zero · 8 ambiguous |

Comparing the invoice to the PO **header** `NETWR` flags three quarters of the pack as a variance —
worse than Round 1's ~56%. Match against a PO **line** `NETWR`. Zero matches → real price variance →
human. Multiple → ambiguous → human. Never auto-pick the nearest line.

### Goods receipt (on the uniquely matched line, 2% tolerance)

| Outcome | Count |
|---|---|
| `RECEIPT_MISSING` | 203 |
| receipt OK | 175 |
| `RECEIPT_PARTIAL` | 20 |
| no unique line to check | 29 |

163 invoices sit on framework (`BSART=FO`) POs — the population the `fo_aware` toggle exempts.

### Touchless ceiling (public pack, before any human resolution)

| GR policy | Touchless |
|---|---|
| `strict_require_gr` | 135/450 = **30.0%** |
| `fo_aware` | 194/450 = **43.1%** |

A **13-point swing from one editable policy field** — that is the live no-code policy demo, and it is
worth more than the absolute number. Round 2 is harder than Round 1 (40.8% → 52.6% on 152 invoices),
so lead the business story with **money protected**, not touchless rate.

### FX

`FX_Rates` covers **2026-03-01 → 2026-07-27** (149 days) for EUR, IDR, INR, SGD, THB → MYR.
All 24 non-MYR invoices with a parseable date have an exact-date rate. But the table **stops on
27 Jul** — anything dated later (including anything a judge submits live on 9 Aug) has no rate.
Implement nearest-prior-date fallback, and audit which rate date was used.

## ⚠️ Timing hazard: the discount window is nearly closed

`DISC_DAYS` runs 15–20 days from `BLDAT`, and most invoices are dated Apr–Jul 2026:

| As of | Inside discount window | Expiring ≤7d | Discount value at stake |
|---|---|---|---|
| 2026-07-31 | 13 | 12 | MYR 106,039.64 |
| **2026-08-09 (finale)** | **1** | **1** | **MYR 9,309.01** |

"Cash optimized" is a named outcome metric and "discount captured vs at risk" is a named dashboard
tile. **Anchor every date-relative calculation to a configurable operational "as-of" date** (a policy
field, defaulting to today) instead of hardcoding `now()`. Set it to ~2026‑07‑15 for the demo and the
discount, DPO, aging, and cash-forecast tiles all come alive — and it is defensible, because it is a
visible, editable policy rather than a fudge.
