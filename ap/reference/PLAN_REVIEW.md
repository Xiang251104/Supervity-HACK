# Review of `PLAN_teammate.md`

Reviewed against: Round 2 Participant Guide, Round 2 Finance problem statement, the actual
AutoPilot-Template code (cloned, `main` @ `f0250ac`), and the Round 2 data pack
(see `../analysis/DATA_PROFILE_R2.md`).

## Verdict

**Structurally correct, and worth building on — but it is a compliance plan, not a winning plan.**

It gets every mandatory item right and would clear the qualification gate. What it does not do is
optimise for where the marks actually are. On the published rubric it reads like a mid-band build
(solid Architecture, thin Insights, generic Policies, no bonus). Recommendation: **keep it as the
skeleton, add the ten items below.**

### What it gets right

- Starting from the official template rather than the old `AIEmployee` repo. Mandatory; correct.
- Six Operators (floor is five), Round 1 three extended rather than rebuilt.
- Refusing to count an infrastructure workflow ("Store Decision") as a business Operator — sharp
  catch, and exactly the "delete it and see if a capability disappears" test in §2.6 of the guide.
- Supabase as system of record, dataset seeded not read from disk, dataset not committed.
- Policy snapshot loaded per run, versioned, passed into the Orchestrator, evaluated **before**
  the action — this is the part most teams get wrong (§7.2).
- Streaming workflow endpoint + bearer key in `.env` only.
- A real acceptance-test list, and the clean-clone requirement.

## The ten gaps

Ordered by rubric points per hour of work.

### 1. No hero case — the BEC fraud chain is the strongest thing in the pack and the plan treats it as one line item
`Rubric: Business output 30 · AI Insights 15`

The plan lists "AP – Bank Change Verification" as an Operator and "a spoofed bank-change email
produces a fraud hold" as an acceptance test. That understates it. The pack contains **3 spoofed
bank-change attempts and 7 legitimate ones**, and the discriminator requires joining four tables
(`Email_Headers` auth flags + sender domain vs `LFA1.EMAIL` + `Bank_Master.CHANGE_SOURCE=EMAIL` /
`CHANGED_BY=EXTERNAL` + a large invoice following within N days).

A naive "freeze on any bank change" rule scores 3/3 recall and 7 false positives. Ours should catch
3/3 with 0 false positives, and we should **say that number out loud in the demo**. That is
"quantified metric movement" (10 pts) and a non-trivial insight with severity (5 pts) in one.

### 2. Policies are generically named — the pack tells us what to call them
`Rubric: Customizability and Policies 20`

The plan proposes four policies by description. `Approval_Log.POLICY_REF` gives the organizer's own
vocabulary: `DOA-BAND` (100 rows), `FX-RECONCILE` (14), `PRICE-TOLERANCE` (12), `VENDOR-BLOCK` (6),
`BANK-CHANGE-FREEZE` (4), `ENTITY-CONSISTENCY` (3), `MATCH-EXCEPTION` (2).

Name our policies exactly these. Two payoffs: instant credibility with a finance judge, and
`Approval_Log` becomes a **validation set** — we can state what share of its 111 approvals / 21
escalations our engine reproduces. Nobody else will do this.

### 3. No oracle for the 450-invoice pack
`Rubric: Business output 30`

Round 1's single biggest advantage was `EXPECTED_ORACLE.csv` — an independently computed answer key.
The plan never mentions rebuilding it for Round 2. We already have `round1/oracle/build_oracle.py`;
extending it to 450 invoices and the six new tables is a few hours and it is what lets us (a) quote
real touchless / money-protected / cash-optimised numbers instead of vibes, (b) catch a regression in
minutes, and (c) survive a judge asking for a row we did not rehearse.

### 4. The discount metric is dead on demo day
`Rubric: Business output 30 · Command Center 15`

`DISC_DAYS` is 15–20 days from `BLDAT` and most invoices are Apr–Jul 2026. As of the finale
(2026‑08‑09), **exactly 1 invoice is still inside its discount window** (MYR 9,309 at stake) versus
13 as of 2026‑07‑31. "Cash optimized" is a named outcome metric and "discount captured vs at risk" a
named dashboard tile.

Fix: every date-relative calculation (discount, DPO, aging, cash forecast) reads a configurable
**operational as-of date** from the policy store rather than `now()`. Defensible because it is a
visible, editable policy — and it doubles as another live no-code knob for a judge to turn.

### 5. Nothing claims the +10 bonus, and the cheapest bonus is one feature
`Rubric: bonus +10`

Both the guide (§7.6, §11.4) and the problem statement call out **self-learning: a human correction
at the Workbench changes future behaviour**. It is also the "automation-opportunity insight" the
guide calls "one of the strongest things to build" (§7.3).

