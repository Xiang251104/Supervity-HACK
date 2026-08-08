"""Tests for the AI Insights engine and its API.

The engine's contract is narrow and worth defending: insights are computed only from
decisions the agent actually produced, currencies are never mixed, and an empty
dataset yields no insights rather than invented ones.
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
from app.models.ap import Decision, Insight, PolicyEvaluation
from app.security import get_current_user, verify_access
from app.services.insights import compute_insights, refresh_insights


@dataclass
class InsightHarness:
    client: TestClient
    session_factory: sessionmaker

    def add_decision(
        self,
        *,
        belnr: str,
        verdict: str = "PAY_READY",
        reason_codes: list[str] | None = None,
        lifnr: str = "4110000",
        ebeln: str | None = "46200048",
        currency: str = "MYR",
        amount: float = 1000.0,
        money_protected: float = 0.0,
        spend_under_review: float = 0.0,
        bukrs: str | None = "MY20",
        source: str = "auto_run",
        run_id: str | None = None,
    ) -> None:
        with self.session_factory() as db:
            db.add(
                Decision(
                    run_id=run_id or f"RUN-{belnr}",
                    belnr=belnr,
                    lifnr=lifnr,
                    ebeln=ebeln,
                    bukrs=bukrs,
                    currency=currency,
                    amount=amount,
                    verdict=verdict,
                    reason_codes=reason_codes or [],
                    money_protected=money_protected,
                    spend_under_review=spend_under_review,
                    source=source,
                    created_at=datetime(2026, 8, 7, 12, 0, tzinfo=timezone.utc),
                )
            )
            db.commit()

    def add_policy_evaluation(
        self,
        *,
        policy_key: str,
        fired: bool,
        threshold: Any = 2,
        run_id: str = "RUN-EVAL",
    ) -> None:
        with self.session_factory() as db:
            db.add(
                PolicyEvaluation(
                    run_id=run_id,
                    belnr="5110000002",
                    policy_key=policy_key,
                    policy_version=1,
                    threshold_value=threshold,
                    observed_value=None,
                    fired=fired,
                    outcome="escalate" if fired else "allow",
                    explanation="test",
                )
            )
            db.commit()

    def session(self) -> Session:
        return self.session_factory()


@pytest.fixture
def insights(tmp_path: Path):
    database_path = tmp_path / "ap-insights.db"
    engine = create_engine(
        f"sqlite:///{database_path.as_posix()}",
        connect_args={"check_same_thread": False},
    )
    test_session = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    Decision.__table__.create(engine)
    Insight.__table__.create(engine)
    PolicyEvaluation.__table__.create(engine)

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
    app.user_middleware = [
        m for m in original_user_middleware if m.cls is not AuditMiddleware
    ]
    app.middleware_stack = None

    try:
        with TestClient(app) as client:
            yield InsightHarness(client, test_session)
    finally:
        app.dependency_overrides.clear()
        app.dependency_overrides.update(original_overrides)
        app.user_middleware = original_user_middleware
        app.middleware_stack = original_middleware_stack
        engine.dispose()
        database_path.unlink(missing_ok=True)


# --------------------------------------------------------------------------- #
# The engine
# --------------------------------------------------------------------------- #


def test_no_decisions_produces_no_insights(insights: InsightHarness):
    """An empty page is correct. A populated one would be fabricated."""
    with insights.session() as db:
        assert compute_insights(db) == []


def test_oracle_backfill_rows_are_excluded(insights: InsightHarness):
    """Computed development data must never surface as agent output."""
    insights.add_decision(belnr="5110000001", source="oracle_backfill")
    with insights.session() as db:
        assert compute_insights(db) == []


def test_reprocessing_an_invoice_does_not_double_any_metric(insights: InsightHarness):
    """The demo path: edit a policy, re-run the same invoices. Metrics must not double."""
    insights.add_decision(
        belnr="R1", verdict="PAY_READY", run_id="RUN-1", reason_codes=[]
    )
    insights.add_decision(
        belnr="R2",
        verdict="PAYMENT_HOLD",
        reason_codes=["BEC_SUSPECTED", "DUP_LATER_COPY"],
        money_protected=5000.0,
        run_id="RUN-1",
    )
    with insights.session() as db:
        first = {i.key: i for i in compute_insights(db)}
    assert first["touchless-rate"].evidence["processed"] == 2
    assert first["money-protected"].evidence["protected_by_currency"] == {"MYR": 5000.0}

    # Same two invoices processed again under a new run.
    insights.add_decision(belnr="R1", verdict="PAY_READY", run_id="RUN-2")
    insights.add_decision(
        belnr="R2",
        verdict="PAYMENT_HOLD",
        reason_codes=["BEC_SUSPECTED", "DUP_LATER_COPY"],
        money_protected=5000.0,
        run_id="RUN-2",
    )
    with insights.session() as db:
        second = {i.key: i for i in compute_insights(db)}

    assert second["touchless-rate"].evidence["processed"] == 2
    assert second["money-protected"].evidence["protected_by_currency"] == {"MYR": 5000.0}
    assert second["duplicate-clusters"].metric_value == 1.0
    assert second["fraud-anomalies"].metric_value == 1.0


def test_touchless_rate_counts_only_pay_ready(insights: InsightHarness):
    insights.add_decision(belnr="A1", verdict="PAY_READY")
    insights.add_decision(belnr="A2", verdict="PAY_READY")
    insights.add_decision(belnr="A3", verdict="HUMAN_REVIEW", reason_codes=["RECEIPT_MISSING"])
    insights.add_decision(belnr="A4", verdict="PAYMENT_HOLD", reason_codes=["BEC_SUSPECTED"])

    with insights.session() as db:
        found = {i.key: i for i in compute_insights(db)}

    touchless = found["touchless-rate"]
    assert touchless.metric_value == 50.0
    assert touchless.metric_unit == "%"
    assert touchless.evidence["processed"] == 4
    assert touchless.evidence["pay_ready"] == 2


def test_money_protected_is_grouped_by_currency_never_summed_across(insights: InsightHarness):
    insights.add_decision(
        belnr="B1", verdict="PAYMENT_HOLD", currency="MYR", money_protected=1000.0
    )
    insights.add_decision(
        belnr="B2", verdict="PAYMENT_HOLD", currency="SGD", money_protected=500.0
    )

    with insights.session() as db:
        found = {i.key: i for i in compute_insights(db)}

    protected = found["money-protected"].evidence["protected_by_currency"]
    assert protected == {"MYR": 1000.0, "SGD": 500.0}
    # Two currencies means no single headline number — we never add them together.
    assert found["money-protected"].metric_value is None


def test_spend_under_review_is_not_reported_as_protected(insights: InsightHarness):
    insights.add_decision(
        belnr="C1", verdict="PAYMENT_HOLD", currency="MYR", money_protected=200.0
    )
    insights.add_decision(
        belnr="C2", verdict="HUMAN_REVIEW", currency="MYR", spend_under_review=9000.0
    )

    with insights.session() as db:
        found = {i.key: i for i in compute_insights(db)}

    evidence = found["money-protected"].evidence
    assert evidence["protected_by_currency"] == {"MYR": 200.0}
    assert evidence["spend_under_review_by_currency"] == {"MYR": 9000.0}


def test_fraud_insight_is_critical_when_bec_is_present(insights: InsightHarness):
    insights.add_decision(
        belnr="D1", verdict="PAYMENT_HOLD", reason_codes=["BEC_SUSPECTED"], amount=50000.0
    )
    with insights.session() as db:
        found = {i.key: i for i in compute_insights(db)}
    assert found["fraud-anomalies"].severity == "critical"


def test_fraud_insight_is_warning_without_bec(insights: InsightHarness):
    insights.add_decision(
        belnr="D2", verdict="HUMAN_REVIEW", reason_codes=["BANK_MISMATCH"], amount=100.0
    )
    with insights.session() as db:
        found = {i.key: i for i in compute_insights(db)}
    assert found["fraud-anomalies"].severity == "warning"


def test_duplicate_clusters_group_by_vendor(insights: InsightHarness):
    insights.add_decision(belnr="E1", lifnr="4110000", reason_codes=["DUP_LATER_COPY"])
    insights.add_decision(belnr="E2", lifnr="4110000", reason_codes=["DUP_LATER_COPY"])
    insights.add_decision(belnr="E3", lifnr="4110030", reason_codes=["DUP_NEAR"])

    with insights.session() as db:
        found = {i.key: i for i in compute_insights(db)}

    clusters = found["duplicate-clusters"].evidence["clusters"]
    assert clusters[0]["lifnr"] == "4110000"
    assert clusters[0]["count"] == 2


def test_released_duplicates_are_not_reported_as_money_avoided(insights: InsightHarness):
    """A flagged invoice that still cleared protected nothing."""
    for belnr in ("E4", "E5", "E6"):
        insights.add_decision(
            belnr=belnr,
            verdict="PAY_READY",
            reason_codes=["DUP_NEAR"],
            amount=1000.0,
            money_protected=0.0,
        )

    with insights.session() as db:
        found = {i.key: i for i in compute_insights(db)}

    duplicates = found["duplicate-clusters"]
    assert duplicates.evidence["avoided_by_currency"] == {}
    assert duplicates.evidence["flagged_but_released"] == 3
    assert "no payment was avoided" in duplicates.body
    assert "MYR 3,000.00" not in duplicates.body
    # And nothing conjured a protected figure out of released invoices.
    assert "money-protected" not in found


def test_policy_evaluations_from_other_runs_do_not_leak_in(insights: InsightHarness):
    """Backfill evaluations survive a decisions-only purge; they must not be counted."""
    insights.add_decision(belnr="P1", run_id="RUN-REAL")
    insights.add_policy_evaluation(policy_key="GR-POLICY", fired=True, run_id="RUN-REAL")
    for _ in range(200):
        insights.add_policy_evaluation(
            policy_key="GR-POLICY", fired=True, run_id="RUN-OLD-BACKFILL"
        )

    with insights.session() as db:
        found = {i.key: i for i in compute_insights(db)}

    friction = found["policy-friction"]
    assert friction.metric_value == 1.0
    # The reader is a finance user: the title leads with the rule's plain name,
    # while the raw key stays in the body and evidence for the audit trail.
    assert friction.title == "The goods-receipt requirement rule affected 1 of 1 invoices"


def test_policy_friction_reports_the_most_recent_threshold(insights: InsightHarness):
    insights.add_decision(belnr="P2", run_id="RUN-T")
    insights.add_policy_evaluation(
        policy_key="PRICE-TOLERANCE", fired=True, threshold=2, run_id="RUN-T"
    )
    insights.add_policy_evaluation(
        policy_key="PRICE-TOLERANCE", fired=True, threshold=10, run_id="RUN-T"
    )

    with insights.session() as db:
        found = {i.key: i for i in compute_insights(db)}

    assert "its setting was 10" in found["policy-friction"].body


def test_malformed_reason_codes_do_not_shred_into_characters(insights: InsightHarness):
    insights.add_decision(belnr="M1", verdict="PAYMENT_HOLD", reason_codes="BEC_SUSPECTED")

    with insights.session() as db:
        found = {i.key: i for i in compute_insights(db)}

    rows = found["touchless-rate"].evidence["invoices_needing_a_human"]
    assert rows[0]["reason_codes"] == []


def test_missing_vendor_and_currency_do_not_render_as_none(insights: InsightHarness):
    insights.add_decision(
        belnr="N1",
        verdict="PAYMENT_HOLD",
        reason_codes=["BEC_SUSPECTED"],
        lifnr=None,
        currency=None,
        amount=None,
        money_protected=900.0,
    )

    with insights.session() as db:
        found = {i.key: i for i in compute_insights(db)}

    assert "vendor None" not in found["fraud-anomalies"].body
    # A single UNKNOWN currency bucket is not a headline number.
    assert found["money-protected"].metric_value is None
    assert found["money-protected"].metric_unit is None


def test_vendor_risk_ranks_by_volume_not_by_a_tiny_sample(insights: InsightHarness):
    # A perfect-rate vendor with the minimum sample must not outrank a high-volume one.
    for i in range(3):
        insights.add_decision(
            belnr=f"SMALL{i}", lifnr="4119999", verdict="HUMAN_REVIEW",
            reason_codes=["RECEIPT_MISSING"],
        )
    for i in range(12):
        verdict = "PAYMENT_HOLD" if i < 9 else "PAY_READY"
        insights.add_decision(
            belnr=f"BIG{i}", lifnr="4110030", verdict=verdict,
            reason_codes=["BEC_SUSPECTED"] if i < 9 else [],
        )

    with insights.session() as db:
        found = {i.key: i for i in compute_insights(db)}

    assert found["vendor-risk"].action_payload["lifnr"] == "4110030"


def test_vendor_below_the_minimum_sample_is_ignored(insights: InsightHarness):
    insights.add_decision(belnr="T1", lifnr="4110001", verdict="PAYMENT_HOLD")
    insights.add_decision(belnr="T2", lifnr="4110001", verdict="PAYMENT_HOLD")

    with insights.session() as db:
        found = {i.key: i for i in compute_insights(db)}

    assert "vendor-risk" not in found


def test_maverick_spend_counts_invoices_without_a_purchase_order(insights: InsightHarness):
    insights.add_decision(belnr="F1", ebeln=None, reason_codes=["NON_PO_APPROVAL"])
    insights.add_decision(belnr="F2", ebeln="46200048")

    with insights.session() as db:
        found = {i.key: i for i in compute_insights(db)}

    assert found["maverick-spend"].metric_value == 50.0


def test_policy_friction_ranks_the_most_fired_policy(insights: InsightHarness):
    insights.add_decision(belnr="G1", run_id="RUN-G")
    insights.add_policy_evaluation(policy_key="GR-POLICY", fired=True, run_id="RUN-G")
    insights.add_policy_evaluation(policy_key="GR-POLICY", fired=True, run_id="RUN-G")
    insights.add_policy_evaluation(policy_key="PRICE-TOLERANCE", fired=True, run_id="RUN-G")
    insights.add_policy_evaluation(policy_key="DOA-BAND", fired=False, run_id="RUN-G")

    with insights.session() as db:
        found = {i.key: i for i in compute_insights(db)}

    friction = found["policy-friction"]
    assert friction.action_payload["policy_key"] == "GR-POLICY"
    assert friction.evidence["fired_counts"][0] == {
        "policy_key": "GR-POLICY",
        "count": 2,
        "threshold_when_last_evaluated": 2,
    }


def test_refresh_replaces_previous_set_and_preserves_dismissals(insights: InsightHarness):
    insights.add_decision(belnr="H1", verdict="PAY_READY")

    with insights.session() as db:
        first = refresh_insights(db)
        assert first
        target = db.query(Insight).filter(Insight.key == "touchless-rate").one()
        target.dismissed = True
        db.commit()

    with insights.session() as db:
        refresh_insights(db)
        again = db.query(Insight).filter(Insight.key == "touchless-rate").one()
        assert again.dismissed is True
        # Replaced, not duplicated.
        assert db.query(Insight).filter(Insight.key == "touchless-rate").count() == 1


# --------------------------------------------------------------------------- #
# The API
# --------------------------------------------------------------------------- #


def test_list_is_read_only_and_never_writes(insights: InsightHarness):
    """Two concurrent GETs must not be able to insert two sets of insights."""
    insights.add_decision(belnr="I1", verdict="PAY_READY")

    first = insights.client.get("/api/ap/insights").json()
    second = insights.client.get("/api/ap/insights").json()

    assert first["items"] == [] and second["items"] == []
    assert first["decisions_analysed"] == 1
    with insights.session() as db:
        assert db.query(Insight).count() == 0

    # The client computes explicitly, and repeat computes stay idempotent.
    insights.client.post("/api/ap/insights/refresh")
    insights.client.post("/api/ap/insights/refresh")
    with insights.session() as db:
        assert db.query(Insight).filter(Insight.key == "touchless-rate").count() == 1


def test_list_is_empty_and_honest_before_any_run(insights: InsightHarness):
    response = insights.client.get("/api/ap/insights")
    assert response.status_code == 200
    body = response.json()
    assert body["items"] == []
    assert body["total"] == 0
    assert body["decisions_analysed"] == 0


def test_refresh_endpoint_recomputes(insights: InsightHarness):
    insights.add_decision(belnr="J1", verdict="PAY_READY")
    assert insights.client.post("/api/ap/insights/refresh").json()["decisions_analysed"] == 1

    insights.add_decision(belnr="J2", verdict="PAYMENT_HOLD", reason_codes=["BEC_SUSPECTED"])
    body = insights.client.post("/api/ap/insights/refresh").json()
    assert body["decisions_analysed"] == 2
    assert body["critical"] >= 1


def test_severity_counts_match_returned_items(insights: InsightHarness):
    insights.add_decision(belnr="K1", verdict="PAYMENT_HOLD", reason_codes=["BEC_SUSPECTED"])
    body = insights.client.post("/api/ap/insights/refresh").json()
    counts = {"critical": 0, "warning": 0, "info": 0}
    for item in body["items"]:
        counts[item["severity"]] += 1
    assert counts["critical"] == body["critical"]
    assert counts["warning"] == body["warning"]
    assert counts["info"] == body["info"]
    assert body["total"] == len(body["items"])


def test_dismiss_hides_the_insight_from_the_list(insights: InsightHarness):
    insights.add_decision(belnr="L1", verdict="PAY_READY")
    items = insights.client.post("/api/ap/insights/refresh").json()["items"]
    target = items[0]

    dismissed = insights.client.post(f"/api/ap/insights/{target['id']}/dismiss")
    assert dismissed.status_code == 200
    assert dismissed.json()["dismissed"] is True

    remaining = insights.client.get("/api/ap/insights").json()["items"]
    assert all(item["id"] != target["id"] for item in remaining)


def test_dismiss_unknown_insight_returns_404(insights: InsightHarness):
    assert insights.client.post("/api/ap/insights/9999/dismiss").status_code == 404


def test_dismissal_is_reversible(insights: InsightHarness):
    insights.add_decision(belnr="U1", verdict="PAY_READY")
    target = insights.client.post("/api/ap/insights/refresh").json()["items"][0]

    insights.client.post(f"/api/ap/insights/{target['id']}/dismiss")
    assert insights.client.get("/api/ap/insights").json()["items"] == []

    restored = insights.client.delete(f"/api/ap/insights/{target['id']}/dismiss")
    assert restored.status_code == 200
    assert restored.json()["dismissed"] is False
    assert any(
        item["id"] == target["id"]
        for item in insights.client.get("/api/ap/insights").json()["items"]
    )


def test_ids_stay_stable_across_refreshes(insights: InsightHarness):
    """An open tab holds these ids; churning them makes its Dismiss button 404."""
    insights.add_decision(belnr="V1", verdict="PAY_READY")
    before = {i["key"]: i["id"] for i in insights.client.post("/api/ap/insights/refresh").json()["items"]}
    after = {i["key"]: i["id"] for i in insights.client.post("/api/ap/insights/refresh").json()["items"]}
    assert before == after


def test_a_dismissed_insight_returns_when_it_becomes_more_severe(insights: InsightHarness):
    insights.add_decision(belnr="W1", verdict="PAY_READY")
    target = insights.client.post("/api/ap/insights/refresh").json()["items"][0]
    assert target["key"] == "touchless-rate"
    assert target["severity"] == "info"
    insights.client.post(f"/api/ap/insights/{target['id']}/dismiss")

    # The picture deteriorates: everything now needs a human.
    for i in range(30):
        insights.add_decision(belnr=f"W-HOLD-{i}", verdict="PAYMENT_HOLD",
                              reason_codes=["BEC_SUSPECTED"])

    items = insights.client.post("/api/ap/insights/refresh").json()["items"]
    touchless = next(i for i in items if i["key"] == "touchless-rate")
    assert touchless["severity"] == "critical"
    assert touchless["dismissed"] is False


def test_a_dismissed_insight_stays_dismissed_when_it_does_not_worsen(insights: InsightHarness):
    insights.add_decision(belnr="X1", verdict="PAY_READY")
    target = insights.client.post("/api/ap/insights/refresh").json()["items"][0]
    insights.client.post(f"/api/ap/insights/{target['id']}/dismiss")

    insights.add_decision(belnr="X2", verdict="PAY_READY")
    items = insights.client.post("/api/ap/insights/refresh").json()["items"]
    assert all(i["key"] != "touchless-rate" for i in items)


def test_insights_that_no_longer_hold_are_removed(insights: InsightHarness):
    insights.add_decision(belnr="Y1", verdict="PAYMENT_HOLD", reason_codes=["BEC_SUSPECTED"])
    keys = {i["key"] for i in insights.client.post("/api/ap/insights/refresh").json()["items"]}
    assert "fraud-anomalies" in keys

    with insights.session() as db:
        db.query(Decision).delete()
        db.add(
            Decision(
                run_id="RUN-Y2", belnr="Y2", lifnr="4110000", ebeln="46200048",
                currency="MYR", amount=100.0, verdict="PAY_READY", reason_codes=[],
                money_protected=0.0, spend_under_review=0.0, source="auto_run",
                created_at=datetime(2026, 8, 7, 13, 0, tzinfo=timezone.utc),
            )
        )
        db.commit()

    keys = {i["key"] for i in insights.client.post("/api/ap/insights/refresh").json()["items"]}
    assert "fraud-anomalies" not in keys
