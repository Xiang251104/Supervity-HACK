# Data Manager Live-Evidence Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Persist real Outlook provenance and Slack exception-delivery evidence from AP runs.

**Architecture:** The AP run router derives the default source only after canonical output exists and appends a real Slack integration event only after a Workbench item is opened. A focused Slack formatter applies the established account redaction before transport.

**Tech Stack:** FastAPI, SQLAlchemy, pytest, httpx.

---

### Task 1: Specify and build the exception alert formatter

**Files:**
- Modify: `tests/test_slack.py`
- Modify: `app/services/slack.py`

- [x] **Step 1: Write failing formatter tests** covering actual identifiers, safe fallback, and account-number redaction.
- [x] **Step 2: Run** `pytest tests/test_slack.py -q` and observe the missing-builder failure.
- [x] **Step 3: Implement** `build_exception_alert` using the existing redactor across the composed text.
- [x] **Step 4: Run** `pytest tests/test_slack.py -q` and confirm it passes.

### Task 2: Specify and build run-derived evidence

**Files:**
- Create: `tests/test_ap_runs_live_evidence.py`
- Modify: `app/routers/ap_runs.py`

- [x] **Step 1: Write failing router tests** for EMAIL derivation/default API, non-default precedence, Slack success/failure/unconfigured event payloads, pay-ready omission, and sequence order.
- [x] **Step 2: Run** `pytest tests/test_ap_runs_live_evidence.py -q` and observe feature-missing failures.
- [x] **Step 3: Implement** normalized EMAIL derivation, best-effort send handling, and append-only integration event recording.
- [x] **Step 4: Run** `pytest tests/test_ap_runs_live_evidence.py tests/test_slack.py -q` and confirm it passes.

### Task 3: Record completion evidence

**Files:**
- Modify: `PROJECT_REQUIREMENTS.md`
- Modify: `ARCHITECTURE_AND_CODING_DESIGN.md`
- Modify: `PROJECT_STATUS.md`

- [x] **Step 1: Update** requirements, design, and status with the implemented behavior and verification results.
- [x] **Step 2: Run** focused pytest suite and `git diff --check`.
- [ ] **Step 3: Commit** all task files with `git commit -m "feat: record live Outlook and Slack evidence"`.