One feature covers both: capture every Workbench override, aggregate by reason code, and when a
pattern crosses a threshold emit an Insight — *"You approved 6 `RECEIPT_MISSING` exceptions on
framework (`FO`) orders this week. Promote to policy?"* — with a one-click button that writes the
policy and changes the next run. Insight → action path → policy → behaviour change → logged
evaluation. That is Insights (15), Policies (20) and bonus in a single build.

### 6. Data Manager is build-from-zero, not "replace demo data"
`Rubric: Architecture 20 (integration realism 5) · Command Center 15`

Verified against the cloned template: `frontend/src/app/` contains `admin/`, `ai/insights`,
`ai/policies`, `workbench`, `settings` — **there is no Data Manager page and no backend health
registry.** The plan lists it alongside surfaces that merely need rewiring. It is a new page, new
model, new endpoints. Budget for it; §7.5 says it is "how a judge sees that your integrations are
real", and §8.4 says a hardcoded Data Manager entry does not count toward the three-integration floor.

Also worth knowing: the template ships **zero** Supervity/Auto client code (grep confirms it is
mentioned only in the docs). The entire Auto wiring is ours to write.

### 7. Half the Round 2 traps are not in the acceptance tests
`Rubric: Business output 30 (edge cases 5) · gate condition 1`

The plan tests ~5 trap types. The pack seeds these too, and each will break a naive implementation:

| Trap | Count | Why it bites |
|---|---|---|
| Credit memos (negative `WRBTR`) | 3 | breaks line matching and inflates/negates money-protected |
| Retroactive PO (invoice predates PO) | 42 | large population — needs a deliberate rule, not an accident |
| Orphan PO ref (EBELN not in EKKO) | 5 | must escalate, not crash |
| Expired contract price (`KONP.DATBI` past) | 18 | the price-tolerance check silently uses a dead rate |
| Mixed date formats in `BLDAT` | 88 | 44 × `Apr 29 2026`, 44 × `19/04/2026` |
| ⤷ genuinely ambiguous (both ≤12) | 15 | **must escalate, never guess** — this is the "don't invent a value" rule |
| `SUBMIT_TS` without timezone | 246 | duplicate-window and SLA maths |
| Duplicate vendor-master row | 1 (`4110005`) | two "current" banks for one vendor |

`GST_AMT` is clean across all 450 — no tax trap. Don't spend time there.

### 8. "Branch/fan out" is one sentence; orchestration depth is 7 points
`Rubric: Architecture 20 (orchestration depth 7)`

The rubric scores parallel fan-out/fan-in, conditional branching, retries and clean context passing
specifically. We need a written map: which Operators run concurrently, where the fan-in is, the
retry/backoff rule, and the shared context contract (Round 1's `CanonicalInvoice` is the obvious
basis). Judges ask you to explain your own architecture (§11.5).

### 9. Six Operators, but no payment run — and "cash optimized" needs one
`Rubric: Business output 30`

The problem statement's example flow ends with **Payment Prep**, and DPO + short-horizon cash
forecast are named dashboard tiles. A "Discount Optimizer" that flags discounts does not schedule a
payment run. Adding a 7th Operator (Payment Run / Cash Optimizer) closes the loop from decision to
disbursement and is also straightforward bonus ("extra Operators and richer downstream actions").

### 10. Logistics the plan leaves open

- **Integrations:** plan has Outlook + Slack + Supabase = 3 across 2 categories. That is the floor
  with no margin. A document store (Dropbox / OneDrive / SharePoint — all explicitly blessed in §8.3)
  adds a 4th across a 3rd category, and the pack literally has 126 invoices on a `DRIVE` channel.
  Cheap insurance if one connector misbehaves on the day.
- **Repo:** the plan references `C:\Users\User\...` paths. We need one shared team repo created from
  the template, both of us pushing, and a verified clean-clone start before the 8 Aug 23:59 freeze.
- **Seeding:** "import into Supabase, don't commit the dataset" needs an actual seed script plus a
  demo-reset path, or a clean clone has no data to run against.
- **Round 1's locked design decisions are not carried forward.** Line-level matching (not header
  total), PO currency authoritative, conservative money-protected, verdict precedence — these were
  hard-won and the oracle depends on them. They should be restated in the Round 2 spec, not assumed.

## Calendar

Today is **1 Aug**. Remote build **3–7 Aug**, offline build **8 Aug** (code freeze 23:59), finale
**9 Aug**. Two prep days left. The plan's 13 steps have no day allocation and no stated cut-list —
worth fixing before the 3rd, because with two people the risk is finishing wide instead of finishing.
