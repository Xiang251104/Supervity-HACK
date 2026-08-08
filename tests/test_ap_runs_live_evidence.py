"""Live Outlook and Slack evidence emitted by completed AP runs."""

from __future__ import annotations

from types import SimpleNamespace

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.core.database import Base
from app.models.ap import Decision, RunEvent, WorkbenchItem
from app.routers import ap_runs
from app.schemas.ap_runs import RunRequest
from app.services.policies import GateResult, PolicySnapshot
from app.services.slack import SlackResult


class _FakeSupervityClient:
    payload: dict[str, object] = {}

    async def execute_stream(self, inputs, workflow_id=None):
        yield SimpleNamespace(
            seq=7,
            event_type="result",
            operator_name="AP - Intake and Normalize",
            summary="Canonical invoice ready",
            payload=self.payload,
        )

    async def collect_run_outputs(self, payload):
        return payload


@pytest.fixture
def db() -> Session:
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    session = sessionmaker(bind=engine)()
    try:
        yield session
    finally:
        session.close()
        Base.metadata.drop_all(engine)


def _snapshot() -> PolicySnapshot:
    return PolicySnapshot(label="v-test", values={}, versions={})


def _gate(verdict: str) -> GateResult:
    return GateResult(
        verdict=verdict,
        allowed_actions=["review"],
        fired=[],
        evaluated=[],
        explanation="Policy outcome",
    )


async def _run(
    db: Session,
    monkeypatch: pytest.MonkeyPatch,
    *,
    source_channel: str,
    trigger_source: str = "api",
    verdict: str = "PAYMENT_HOLD",
    slack_result: SlackResult | None = None,
) -> str:
    run_id = "RUN-TEST-LIVE-EVIDENCE"
    _FakeSupervityClient.payload = {
        "canonical_invoice": {
            "belnr": "5110000150",
            "source_channel": source_channel,
            "vendor_name": "6406-8941-4832 Vendor",
            "amount": 250.0,
            "waers": "MYR",
        },
        "verdict": verdict,
        "reason_codes": ["BANK_MISMATCH"],
    }
    monkeypatch.setattr(ap_runs, "SupervityClient", _FakeSupervityClient)
    monkeypatch.setattr(ap_runs, "build_snapshot", lambda db: _snapshot())
    monkeypatch.setattr(ap_runs, "evaluate", lambda *args: _gate(verdict))
    monkeypatch.setattr(ap_runs, "record_evaluations", lambda *args: None)
    if slack_result is not None:
        monkeypatch.setattr(ap_runs.slack, "send", lambda message: slack_result)

    await ap_runs.start_run(
        RunRequest(
            run_id=run_id,
            invoice_ref="5110000150",
            trigger_source=trigger_source,
        ),
        db,
    )
    return run_id


@pytest.mark.asyncio
async def test_default_api_source_becomes_outlook_for_whitespace_case_insensitive_email(
    db: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    run_id = await _run(db, monkeypatch, source_channel="  eMaIl  ")

    assert db.get(ap_runs.Run, 1).trigger_source == "outlook"


@pytest.mark.asyncio
async def test_explicit_non_default_source_wins_over_email_canonical_evidence(
    db: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    await _run(db, monkeypatch, source_channel="EMAIL", trigger_source="rerun")

    assert db.get(ap_runs.Run, 1).trigger_source == "rerun"


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "result", [
        SlackResult(sent=True, outcome="success", detail="Message delivered to Slack."),
        SlackResult(sent=False, outcome="failed", detail="connection refused"),
        SlackResult(sent=False, outcome="not_configured", detail="webhook not configured"),
    ],
)
async def test_opened_workbench_item_records_actual_slack_outcome_after_stream_events(
    db: Session, monkeypatch: pytest.MonkeyPatch, result: SlackResult
) -> None:
    run_id = await _run(db, monkeypatch, source_channel="PORTAL", slack_result=result)

    events = db.query(RunEvent).filter(RunEvent.run_id == run_id).order_by(RunEvent.seq).all()
    assert [event.seq for event in events] == [7, 8]
    activity = events[-1]
    assert activity.event_type == "integration_activity"
    assert activity.payload["integration_key"] == "slack"
    assert activity.payload["outcome"] == result.outcome
    assert "6406-8941-4832" not in activity.summary
    assert db.query(Decision).filter(Decision.run_id == run_id).one()
    assert db.query(WorkbenchItem).filter(WorkbenchItem.run_id == run_id).one()


@pytest.mark.asyncio
async def test_pay_ready_run_does_not_create_automatic_slack_activity(
    db: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    run_id = await _run(db, monkeypatch, source_channel="PORTAL", verdict="PAY_READY")

    assert db.get(ap_runs.Run, 1).trigger_source == "api"
    assert [event.event_type for event in db.query(RunEvent).filter(RunEvent.run_id == run_id)] == ["result"]
