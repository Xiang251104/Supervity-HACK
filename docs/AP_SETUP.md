# AP Control Tower — setup

What is already built in this repo, and what to do next. Nothing here needs Supervity
Auto — all of it can be done while the token allowance is out.

## What's in place

| | |
|---|---|
| `app/models/ap.py` | 9 tables: policies, policy versions, runs, run events, decisions, policy evaluations, workbench items, insights, integrations |
| `alembic/versions/d4e5f6a7b8c9_*.py` | migration + seeds 7 policies and the 4 integration registry rows |
| `app/services/supervity.py` | Auto client: `multipart/form-data` execute, SSE parsing, 60/min rate limiter, health check |
| `app/services/policies.py` | the Policies engine: snapshot → gate → evaluation logging |
| `tests/test_ap_policies.py` | 11 tests, all passing, no DB required |

## 1. Start the stack

```powershell
Copy-Item .env.example .env
# set NEXTAUTH_SECRET (any base64 string) — the rest can stay blank for now
.\scripts\start.ps1
```

Check: dashboard http://localhost:3001 · API docs http://localhost:8001/api/docs

## 2. Apply the migration

```powershell
docker compose exec backend alembic upgrade head
```

Verify the seeds landed:

```powershell
docker compose exec postgres psql -U user -d app_db -c "select key, value, version from ap_policies order by key;"
docker compose exec postgres psql -U user -d app_db -c "select key, category, status from ap_integrations;"
```

You should see 7 policies and 4 integrations.

## 3. Seed Supabase (this is what unblocks Lim)

From the war room folder `round2/supabase/`:

1. Open the Supabase SQL editor, paste **all** of `schema_r2.sql`, run it.
   It drops and recreates all 14 tables with indexes on every join key the Operators filter by.
2. Import each CSV from `round2/supabase/import/` into the matching table
   (Table editor → Import data from CSV). Headers already match the column names.
3. Run the verification query at the bottom of `schema_r2.sql` and check the counts:

   | table | rows | | table | rows |
   |---|---|---|---|---|
   | ap_invoices | 450 | | company_codes | 6 |
   | vendor_master | 80 | | fx_rates | 894 |
   | po_headers | 153 | | bank_master | 114 |
   | po_items | 276 | | email_headers | 78 |
   | goods_receipts | 135 | | discount_schedule | 79 |
   | gl_master | 14 | | approval_log | 141 |
   | doa_matrix | 10 | | pricing_conditions | 135 |

4. Send Lim the confirmed table and column names.

**Why `wrbtr` is TEXT and not numeric:** 52 invoices carry comma-decimal amounts like
`327845,70`, and 88 carry mixed date formats. The mess is deliberate — the Operators
normalize it at runtime, which is exactly what is being judged. Do not pre-clean the source.

## 4. Wire the Supervity credentials (once Lim sends them)

```
SUPERVITY_API_KEY=...
SUPERVITY_ACTIVE_ORG=...
SUPERVITY_ORCHESTRATOR_WORKFLOW_ID=...
```

Then smoke-test the connection before building anything on top:

```powershell
docker compose exec backend python -c "import asyncio; from app.services.supervity import SupervityClient; print(asyncio.run(SupervityClient().health()))"
```

Expect `('healthy', <ms>, {...})`. If it returns `down`, fix that before writing another line —
everything downstream depends on it.

## 5. Things that will bite you

- **The execute endpoints take `multipart/form-data`, not JSON.** The client already does this.
  If you hand-roll a call with `json=`, you get a 4xx and a confusing error.
- **60 requests/minute per IP.** `app/services/supervity.py` has a limiter set to 55/min.
  Do not bypass it to batch 450 invoices faster — you will get throttled mid-demo.
- **The SSE payload shape is not fully documented.** The client normalizes what it recognises
  and keeps the full frame in `payload`. Once a real run comes back on the 3rd, look at a few
  raw frames and tighten `_TYPE_MAP` and `_dig()` in the client.

## 6. Data integrity rule — read this before seeding decisions

`ap_decisions.source` is either `auto_run` or `oracle_backfill`.

Backfilling decisions from `EXPECTED_ORACLE_R2.csv` is fine and useful — it lets the dashboard,
Workbench and Insights be built and tested before Auto is available. But:

> **Every `oracle_backfill` row must be purged before submission.**
> Shipping computed demo data as agent output is explicitly disqualifying.

```sql
delete from ap_decisions where source = 'oracle_backfill';
```

## 7. Next code tasks, in order

1. `app/routers/ap_runs.py` — `POST /api/ap/runs` (build snapshot → call Auto → persist run + events →
   gate → persist decision → create Workbench item), plus `GET /api/ap/runs/{id}` and an SSE passthrough.
2. `app/routers/ap_policies.py` — list / update / history. `update_policy()` already handles versioning.
3. `app/routers/ap_workbench.py` — queue, detail, resolve. Resolution writes only the `human_*` columns.
4. `app/services/insights.py` — the three computed insights.
5. `app/routers/ap_data_manager.py` — health checks per integration.
