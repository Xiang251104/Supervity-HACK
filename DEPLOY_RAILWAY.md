# Deploying the AP Command Center to Railway

Follow this top to bottom. Order matters in two places and both are called out.

**Why Railway.** One Orchestrator run holds the HTTP connection open for its whole
duration — measured at 83s for a clean invoice and 187s for the bank-fraud one.
Render (~100s) and Vercel (60s) cut the connection before the slow runs finish.
Railway does not impose a request timeout, so it is the safe choice until runs
are made asynchronous.

**Never paste secrets into this file.** Every value marked `← from .env` is copied
from your local `.env`, which is gitignored and stays that way.

---

## Before you start

- The branch is pushed to GitHub (`Xiang251104/Supervity-HACK`).
- You are signed in at [railway.app](https://railway.app) with GitHub.
- Your local `.env` is open in another window to copy values from.

---

## Step 1 — Project and database

1. Railway dashboard → **New Project** → **Deploy from GitHub repo**
2. Pick **Supervity-HACK**. Railway will try to build something — ignore it for now.
3. In the project canvas: **New** → **Database** → **Add PostgreSQL**.

Postgres provisions itself and exposes a `DATABASE_URL` that other services can
reference. You never copy this value by hand.

---

## Step 2 — Backend service

If Railway already created a service from the repo, rename it to `backend` and
use it. Otherwise **New** → **GitHub Repo** → Supervity-HACK.

**Settings → Source**
| Field | Value |
|---|---|
| Root Directory | `/` |
| Branch | the branch you are deploying |
| Builder | Dockerfile |
| Dockerfile Path | `Dockerfile` |

**Settings → Networking** → **Generate Domain**. Copy the URL, e.g.
`https://backend-production-xxxx.up.railway.app`. You need it in Step 3.

**Variables** — add these. `DATABASE_URL` uses Railway's reference syntax, so type
it exactly as shown; it resolves to the Postgres you just created.

```
APP_ENV=production
AUTH_BYPASS=true
LOG_LEVEL=INFO
DATABASE_URL=${{Postgres.DATABASE_URL}}

# Gunicorn kills a worker after this many seconds. The default is 120, which is
# LESS than a bank-fraud run (187s), so leaving it unset truncates real runs.
GUNICORN_TIMEOUT=600

SUPERVITY_API_KEY=            ← from .env
SUPERVITY_ACTIVE_ORG=Sixteen
SUPERVITY_ORCHESTRATOR_WORKFLOW_ID=019fdb5f-a085-7000-ba58-acedb3f006dd
SUPERVITY_BASE_URL=https://auto-workflow-api.supervity.ai
SUPERVITY_TIMEOUT_SECONDS=300

INTEGRATION_HEALTH_MAX_AGE_HOURS=24
```

`SUPERVITY_BASE_URL` must be the `auto-workflow-api` host. `auto.supervity.ai` is
the web app and returns a generic 400 to every API call, with or without a valid
key — a wrong host is indistinguishable from a bad key.

Deploy. In **Deploy Logs** you are looking for:

```
Running upgrade ... -> d4e5f6a7b8c9, Add AP Control Tower tables
Starting production server
```

That migration creates the tables *and* seeds the 10 policies. No manual DB setup.

Check it: open `https://<backend-url>/api/health` → `{"status":"ok"}`.

---

## Step 3 — Frontend service

⚠️ **Do not start this until the backend has a public URL.** `NEXT_PUBLIC_API_URL`
is a *build* argument compiled into the JavaScript bundle. Change it later and you
must rebuild — editing the variable alone does nothing.

**New** → **GitHub Repo** → Supervity-HACK (the same repo, a second service).

**Settings → Source**
| Field | Value |
|---|---|
| Root Directory | `/frontend` |
| Builder | Dockerfile |
| Dockerfile Path | `Dockerfile` |

**Settings → Networking** → **Generate Domain**. This URL is what you give judges.

**Variables** — Railway passes these as both build args and runtime env:

```
NEXT_PUBLIC_API_URL=https://<your-backend-url>     ← no trailing slash
NEXTAUTH_URL=https://<your-frontend-url>
NEXTAUTH_SECRET=                                    ← from .env
NODE_ENV=production
NEXT_PUBLIC_BASE_PATH=
```

**Settings → Build** → set **Docker Target** to `prod`.

Deploy, then open the frontend URL. The dashboard should load with zeros — an
empty Command Center, which is correct: it has no runs yet.

---

## Step 4 — Point the backend back at the frontend

Return to the **backend** service variables and add:

```
FRONTEND_URL=https://<your-frontend-url>
```

This is the CORS allow-list. Without it the browser blocks the dashboard's API
calls and every tile silently shows nothing. Redeploy the backend.

---

## Step 5 — Verify before trusting it

| Check | URL | Expected |
|---|---|---|
| Backend alive | `<backend>/api/health` | `{"status":"ok"}` |
| Policies seeded | `<backend>/api/ap/policies` | 10 policies |
| Metrics honest | `<backend>/api/ap/metrics` | zeros, not sample data |
| Dashboard | `<frontend>` | loads, tiles at zero |
| **No CORS errors** | browser DevTools → Console | clean |

That last one is the usual failure and it is silent — the page renders fine while
every number stays zero. Always open the console once.

---

## Step 6 — Populate it with real runs

Seed the hosted database from your laptop. Runs execute locally against Auto and
write straight to the hosted Postgres, so no gateway sits in the path:

```powershell
cd C:\Users\kianx\Projects\ap-command-center
.\.venv\Scripts\python.exe scripts\seed_demo_runs.py `
  --range 5110000000:36 5110000150 5110000158 5110000159 5110000164 `
  --base-url https://<your-backend-url>
```

About 25 minutes for 40 invoices, unattended. Re-runnable: an already-used run id
returns 409 and is reported as skipped.

**Seed only after Lim's final Operator changes are published**, otherwise the
dashboard shows decisions the current agent would no longer make.

---

## If something breaks

| Symptom | Cause | Fix |
|---|---|---|
| Build fails, no logs | Root Directory wrong | `/` backend, `/frontend` frontend |
| Backend boots then exits | `DATABASE_URL` unresolved | Use `${{Postgres.DATABASE_URL}}` verbatim |
| Dashboard loads, all zeros | CORS | Set `FRONTEND_URL` on the backend (Step 4) |
| Tiles zero, console 404s | `NEXT_PUBLIC_API_URL` wrong or has a trailing slash | Fix it and **rebuild** the frontend |
| Runs fail near 120s | `GUNICORN_TIMEOUT` unset | Set it to 600 |
| `no such table` | Migration did not run | `APP_ENV` must be `production` or `development`, never blank |
| Auto returns 400 on every call | Wrong `SUPERVITY_BASE_URL` | Must be `auto-workflow-api.supervity.ai` |
