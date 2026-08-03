# What to reuse from `Weychenglim/AIEmployee`

Repo cloned and read in full (`main` @ `bb7708e`; `codex/learning-lab` is already merged, no diff).
Verdict per file, so nobody spends build days porting something that fails the gate.

## What that repo actually is

- **`frontend/`** — `ops-triage-dashboard`, a Next.js 14 **Operations** triage UI (~3,350 LOC of
  components). Pages: audit, exceptions, learning, metrics, policies, queue, requests/[id], settings.
  **No AP pages exist.**
- **`backend/`** — FastAPI, Operations domain: clarifications, classifier, policy evaluator,
  Google Sheets integration.
- **`docs/superpowers/`** — the AP Control Tower plans and specs. **Documentation only — there is no
  AP code anywhere in the repo.**

Two findings that decide most of this document:

1. **There is no Supervity integration code.** `supervity_mode`, `supervity_webhook_url` and
   `supervity_api_key` exist in `core/config.py` and are **never read anywhere else**. The documented
   `webhook` mode was never implemented; `TriageWorkflow` runs the whole orchestration **in-process
   in Python**.
2. **The policies are a hardcoded Python list.** `domain/policy_matrix.py` is a `list[PolicyRule]`
   constant, and `app/policies/page.tsx` contains no `fetch`, `POST`, `input`, `onChange` or save
   handler — it renders that list read-only.

## Stack divergence (nothing is drop-in)

| | AutoPilot template | AIEmployee |
|---|---|---|
| Next.js | 15.5.18 | 14.2.5 |
| React | 19 | 18.3.1 |
| UI kit | **shadcn/ui** (Radix + CVA + tailwind-merge) | custom `components/primitives.tsx` |
| Motion | `framer-motion` 11 | `motion` 12 |
| Charts | **`recharts` 3** (already installed) | none |
| Layout | `frontend/src/…`, `@/` → `src/` | `frontend/app/…` at root |
| Auth | next-auth 4 + `AUTH_BYPASS` | custom `AuthProvider` + `X-API-Key` |

Every component ported has to be rewritten against shadcn primitives. Budget for a rewrite, not a copy.

---

## ✅ Port — real value, fills a real template gap

### 1. The SSE live event stream — the single best thing in the repo
`backend/app/api/routes.py` (`_sse`, `/events/stream`, `_stream_audit_events_from_queue`, ~lines 538–600)
+ `frontend/components/LiveStreamProvider.tsx` (108 LOC) + `EventToast.tsx` (104) + `LiveActivityFeed.tsx`

**The template has no live stream** — its only `StreamingResponse` uses are audit CSV/XLSX export.
Round 2 is scored on "a dashboard that moves when the agent runs" and a "coherent end-to-end run".
This is a working shared-EventSource pattern with auto-reconnect, keep-alive frames and SSR guards.
Swap the event-type list (`intake`, `ai_decision`, `policy_decision`…) for AP step events streamed
out of the Auto run. ~250 LOC, domain-agnostic, saves a day.

### 2. `AuditTimeline.tsx` (70 LOC)
Right shape for a per-invoice decision trace. Rewrite the markup against shadcn `Card`; keep the structure.

### 3. The Learning Lab **shape** — `backend/app/api/learning.py` (273 LOC)
`FeedbackCreate` → `LearningSummary` (verdicts, `disagreement_rate`, `dimension_disagreements`) →
`ReplayEvaluation` (`ReplayCase` with `original` vs `current`, `changed`, `mismatches`).

This is exactly the **self-learning bonus** pattern: capture the human's expected outcome, replay past
cases against current rules, and measure what changed. Port the API shape and the replay idea; replace
the Ops fields (category / urgency / risk_level / owner) with AP ones (verdict, reason codes, protected
value). Do **not** port the classifier it calls.

---

## ⚠️ Adapt — take the interaction design, rewrite the code

| File | LOC | Take |
|---|---|---|
| `HumanActionPanel.tsx` | 210 | Workbench approve / modify / reject + reviewer note. Good information architecture, wrong primitives. |
| `QueueExplorer.tsx` | 363 | Queue with filters and detail selection — the Workbench list. |
| `ExceptionsList.tsx` | 71 | Compact exception rows. |
| `lib/sla.ts` | — | Ageing/SLA bucketing → reuse directly for the **invoice aging** dashboard tile. |
| `lib/api.ts` | — | Server-component reads + keyed writes pattern. The template already ships `lib/api-client.ts`, so take ideas only. |
| `PageSkeleton` / `skeletons.tsx` / `loading.tsx` | 122 | Loading conventions. Template has shadcn `skeleton.tsx` — mirror the convention, not the code. |

