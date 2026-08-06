"""API contract tests for the AP human-review Workbench."""

from __future__ import annotations

from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from app.core.database import SessionLocal
from app.main import app
from app.models.ap import Decision, Run, RunEvent, WorkbenchItem


@pytest.fixture
def client() -> TestClient:
    return TestClient(app)


@pytest.fixture
def workbench_record():
    run_id = f"workbench-test-{uuid4()}"
    db = SessionLocal()
    try:
        run = Run(
            run_id=run_id,
            invoice_ref="5110000017",
            status="completed",
            trigger_source="outlook",
            policy_version_label="Standard v1.0",
        )
        db.add(run)
        db.flush()

        decision = Decision(
            run_id=run_id,
            belnr="5110000017",
            lifnr="4110006",
            ebeln="46200003",
            vendor_name="Demo Vendor",
            currency="MYR",
            amount=805_966.59,
            amount_myr=805_966.59,
            verdict="PAYMENT_HOLD",
            reason_codes=["PO_VENDOR_MISMATCH"],
            evidence={"po_gr": {"invoice_vendor": "4110006", "po_vendor": "4110030"}},
            money_protected=805_966.59,
            spend_under_review=0,
            policy_version_label="Standard v1.0",
            confidence=0.99,
            human_status="PENDING_REVIEW",
            source="auto_run",
        )
        db.add(decision)
        db.flush()

        item = WorkbenchItem(
            run_id=run_id,
            decision_id=decision.id,
            belnr="5110000017",
            title="Vendor mismatch requires review",
            exception_type="PO_VENDOR_MISMATCH",
            priority="critical",
            recommendation="Confirm the supplier identity before releasing payment.",
            context={"invoice_vendor": "4110006", "po_vendor": "4110030"},
            assigned_role="AP Manager",
            status="open",
        )
        db.add(item)
        db.commit()
        db.refresh(item)
        db.refresh(decision)
        yield {"run_id": run_id, "item_id": item.id, "decision_id": decision.id}
    finally:
        db.rollback()
        db.query(RunEvent).filter(RunEvent.run_id == run_id).delete(synchronize_session=False)
        db.query(WorkbenchItem).filter(WorkbenchItem.run_id == run_id).delete(synchronize_session=False)
        db.query(Decision).filter(Decision.run_id == run_id).delete(synchronize_session=False)
        db.query(Run).filter(Run.run_id == run_id).delete(synchronize_session=False)
        db.commit()
        db.close()


def test_list_workbench_items_supports_status_and_priority_filters(
    client: TestClient, workbench_record: dict
):
    response = client.get("/api/ap/workbench?status=open&priority=critical")

    assert response.status_code == 200
    body = response.json()
    matching = [item for item in body["items"] if item["id"] == workbench_record["item_id"]]
    assert body["total"] >= 1
    assert matching == [
        {
            "id": workbench_record["item_id"],
            "run_id": workbench_record["run_id"],
            "decision_id": workbench_record["decision_id"],
            "belnr": "5110000017",
            "title": "Vendor mismatch requires review",
            "exception_type": "PO_VENDOR_MISMATCH",
            "priority": "critical",
            "status": "open",
            "assigned_role": "AP Manager",
            "created_at": matching[0]["created_at"],
            "verdict": "PAYMENT_HOLD",
            "currency": "MYR",
            "amount": 805966.59,
            "money_protected": 805966.59,
        }
    ]

    assert client.get("/api/ap/workbench?status=resolved&priority=critical").json()["items"] == []
    assert client.get("/api/ap/workbench?status=open&priority=normal").json()["items"] == []


def test_get_workbench_detail_includes_full_immutable_decision(
    client: TestClient, workbench_record: dict
):
    response = client.get(f"/api/ap/workbench/{workbench_record['item_id']}")

    assert response.status_code == 200
    body = response.json()
    assert body["id"] == workbench_record["item_id"]
    assert body["context"] == {"invoice_vendor": "4110006", "po_vendor": "4110030"}
    assert body["recommendation"].startswith("Confirm the supplier")
    assert body["decision"]["verdict"] == "PAYMENT_HOLD"
    assert body["decision"]["reason_codes"] == ["PO_VENDOR_MISMATCH"]
    assert body["decision"]["evidence"]["po_gr"]["po_vendor"] == "4110030"
    assert body["decision"]["policy_version_label"] == "Standard v1.0"


def test_get_unknown_workbench_item_returns_404(client: TestClient):
    response = client.get("/api/ap/workbench/2147483647")
    assert response.status_code == 404
    assert response.json()["detail"] == "Workbench item not found"


@pytest.mark.parametrize(
    ("action", "expected_item_status", "expected_human_status"),
    [
        ("approve", "resolved", "APPROVED"),
        ("reject", "resolved", "REJECTED"),
        ("request_info", "open", "PENDING_INFORMATION"),
    ],
)
def test_resolve_records_human_action_without_mutating_ai_verdict(
    client: TestClient,
    workbench_record: dict,
    action: str,
    expected_item_status: str,
    expected_human_status: str,
):
    db = SessionLocal()
    try:
        decision = db.get(Decision, workbench_record["decision_id"])
        immutable_before = {
            "verdict": decision.verdict,
            "reason_codes": decision.reason_codes,
            "evidence": decision.evidence,
            "money_protected": decision.money_protected,
            "policy_version_label": decision.policy_version_label,
        }
    finally:
        db.close()

    response = client.post(
        f"/api/ap/workbench/{workbench_record['item_id']}/resolve",
        json={"action": action, "note": f"Reviewer selected {action}."},
    )

    assert response.status_code == 200
    assert response.json()["status"] == expected_item_status
    assert response.json()["decision"]["human_status"] == expected_human_status
    assert response.json()["decision"]["resolution_action"] == action

    db = SessionLocal()
    try:
        item = db.get(WorkbenchItem, workbench_record["item_id"])
        decision = db.get(Decision, workbench_record["decision_id"])
        events = (
            db.query(RunEvent)
            .filter(
                RunEvent.run_id == workbench_record["run_id"],
                RunEvent.event_type == "human_action",
            )
            .all()
        )
        assert item.status == expected_item_status
        assert item.action == action
        assert item.note == f"Reviewer selected {action}."
        assert decision.human_status == expected_human_status
        assert {
            "verdict": decision.verdict,
            "reason_codes": decision.reason_codes,
            "evidence": decision.evidence,
            "money_protected": decision.money_protected,
            "policy_version_label": decision.policy_version_label,
        } == immutable_before
        assert len(events) == 1
        assert events[0].payload["action"] == action
        assert events[0].payload["workbench_item_id"] == workbench_record["item_id"]
        assert events[0].payload["decision_id"] == workbench_record["decision_id"]
    finally:
        db.close()


def test_resolve_requires_a_non_blank_note(client: TestClient, workbench_record: dict):
    response = client.post(
        f"/api/ap/workbench/{workbench_record['item_id']}/resolve",
        json={"action": "approve", "note": "   "},
    )
    assert response.status_code == 422


def test_resolved_item_cannot_be_resolved_again(client: TestClient, workbench_record: dict):
    endpoint = f"/api/ap/workbench/{workbench_record['item_id']}/resolve"
    first = client.post(endpoint, json={"action": "approve", "note": "Approved once."})
    second = client.post(endpoint, json={"action": "reject", "note": "Rejected later."})

    assert first.status_code == 200
    assert second.status_code == 409
    assert second.json()["detail"] == "Workbench item is already resolved"
