"""Tests for the grounded AI Manager chat.

The thing worth defending here is that it never speaks beyond the record: an
invoice it has not seen gets an admission, not a verdict; an empty database
gets zeros, not sample figures; and oracle-backfilled rows are invisible to it
exactly as they are to the dashboard.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.core.database import get_db
from app.main import app
from app.middleware import AuditMiddleware
from app.models.ap import Decision, Insight, Integration, Policy, Run, WorkbenchItem
from app.security import get_current_user, verify_access


@dataclass
class ChatHarness:
    client: TestClient
    session_factory: sessionmaker

    def ask(self, message: str, history: list[dict] | None = None, page: str | None = None) -> dict:
        response = self.client.post(
            "/api/ai/chat",
            json={
                "message": message,
                "history": history or [],
                "context": {"page": page or "/"},
            },
        )
        assert response.status_code == 200, response.text
        return response.json()

    def add_decision(
        self,
        *,
        belnr: str,
        verdict: str = "PAY_READY",
        reason_codes: list[str] | None = None,
        currency: str = "MYR",
        amount: float = 1000.0,
        money_protected: float = 0.0,
        spend_under_review: float = 0.0,
        evidence: dict[str, Any] | None = None,
        vendor_name: str | None = "Summit Steelworks",
        source: str = "auto_run",
        run_id: str | None = None,
    ) -> None:
        with self.session_factory() as db:
            db.add(
                Decision(
                    run_id=run_id or f"RUN-{belnr}",
                    belnr=belnr,
                    lifnr="4110000",
                    ebeln="46200048",
                    vendor_name=vendor_name,
                    bukrs="MY20",
                    currency=currency,
                    amount=amount,
                    verdict=verdict,
                    reason_codes=reason_codes or [],
                    evidence=evidence,
                    money_protected=money_protected,
                    spend_under_review=spend_under_review,
                    policy_version_label="Standard v1.1",
                    confidence=0.95,
                    source=source,
                    created_at=datetime(2026, 8, 8, 9, 0, tzinfo=timezone.utc),
                )
            )
            db.commit()

    def add_workbench_item(
        self, *, belnr: str, status: str = "open", priority: str = "critical"
    ) -> None:
        with self.session_factory() as db:
            db.add(
                WorkbenchItem(
                    run_id=f"RUN-{belnr}",
                    belnr=belnr,
                    title=f"Review {belnr}",
                    exception_type="BEC_SUSPECTED",
                    priority=priority,
                    recommendation="Confirm the bank details by phone before paying.",
                    status=status,
                    created_at=datetime(2026, 8, 8, 9, 0, tzinfo=timezone.utc),
                )
            )
            db.commit()

    def add_policy(self, *, key: str, value: Any, active: bool = True) -> None:
        with self.session_factory() as db:
            db.add(
                Policy(
                    key=key,
                    name=key.title(),
                    description="",
                    value_type="number",
                    value=value,
                    severity="escalate",
                    active=active,
                    version=1,
                )
            )
            db.commit()

    def add_insight(self, *, key: str, title: str, dismissed: bool = False) -> None:
        with self.session_factory() as db:
            db.add(
                Insight(
                    key=key,
                    title=title,
                    severity="critical",
                    body="Three spoofed bank-change attempts were caught.",
                    action_label="Review the vendors involved",
                    dismissed=dismissed,
                    computed_at=datetime(2026, 8, 8, 9, 0, tzinfo=timezone.utc),
                )
            )
            db.commit()

    def add_integration(self, *, key: str, name: str, status: str) -> None:
        with self.session_factory() as db:
            db.add(
                Integration(
                    key=key,
                    name=name,
                    category="channel",
                    purpose="",
                    status=status,
                )
            )
            db.commit()

    def add_run(self, *, run_id: str, invoice_ref: str) -> None:
        with self.session_factory() as db:
            db.add(
                Run(
                    run_id=run_id,
                    invoice_ref=invoice_ref,
                    status="completed",
                    trigger_source="api",
                    policy_version_label="Standard v1.1",
                    duration_ms=4200,
                    started_at=datetime(2026, 8, 8, 9, 0, tzinfo=timezone.utc),
                )
            )
            db.commit()


@pytest.fixture
def chat(tmp_path: Path):
    database_path = tmp_path / "ai-manager.db"
    engine = create_engine(
        f"sqlite:///{database_path.as_posix()}",
        connect_args={"check_same_thread": False},
    )
    test_session = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    for table in (Run, Decision, WorkbenchItem, Policy, Insight, Integration):
        table.__table__.create(engine)

    def override_get_db():
        db: Session = test_session()
        try:
            yield db
        finally:
            db.close()

    original_overrides = app.dependency_overrides.copy()
    original_user_middleware = app.user_middleware
    original_middleware_stack = app.middleware_stack
    app.dependency_overrides[get_db] = override_get_db
    app.dependency_overrides[get_current_user] = lambda: {"email": "reviewer@example.com"}
    app.dependency_overrides[verify_access] = lambda: None
    app.user_middleware = [m for m in original_user_middleware if m.cls is not AuditMiddleware]
    app.middleware_stack = None

    try:
        with TestClient(app) as client:
            yield ChatHarness(client, test_session)
    finally:
        app.dependency_overrides.clear()
        app.dependency_overrides.update(original_overrides)
        app.user_middleware = original_user_middleware
        app.middleware_stack = original_middleware_stack
        engine.dispose()
        database_path.unlink(missing_ok=True)


# --------------------------------------------------------------------------- #
# The demo question
# --------------------------------------------------------------------------- #


def test_explains_why_a_specific_invoice_was_held(chat: ChatHarness):
    chat.add_decision(
        belnr="5110000150",
        verdict="PAYMENT_HOLD",
        reason_codes=["BEC_SUSPECTED"],
        amount=1_234_293.69,
        money_protected=1_234_293.69,
        evidence={
            "bank_result": {
                "status": "FAIL",
                "explanation": "The sender domain does not match the vendor master.",
            },
            "match_result": {"status": "PASS", "explanation": "Matched PO line 30."},
        },
    )
    chat.add_workbench_item(belnr="5110000150")

    body = chat.ask("Why was invoice 5110000150 held?")

    assert "5110000150" in body["response"]
    assert "held" in body["response"]
    assert "possible payment-redirect fraud" in body["response"]
    assert "1,234,293.69" in body["response"]
    # The failing Operator's own words are surfaced; the passing one is not.
    assert "sender domain does not match" in body["response"]
    assert "Matched PO line 30" not in body["response"]
    # It shows its working.
    assert [c["name"] for c in body["tool_calls"]] == [
        "lookup_decision",
        "lookup_workbench_item",
    ]


def test_a_follow_up_question_carries_the_invoice_over(chat: ChatHarness):
    chat.add_decision(
        belnr="5110000164",
        verdict="PAYMENT_HOLD",
        reason_codes=["VENDOR_BLOCKED"],
        money_protected=500.0,
    )

    body = chat.ask(
        "Why was it held?",
        history=[
            {"role": "user", "content": "Tell me about invoice 5110000164"},
            {"role": "assistant", "content": "Invoice 5110000164 was held."},
        ],
    )

    assert "5110000164" in body["response"]
    assert "blocked vendor" in body["response"]


def test_an_unknown_invoice_gets_an_admission_not_a_verdict(chat: ChatHarness):
    body = chat.ask("Why was invoice 5119999999 held?")

    assert "no decision recorded" in body["response"]
    assert "will not guess" in body["response"]
    for verdict in ("PAY_READY", "PAYMENT_HOLD", "HUMAN_REVIEW"):
        assert verdict not in body["response"]


def test_a_resolved_exception_reports_the_ai_verdict_as_unchanged(chat: ChatHarness):
    chat.add_decision(belnr="5110000017", verdict="PAYMENT_HOLD", reason_codes=["ENTITY_MISMATCH"])
    chat.add_workbench_item(belnr="5110000017", status="resolved")

    body = chat.ask("What happened to invoice 5110000017?")

    assert "resolved" in body["response"]
    assert "unchanged" in body["response"]


# --------------------------------------------------------------------------- #
# Grounding
# --------------------------------------------------------------------------- #


def test_an_empty_system_reports_nothing_rather_than_sample_figures(chat: ChatHarness):
    body = chat.ask("What is our touchless rate?")

    assert "not processed any invoices yet" in body["response"]
    assert "%" not in body["response"]


def test_oracle_backfilled_rows_are_invisible_to_the_assistant(chat: ChatHarness):
    chat.add_decision(belnr="5110000002", verdict="PAY_READY", source="oracle_backfill")

    metrics = chat.ask("How many invoices have we processed?")
    assert "not processed any invoices yet" in metrics["response"]

    invoice = chat.ask("Explain invoice 5110000002")
    assert "no decision recorded" in invoice["response"]


def test_metrics_are_reported_per_currency_and_never_summed(chat: ChatHarness):
    chat.add_decision(belnr="A1", verdict="PAY_READY")
    chat.add_decision(
        belnr="A2", verdict="PAYMENT_HOLD", currency="MYR", money_protected=1000.0,
        reason_codes=["BEC_SUSPECTED"],
    )
    chat.add_decision(
        belnr="A3", verdict="PAYMENT_HOLD", currency="SGD", money_protected=500.0,
        reason_codes=["BEC_SUSPECTED"],
    )

    body = chat.ask("What is our touchless rate and how much money have we protected?")

    assert "3 invoices" in body["response"]
    assert "33.3%" in body["response"]
    assert "MYR 1,000.00" in body["response"]
    assert "SGD 500.00" in body["response"]
    assert "1,500" not in body["response"]


def test_reason_codes_reach_the_reader_in_plain_language(chat: ChatHarness):
    chat.add_decision(
        belnr="5110000020", verdict="HUMAN_REVIEW", reason_codes=["RECEIPT_MISSING"]
    )

    body = chat.ask("Explain invoice 5110000020")

    assert "no goods receipt recorded" in body["response"]
    assert "RECEIPT_MISSING" not in body["response"]


def test_bank_account_numbers_are_redacted_before_they_reach_the_screen(chat: ChatHarness):
    chat.add_decision(
        belnr="5110000332",
        verdict="PAYMENT_HOLD",
        reason_codes=["BANK_MISMATCH"],
        evidence={
            "bank_result": {
                "status": "FAIL",
                "explanation": "The invoice states account 640689414832, not the approved one.",
            }
        },
    )

    body = chat.ask("Explain invoice 5110000332")

    assert "640689414832" not in body["response"]
    assert "****4832" in body["response"]


# --------------------------------------------------------------------------- #
# The other surfaces
# --------------------------------------------------------------------------- #


def test_reports_the_workbench_queue(chat: ChatHarness):
    chat.add_workbench_item(belnr="B1")
    chat.add_workbench_item(belnr="B2", status="resolved")

    body = chat.ask("What is waiting in the workbench?")

    assert "B1" in body["response"]
    assert "possible payment-redirect fraud" in body["response"]


def test_reports_active_policies_only(chat: ChatHarness):
    chat.add_policy(key="PRICE-TOLERANCE", value=2)
    chat.add_policy(key="MIN-CONFIDENCE", value=0.7, active=False)

    body = chat.ask("Which policies are active?")

    assert "price tolerance" in body["response"]
    assert "minimum reading confidence" not in body["response"]
    assert "1** policies are active" in body["response"]


def test_reports_insights_that_have_not_been_dismissed(chat: ChatHarness):
    chat.add_insight(key="fraud", title="Three spoofed bank changes caught")
    chat.add_insight(key="stale", title="An old dismissed one", dismissed=True)

    body = chat.ask("What insights do you have?")

    assert "Three spoofed bank changes caught" in body["response"]
    assert "An old dismissed one" not in body["response"]


def test_reports_integration_health_from_the_registry(chat: ChatHarness):
    chat.add_integration(key="slack", name="Slack", status="healthy")
    chat.add_integration(key="outlook", name="Microsoft Outlook", status="unknown")

    body = chat.ask("Are the integrations healthy?")

    assert "Slack" in body["response"]
    assert "healthy" in body["response"]
    assert "Microsoft Outlook" in body["response"]
    assert "unknown" in body["response"]


def test_reports_recent_runs(chat: ChatHarness):
    chat.add_run(run_id="RUN-01", invoice_ref="5110000002")

    body = chat.ask("Show me recent activity")

    assert "5110000002" in body["response"]
    assert "completed" in body["response"]


def test_the_bank_risk_scan_counts_only_flagged_invoices(chat: ChatHarness):
    chat.add_decision(belnr="C1", verdict="PAY_READY")
    chat.add_decision(
        belnr="C2",
        verdict="PAYMENT_HOLD",
        reason_codes=["BEC_SUSPECTED"],
        money_protected=1_234_293.69,
        amount=1_234_293.69,
    )

    body = chat.ask("Show me the bank change fraud cases")

    assert "**1** of 2" in body["response"]
    assert "C2" in body["response"]
    assert "MYR 1,234,293.69" in body["response"]
    assert "C1" not in body["response"]


# --------------------------------------------------------------------------- #
# Behaviour at the edges
# --------------------------------------------------------------------------- #


def test_it_declines_rather_than_improvises_when_it_cannot_match(chat: ChatHarness):
    body = chat.ask("Write me a poem about accounts payable")

    assert "will not improvise" in body["response"]
    assert "Explain one invoice" in body["response"]
    assert body["tool_calls"] == []


def test_the_capability_list_is_offered_on_request(chat: ChatHarness):
    body = chat.ask("What can you help me with?", page="/workbench")

    assert "Explain one invoice" in body["response"]
    assert "workbench" in body["response"]


def test_an_empty_message_is_rejected_by_validation(chat: ChatHarness):
    response = chat.client.post("/api/ai/chat", json={"message": ""})
    assert response.status_code == 422