---

## ❌ Do not port — some of it would cost us the gate

| File / area | Why |
|---|---|
| `backend/app/orchestrator/workflow.py`, `domain/classifier.py`, `domain/clarifications.py` | **In-process Python orchestration.** Round 2's explicit Don't: *"Rebuild the Orchestrator or Operators outside Supervity Auto."* All orchestration must be on Auto. Carrying this over risks gate condition 1. |
| `domain/policy_matrix.py` + `domain/policy_evaluator.py` + `app/policies/page.tsx` | Hardcoded Python rules rendered read-only. Round 2 needs DB-backed policies, **editable in the UI with no code**, evaluated **before** the action, every evaluation logged. This is the 20-point criterion — build it fresh. |
| `integrations/google_sheets.py` | Google integrations are in beta for this event and explicitly discouraged (§8.3). |
| `frontend/package.json`, routing structure, `AppShell`, `Hero`, `command-center.tsx` (508 LOC) | Wrong Next/React major, wrong UI kit, Ops-specific. The guide says keep it looking like a Supervity product — use the template's design system. |
| `data/seed/requests.json`, Ops domain schemas, `IntakeForm`, `PilotSetupWizard` | Operations domain, no AP meaning. |
| `AuthProvider` / `AuthGate` / `X-API-Key` | Template ships next-auth + `AUTH_BYPASS=true`. Real auth is a bonus, not a requirement — don't spend time here. |

**Rough total:** ~500 LOC worth porting out of ~5,500. The repo's value is the **live-stream pattern
and the learning-replay idea**, not the application.

---

## What the docs in that repo tell us about the Round 1 Auto build

From `docs/superpowers/specs/2026-07-19-finance-ap-lean-competitive-scope-design.md` and
`plans/2026-07-19-task-11-header-only-mvp.md`, the Round 1 submission was deliberately cut to:

| Operator | Round 1 state |
|---|---|
| `AP - Normalize and Validate` | built |
| `AP - Duplicate Control` | built (full invoice population) |
| `AP - PO GR Match` | **rolled back to header-only** — vendor + currency compare. No PO lines, no price tolerance, no goods receipts, no pricing conditions. |
| Vendor Integrity | **deferred — never built** |
| Non-PO Coding & Approval | **deferred — never built** (non-PO routed straight to `HUMAN_REVIEW`) |
| `AP Control Tower Orchestrator - Core` | built, one invoice per execution |

Supabase tables actually used: `ap_invoices`, `po_headers`, `policy_profiles`, `invoice_decisions`,
`audit_events`. Vendor master, PO items, goods receipts, GL master, DOA matrix and pricing conditions
were imported but **unused**.

Three things follow:

1. **We have 3 business Operators, not 5.** The Round 2 plan's "3 extend + 3 new" is the right shape,
   but "extend" for `PO/GR Match` means building line matching, price tolerance and goods-receipt
   reconciliation **from nothing** — the largest single item in the build. Plan it first, not last.
2. **`VENDOR-BLOCK` has no home in the six-Operator plan.** 3 blocked vendors → 25 invoices, and it is
   one of the seven `POLICY_REF` values in `Approval_Log`. Fold it explicitly into one Operator
   (Bank-Change Verification is the natural host) or it will quietly go missing.
3. **Header-only matching must not survive into Round 2.** On the 450-invoice pack, comparing to the
   PO header total flags **77.3%** of invoices as a price variance. Line-level matches exactly one
   line for **93.2%**. The Round 2 plan already says to extend it — this is the number that says how
   urgently.

### One hard-won operational lesson worth keeping

The Task 11 plan repeatedly forbids `SUPABASE_TOKEN`, `SUPABASE_URL`, `httpx`, `requests`, `/rest/v1`
and generic HTTP, and insists on the **native Supabase OAuth `Query table` action**. Read: in Auto, the
native connector worked and hand-rolled token/HTTP queries did not. Start Round 2 on native connectors
and treat a generic-HTTP fallback as a last resort with a time-box.
