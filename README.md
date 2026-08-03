# AP Control Tower

**Autopilot Asia Hackathon 2026 · Round 2 · Track 1 — Finance / Accounts Payable**

A governed Accounts Payable operation: an AI Employee that screens every incoming invoice,
clears the clean ones without a human, and escalates the genuinely risky ones to a person with
the reasoning already written up.

Built on the official [AutoPilot Template](https://github.com/digitamizers/AutoPilot-Template).

---

## The two layers

| Layer | Runs on | What it is |
|---|---|---|
| **The agent** | Supervity Auto | 1 Orchestrator + 5 Operator Agents doing the actual AP work |
| **The Command Center** | this repository | Dashboard · AI Policies · AI Insights · AI Manager · Data Manager · Workbench |

All orchestration lives on Auto. Everything in this repo is the operation *around* the agent —
the rules a business owns, the record of what happened, and the queue where a human steps in.

### The five Operators

| # | Operator | Job |
|---|---|---|
| 1 | AP · Intake & Normalize | parse messy amounts and dates, classify, build matching keys |
| 2 | AP · Duplicate & Fraud Screen | exact and near-duplicate detection across channels |
| 3 | AP · Three-Way Match | invoice ↔ PO **line** ↔ goods receipt |
| 4 | AP · Bank Change Verification | payment-redirection fraud, via 4-signal correlation |
| 5 | AP · Entity & Approval Control | booking entity, FX, delegation-of-authority band |

---

## Start here

**`ap/DELIVERY_PLAN_R2.md`** is the single source of truth. Part A is the delivery plan;
Part B is the exact text to paste into Supervity Auto to build each Operator.

| File | What it is |
|---|---|
| [`ap/DELIVERY_PLAN_R2.md`](ap/DELIVERY_PLAN_R2.md) | the plan + all six Auto build commands |
| [`ap/DATA_PROFILE_R2.md`](ap/DATA_PROFILE_R2.md) | trap census — every edge case in the pack, counted |
| [`ap/oracle/build_oracle_r2.py`](ap/oracle/build_oracle_r2.py) | independent answer key for all 450 invoices |
| [`ap/supabase/schema_r2.sql`](ap/supabase/schema_r2.sql) | Supabase schema for the 14 AP tables |
| [`docs/AP_SETUP.md`](docs/AP_SETUP.md) | step-by-step setup |
| [`docs/template-readme.md`](docs/template-readme.md) | the original template setup guide |

---

## Quick start

```bash
cp .env.example .env          # Windows: Copy-Item .env.example .env
# set NEXTAUTH_SECRET to any base64 string; the rest can stay blank to start
docker compose up --build -d  # Windows: .\scripts\start.ps1
docker compose exec backend alembic upgrade head
```

| Service | URL |
|---|---|
| Command Center | http://localhost:3001 |
| API docs | http://localhost:8001/api/docs |
| Postgres | `localhost:5432` |

The migration seeds 10 policies and the integration registry. Verify:

```bash
docker compose exec postgres psql -U user -d app_db -c "select key, value, version from ap_policies order by key;"
```

### Running the tests

```bash
docker compose exec backend pytest tests/ -q
```

Or locally without Docker:

```bash
python -m venv .venv && .venv/Scripts/pip install -r packages/requirements.txt
.venv/Scripts/python -m pytest tests/ -q
```

---

## ⚠️ The dataset is deliberately not in this repository

The Supervity Round 2 data pack **may not be redistributed** (Round 2 Participant Guide §9.4),
and this repo is public. The organizer pack, anything derived from it, and the briefs are all
gitignored.

Every team already has the pack. To use it, point the scripts at your own copy:

```bash
python ap/supabase/generate_import_csvs.py /path/to/csv   # -> ap/supabase/import/
python ap/oracle/build_oracle_r2.py       /path/to/csv    # -> EXPECTED_ORACLE_R2.csv
```

Both also accept an `AP_DATASET_DIR` environment variable. Load the generated CSVs into
Supabase after running `ap/supabase/schema_r2.sql`.

**The data reaches the Operators through a live Supabase integration — never read from disk
at runtime.**

---

## Standing rules

- **Never hardcode to sample rows.** Judges may run a record we did not prepare.
- **All thresholds live in the policy store**, never in Operator prose or in code.
- **Never invent a value for a missing field** — pause and route to the Workbench.
- **`ap_decisions.source` must be `auto_run` before submission.** Rows backfilled from the
  oracle for development are marked `oracle_backfill` and must be purged.
- **Never commit the dataset or an API key.** The build must run from a clean clone.

## Outcome metrics

Touchless rate · money protected · cash optimized. Baseline from the oracle on the public pack:

| GR policy | Touchless |
|---|---|
| `strict_require_gr` | 27.8% |
| `fo_aware` | 40.2% |

One editable policy moves it 12 points. Money protected: MYR 40.07M (+ SGD/INR/EUR/USD).
Fraud: 4 invoices held across 3 spoofed bank-change attempts, 0 false positives against
7 legitimate bank changes.
