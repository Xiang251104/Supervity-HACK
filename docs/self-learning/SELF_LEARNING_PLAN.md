# Self-learning — implementation handover

**Status: paused, ~40% done. Not wired in. Nothing in the running system is affected.**
Picked up only if there is spare time before code freeze (**8 Aug 2026, 23:59**).

Why it was paused: the priority is Lim's Auto fixes (see `BUGS_FOR_LIM_2026-08-08.md`).
This is a **bonus** item, not a gate item. Do not start it while gate items are open.

---

## 1. What this is and what it is worth

The guide, §7.6:

> *"If a human correction also changes future behavior, that is self-learning and it earns bonus points."*

Scores in **two** places:

| Category | Points |
|---|---|
| Bonus | up to **+10** (one of three bonus paths) |
| Customizability → "auditability and breadth 5" | contributes |

**The rule being built:** when a reviewer has approved the *same vendor + same reason code*
N times, the next invoice carrying that reason is softened by one verdict step —
`HUMAN_REVIEW → PAY_READY`, or `PAYMENT_HOLD → HUMAN_REVIEW`.

Governed by two ordinary rows in `ap_policies`, so a judge switches it on in the same
UI as every other policy. No hidden model, no separate control panel.

---

## 2. Facts already verified — do not re-derive these

Each was confirmed against the live stack on 8 Aug. Re-checking costs tokens for no gain.

| Fact | Evidence |
|---|---|
| The gate is a **pure function**, called in **our backend** after Auto returns | `evaluate(...)` at `app/routers/ap_runs.py:271` |
| Everything downstream flows from `gate.verdict`, not Auto's proposal | `ap_runs.py:274–327` (decision, money, workbench routing) |
| **No Supervity Auto changes needed.** Zero dependency on Lim | follows from the two rows above |
| Workbench resolve writes `decision.resolution_action` | `app/routers/ap_workbench.py:198` |
| So learning reads **one table**, `ap_decisions`, no join | `Decision.lifnr` + `.reason_codes` + `.resolution_action` |
| Alembic head is `d4e5f6a7b8c9` | `grep down_revision alembic/versions/*.py` |
| `note()` inside `evaluate()` writes every policy into the Workbench item's `context` | `policies.py:222–235`, stored at `ap_runs.py:313–322` |

**Correction (8 Aug):** an earlier draft of this doc claimed the Workbench already
*renders* that list and that no UI work was needed. It does not — before the policy
panel was added, `workbench/page.tsx` showed only `policy_version_label`. If the panel
described in `docs/` is in place by the time you read this, the learning rule inherits it
for free; verify that first rather than assuming either way.

### The demo cluster (real data, already seeded)

```
vendor 4110005 · VENDOR_MASTER_DUPLICATE · 4 invoices, all HUMAN_REVIEW
  5110000000  ["RECEIPT_VARIANCE", "VENDOR_MASTER_DUPLICATE"]
  5110000004  ["VENDOR_MASTER_DUPLICATE"]      <- only one code
  5110000027  ["VENDOR_MASTER_DUPLICATE"]      <- only one code
  5110000029  ["VENDOR_MASTER_DUPLICATE"]      <- only one code, keep as the demo subject
```

That vendor is genuinely duplicated in the vendor master — a **data-quality artefact,
not fraud**. Approving three teaches the system to clear the fourth. This is the whole
demo, and it is honest.

Full observed code vocabulary (18 codes, 52 invoices) is in §5 below.

---

## 3. What is already written

### `app/services/learning.py` — **DONE, complete, untested**

Inert: nothing imports it. Contains:

- `LEARNABLE_CODES` — the safety **allowlist** (5 codes)
- `NEVER_LEARNABLE` — named explicitly so intent is visible in review
- `is_learnable(code)`
- `LearnedSignal` dataclass — `code, lifnr, confirmations, examples`, `.meets(threshold)`
- `learned_signals(db, lifnr, codes, *, exclude_belnr)` — counts prior **approvals** only
- `LearningOutcome` dataclass — `.applied`, `.verdict`, `.covered`, `.blocked_by`, `.explanation`, `.observed`
- `apply_learning(verdict, codes, signals, *, mode, threshold)` — **pure**, no DB, no clock

Read the module docstring before changing anything; the three safety rules are stated there.

### `docs/self-learning/e5f6a7b8c9d0_add_learning_policies.py` — **DONE, deliberately parked**

⚠️ **This file was moved OUT of `alembic/versions/` on purpose.**

If it sits in `alembic/versions/`, the next `alembic upgrade head` seeds two policies that
nothing evaluates — i.e. two **decoration policies**, the exact defect fixed in commit
`27492ff`. A judge clicking them would find them inert.

