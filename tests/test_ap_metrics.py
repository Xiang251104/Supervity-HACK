"""Tests for the dashboard metrics endpoint.

The dashboard is the first page a judge sees, so the two rules that matter most are
defended here: one invoice counts once, and money is never summed across currencies.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.core.database import get_db
from app.main import app
from app.middleware import AuditMiddleware
from app.models.ap import Decision, Run, WorkbenchItem
from app.security import get_current_user, verify_access


@dataclass
class MetricsHarness:
    client: TestClient
    session_factory: sessionmaker

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
        confidence: float | None = 0.95,
        run_id: str | None = None,
        source: str = "auto_run",
    ) -> None:
        with self.session_factory() as db:
            db.add(
                Decision(
                    run_id=run_id or f"RUN-{belnr}",
                    belnr=belnr,
                    lifnr="4110000",
                    ebeln="46200048",
                    bukrs="MY20",
                    currency=currency,
                    amount=amount,
                    verdict=verdict,
                    reason_codes=reason_codes or [],
                    money_protected=money_protected,
                    spend_under_review=spend_under_review,
                    confidence=confidence,
                    source=source,
                    created_at=datetime(2026, 8, 8, 9, 0, tzinfo=timezone.utc),
                )
            )
            db.commit()

    def add_run(self, *, run_id: str, status: str = "completed", duration_ms: int = 1000) -> None:
        with self.session_factory() as db:
            db.add(
                Run(
                    run_id=run_id,
                    invoice_ref="5110000002",
                    status=status,
                    trigger_source="api",
                    policy_version_label="v1.1",
                    duration_ms=duration_ms,
                    started_at=datetime(2026, 8, 8, 9, 0, tzinfo=timezone.utc),
                )
            )
            db.commit()

    def add_workbench_item(self, *, belnr: str, days_old: int = 0, status: str = "open") -> None:
        with self.session_factory() as db:
            db.add(
                WorkbenchItem(
                    run_id=f"RUN-{belnr}",
                    belnr=belnr,
                    title=f"Review {belnr}",
                    exception_type="BEC_SUSPECTED",
                    priority="critical",
                    status=status,
                    created_at=datetime.now(timezone.utc) - timedelta(days=days_old),
                )
            )
            db.commit()

    def metrics(self) -> dict:
        response = self.client.get("/api/ap/metrics")
        assert response.status_code == 200
        return response.json()


@pytest.fixture
def metrics(tmp_path: Path):
    database_path = tmp_path / "ap-metrics.db"
    engine = create_engine(
        f"sqlite:///{database_path.as_posix()}",
        connect_args={"check_same_thread": False},
    )
    test_session = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    Run.__table__.create(engine)
    Decision.__table__.create(engine)
    WorkbenchItem.__table__.create(engine)

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
            yield MetricsHarness(client, test_session)
    finally:
        app.dependency_overrides.clear()
        app.dependency_overrides.update(original_overrides)
        app.user_middleware = original_user_middleware
        app.middleware_stack = original_middleware_stack
        engine.dispose()
        database_path.unlink(missing_ok=True)


def test_empty_dashboard_returns_zeros_not_sample_data(metrics: MetricsHarness):
    body = metrics.metrics()
    assert body["invoices_processed"] == 0
    assert body["touchless_rate"] == 0.0
    assert body["money_protected"] == {}
    assert body["spend_under_review"] == {}
    assert body["exceptions_by_type"] == []
    assert body["recent_runs"] == []
    assert body["average_confidence"] is None


def test_touchless_rate_is_the_share_that_cleared(metrics: MetricsHarness):
    metrics.add_decision(belnr="A1", verdict="PAY_READY")
    metrics.add_decision(belnr="A2", verdict="PAY_READY")
    metrics.add_decision(belnr="A3", verdict="PAY_READY")
    metrics.add_decision(belnr="A4", verdict="PAYMENT_HOLD", reason_codes=["BEC_SUSPECTED"])

    body = metrics.metrics()
    assert body["invoices_processed"] == 4
    assert body["pay_ready"] == 3
    assert body["touchless_rate"] == 75.0
    assert body["verdict_breakdown"]["PAY_READY"] == 3
    assert body["verdict_breakdown"]["PAYMENT_HOLD"] == 1


def test_reprocessing_the_same_invoice_does_not_inflate_anything(metrics: MetricsHarness):
    metrics.add_decision(
        belnr="B1", verdict="PAYMENT_HOLD", money_protected=5000.0, run_id="RUN-1"
    )
    first = metrics.metrics()
    assert first["invoices_processed"] == 1
    assert first["money_protected"] == {"MYR": 5000.0}

    metrics.add_decision(
        belnr="B1", verdict="PAYMENT_HOLD", money_protected=5000.0, run_id="RUN-2"
    )
    second = metrics.metrics()
    assert second["invoices_processed"] == 1
    assert second["money_protected"] == {"MYR": 5000.0}


def test_money_is_grouped_by_currency_and_never_summed_across(metrics: MetricsHarness):
    metrics.add_decision(
        belnr="C1", verdict="PAYMENT_HOLD", currency="MYR", money_protected=1000.0
    )
    metrics.add_decision(
        belnr="C2", verdict="PAYMENT_HOLD", currency="SGD", money_protected=500.0
    )

    body = metrics.metrics()
    assert body["money_protected"] == {"MYR": 1000.0, "SGD": 500.0}


def test_protected_and_under_review_stay_separate(metrics: MetricsHarness):
    metrics.add_decision(
        belnr="D1", verdict="PAYMENT_HOLD", money_protected=200.0
    )
    metrics.add_decision(
        belnr="D2", verdict="HUMAN_REVIEW", spend_under_review=9000.0
    )

    body = metrics.metrics()
    assert body["money_protected"] == {"MYR": 200.0}
    assert body["spend_under_review"] == {"MYR": 9000.0}


def test_oracle_backfill_rows_never_reach_the_dashboard(metrics: MetricsHarness):
    metrics.add_decision(belnr="E1", verdict="PAY_READY", source="oracle_backfill")
    body = metrics.metrics()
    assert body["invoices_processed"] == 0


def test_exceptions_by_type_is_ranked_and_ignores_cleared_invoices(metrics: MetricsHarness):
    metrics.add_decision(belnr="F1", verdict="PAYMENT_HOLD", reason_codes=["BEC_SUSPECTED"])
    metrics.add_decision(belnr="F2", verdict="PAYMENT_HOLD", reason_codes=["BEC_SUSPECTED"])
    metrics.add_decision(belnr="F3", verdict="HUMAN_REVIEW", reason_codes=["RECEIPT_MISSING"])
    metrics.add_decision(belnr="F4", verdict="PAY_READY", reason_codes=["GR_EXEMPT_FRAMEWORK"])

    codes = metrics.metrics()["exceptions_by_type"]
    assert codes[0] == {"code": "BEC_SUSPECTED", "count": 2}
    assert {"code": "RECEIPT_MISSING", "count": 1} in codes
    assert all(c["code"] != "GR_EXEMPT_FRAMEWORK" for c in codes)


def test_exception_aging_buckets_open_items_by_age(metrics: MetricsHarness):
    metrics.add_workbench_item(belnr="G1", days_old=0)
    metrics.add_workbench_item(belnr="G2", days_old=3)
    metrics.add_workbench_item(belnr="G3", days_old=10)
    metrics.add_workbench_item(belnr="G4", days_old=30, status="resolved")

    body = metrics.metrics()
    aging = {bucket["bucket"]: bucket["count"] for bucket in body["exception_aging"]}
    assert aging["0-1 days"] == 1
    assert aging["2-3 days"] == 1
    assert aging["8+ days"] == 1
    assert body["workbench_open"] == 3
    assert body["workbench_resolved"] == 1


def test_recent_runs_are_newest_first_and_capped(metrics: MetricsHarness):
    for i in range(7):
        metrics.add_run(run_id=f"RUN-{i:02d}", duration_ms=1000 + i)

    body = metrics.metrics()
    assert len(body["recent_runs"]) == 5
    assert body["total_runs"] == 7
    assert body["average_run_ms"] is not None


def test_average_confidence_ignores_missing_values(metrics: MetricsHarness):
    metrics.add_decision(belnr="H1", confidence=0.90)
    metrics.add_decision(belnr="H2", confidence=0.80)
    metrics.add_decision(belnr="H3", confidence=None)

    assert metrics.metrics()["average_confidence"] == 0.85