**Move it back into `alembic/versions/` only in the same commit as step 4.1 below.**

Seeds two policies:

| Key | Type | Default | Options |
|---|---|---|---|
| `LEARNED-OVERRIDES` | enum | `"advise"` | `off` / `advise` / `apply` |
| `LEARN-CONFIRMATIONS` | number | `3` | — |

Default is `advise` deliberately: on a clean clone the system *reports* what it could have
learned without silently changing a money decision. Turning it to `apply` is then a
deliberate, logged, no-code act — which doubles as the §11.5 "judge edits a policy and asks
you to re-run" scenario.

---

## 4. What is left — roughly 60–70 minutes

### 4.1 Add the learning block to the gate — `app/services/policies.py`

Add the import at the top:

```python
from .learning import LearnedSignal, apply_learning
```

Extend the signature of `evaluate()` (`policies.py:205`):

```python
def evaluate(
    snapshot: PolicySnapshot,
    proposed_verdict: str,
    reason_codes: list[str],
    invoice: dict[str, Any] | None = None,
    learned: dict[str, "LearnedSignal"] | None = None,
) -> GateResult:
```

Insert this block **after DOA-BAND (`policies.py:340`) and before the
`if verdict == "PAY_READY":` block at line 342.** Position matters — see the comment.

```python
    # --- LEARNED-OVERRIDES / LEARN-CONFIRMATIONS --------------------------
    # Runs last, on the verdict every other policy has already settled, so it can
    # only ever soften a finished decision -- never pre-empt a control that has not
    # been evaluated yet. Both policies are logged every run, fired or not, because
    # a control nobody can see the reasoning of is not auditable.
    mode = snapshot.get("LEARNED-OVERRIDES", "advise")
    confirmations = int(snapshot.get("LEARN-CONFIRMATIONS", 3))
    outcome = apply_learning(
        verdict, codes, learned or {}, mode=mode, threshold=confirmations
    )
    if outcome.applied:
        verdict = outcome.verdict
    note("LEARNED-OVERRIDES", outcome.applied, mode, outcome.observed,
         "allow" if outcome.applied else "advise", outcome.explanation)
    note("LEARN-CONFIRMATIONS", outcome.applied, confirmations,
         max((s.confirmations for s in outcome.covered), default=0),
         "allow" if outcome.applied else "advise",
         f"A reason must be approved {confirmations} times for the same vendor "
         f"before it is treated as settled.")
```

Then move the migration back:

```bash
mv docs/self-learning/e5f6a7b8c9d0_add_learning_policies.py alembic/versions/
```

### 4.2 Wire the run pipeline — `app/routers/ap_runs.py`

At line 271, replace the single `evaluate(...)` call with:

```python
    learned = learned_signals(
        db, canonical.get("lifnr"), reason_codes, exclude_belnr=belnr
    )
    gate = evaluate(
        snapshot, proposed_verdict, reason_codes, invoice_context, learned=learned
    )
```

`canonical.get("lifnr")` is already in scope here (it is used again at line 281).
Import `learned_signals` from `..services.learning` at the top of the module.

`exclude_belnr` stops an invoice being evidence for itself on a re-run — needed
because re-running is the demo.

### 4.3 Plain-language labels

Codes must never reach the user — see the vocabulary rule established earlier.

- `frontend/src/lib/ap-language.ts` → add to `POLICY_VALUE_LABELS`:
  `off` → "Ignore past decisions", `advise` → "Show past decisions only",
  `apply` → "Act on past decisions"
- `app/services/language.py` → add both keys to `POLICY_NAMES`:
  `LEARNED-OVERRIDES` → "Learn from reviewer decisions",
  `LEARN-CONFIRMATIONS` → "Approvals before learning"

### 4.4 Tests — `tests/test_learning.py`

`apply_learning` is pure, so most of this is fast table-driven testing. **The safety
tests are not optional** — "the AI learned to ignore a fraud control" loses far more
than this feature wins.

Must cover:

1. **Every code in `NEVER_LEARNABLE` is refused**, even at 99 confirmations. Parametrise
   over the whole set so a future edit to the set cannot silently weaken it.
2. **Partial coverage does not soften.** `["VENDOR_MASTER_DUPLICATE", "BEC_SUSPECTED"]`
   with the first well-evidenced stays `PAYMENT_HOLD`.
3. **One step only.** `PAYMENT_HOLD` → `HUMAN_REVIEW`, never `PAY_READY`.
4. **`DATA_ERROR` is never softened** (absent from `_SOFTEN_ONE_STEP`).
5. **Below threshold does nothing.** 2 confirmations against a threshold of 3.
6. **`advise` mode never changes the verdict** but does explain itself.
7. **`off` mode produces no learning at all.**
8. **Rejections and `request_info` are not evidence** — DB-level test of
   `learned_signals`; only `resolution_action == "approve"` counts.
9. **`exclude_belnr` works** — an invoice is not evidence for itself.
10. **The same invoice counts once** even if it appears twice.

Run: `pytest tests/test_learning.py -v` — and delete any `_p.db` / `_t.db` temp files
afterwards, as previous runs have left them behind.

### 4.5 Live verification

```bash
docker compose exec api alembic upgrade head
docker compose exec -T postgres psql -U user -d app_db \
  -c "select key, value from ap_policies where key like 'LEARN%';"
```

Then:

1. In the Workbench, **approve** 5110000000, 5110000004, 5110000027 (note required).
2. Re-run 5110000029 → expect verdict unchanged (`advise` is the default) but the
   Workbench "What the AI checked" list now shows the learning explanation.
3. On the AI Policies page, set **Learn from reviewer decisions → Act on past decisions**.
4. Re-run 5110000029 → expect **`HUMAN_REVIEW` → `PAY_READY`**, touchless rate up.
5. Confirm `ap_policy_evaluations` has rows for both new keys on both runs.

Steps 2→4 are the demo. It shows a human correction changing future behaviour *and*
live no-code configurability in one sequence.

---

## 5. Safety rules — do not relax these

**Allowlist, never blocklist.** Auto's reason-code vocabulary has already drifted once
(`RECEIPT_VARIANCE` and `NEAR_DUP_SUSPECT` appeared unannounced — see Defect 2 in
`BUGS_FOR_LIM_2026-08-08.md`). A blocklist would be a standing invitation to learn away
a control nobody remembered to exclude. Unclassified codes are **not** learnable.

**Learnable (5)** — recurring properties of a vendor or its data, not controls:
`VENDOR_MASTER_DUPLICATE`, `RECEIPT_VARIANCE`, `PO_OUT_OF_VALIDITY`, `RETRO_PO`,
`DATE_AMBIGUOUS`

**Never learnable** — anything touching bank details, vendor blocks, duplicates, entity
or currency mismatch, delegation of authority, or extraction confidence. Approving a bank
change three times must never teach the system to stop asking about bank changes; that is
precisely the pattern a payment-redirect fraud would exploit.

Full observed vocabulary, with counts across the 52 seeded invoices:

```
RECEIPT_VARIANCE 17 · LOW_CONFIDENCE 8 · PO_LINE_NO_MATCH 5 · PO_CURRENCY_MISMATCH 5
MISSING_INPUT 4 · GL_CODING_REQUIRED 4 · PO_OUT_OF_VALIDITY 4 · NON_PO_APPROVAL 4
VENDOR_MASTER_DUPLICATE 4 · VENDOR_BLOCKED 4 · ENTITY_MISMATCH 3 · CREDIT_MEMO 3
PO_VENDOR_MISMATCH 3 · DATE_AMBIGUOUS 2 · BEC_SUSPECTED 2 · NEAR_DUP_SUSPECT 2
BANK_ACCOUNT_UNKNOWN 1 · BANK_MISMATCH 1
```

`GL_CODING_REQUIRED` and `CREDIT_MEMO` are excluded on purpose: they are harmless, but
softening them means paying non-PO spend without an approver, which breaks the DOA band.

---

## 6. Known dependency

Learning needs resolved items to learn from. As of 8 Aug the Workbench had
**41 open + 2 parked + 0 resolved**, so §4.5 step 1 is mandatory before anything is
observable. It costs about three minutes, and at least one Workbench resolution is a
**mandatory gate item** anyway — so it is not extra work.

If the data is re-seeded after Lim's fixes land, the four-invoice 4110005 cluster must be
re-checked; the demo depends on three of them carrying `VENDOR_MASTER_DUPLICATE` alone:

```sql
select belnr, lifnr, verdict, reason_codes::text
from ap_decisions where lifnr = '4110005' order by belnr;
```

---

## 7. If you have to cut it

The feature degrades cleanly. In descending order of value per minute:

1. **Steps 4.1 + 4.2 + migration only** (~30 min) — learning works and is logged, in
   `advise` mode. Demonstrable, zero risk to any money decision. **If time is very
   short, ship only this.**
2. Add **4.4 safety tests** (~20 min) — required before switching to `apply` in front
   of a judge.
3. Add **4.3 labels** (~10 min) — polish; without it two raw policy keys show in the UI,
   which breaks the plain-language rule applied everywhere else.

Do **not** ship the migration without 4.1. Two inert policies are worse than none.
