"""Tests for the Auto client.

The shapes asserted here were captured from real Orchestrator runs on
2026-08-08, not invented. Three of them encode bugs that made every run fail
silently, so they are worth defending:

  * Operator results live in child runs, not the parent.
  * The verdict step calls its list `combined_reason_codes`.
  * Live frames identify a step by id and carry no display name.
"""

from __future__ import annotations

import asyncio

import pytest

from app.services.supervity import (
    STEP_DISPLAY_NAMES,
    SupervityClient,
    SupervityConfig,
    _contract_result,
    _parse_step_output,
)


@pytest.fixture
def client() -> SupervityClient:
    return SupervityClient(SupervityConfig(api_key="test-key", active_org="Sixteen"))


def subworkflow_step(step_id: str, child_run_id: str) -> dict:
    """A subworkflow call: empty output, child run reachable only via the link."""
    return {
        "kind": "step",
        "stepId": step_id,
        "outputs": {
            "output": "",
            "displayData": {
                "html": '<a href="https://auto.supervity.ai/u/alpha/agent/workflow/'
                        f'019fc777-84bc-7000-ac8e-32bfb4090ab8/runs/{child_run_id}">View</a>'
            },
        },
    }


def contract(operator: str, status: str, protected: float = 0.0, **extra) -> dict:
    body = {
        "operator_name": operator,
        "status": status,
        "reason_codes": [],
        "explanation": "",
        "evidence": {},
        "retryable": False,
        "protected_value_candidate": protected,
        "protected_value_currency": "MYR",
    }
    body.update(extra)
    return body


# --------------------------------------------------------------------------- #
# Output parsing
# --------------------------------------------------------------------------- #


class TestParseStepOutput:
    def test_reads_the_json_string_auto_actually_sends(self):
        assert _parse_step_output('{"verdict": "PAY_READY"}') == {"verdict": "PAY_READY"}

    def test_passes_through_a_dict_untouched(self):
        assert _parse_step_output({"a": 1}) == {"a": 1}

    @pytest.mark.parametrize("raw", ["", "   ", None, "not json", "[1, 2]", '"a string"', 42])
    def test_anything_unusable_is_none_rather_than_a_guess(self, raw):
        assert _parse_step_output(raw) is None


class TestContractResult:
    def test_prefers_the_step_carrying_the_full_contract(self):
        detail = {
            "activityRuns": [
                {"outputs": {"output": '{"duplicate_fingerprint": "x"}'}},
                {"outputs": {"output": '{"operator_name": "AP - Intake", "status": "PASS"}'}},
            ]
        }
        assert _contract_result(detail)["operator_name"] == "AP - Intake"

    def test_identifies_the_contract_by_shape_not_by_step_name(self):
        # The Operator's final step is not always called "Return Result".
        detail = {
            "activityRuns": [
                {"stepName": "Anything At All",
                 "outputs": {"output": '{"operator_name": "AP - Bank", "status": "FAIL"}'}},
            ]
        }
        assert _contract_result(detail)["status"] == "FAIL"

    def test_falls_back_to_the_last_structured_output(self):
        detail = {"activityRuns": [{"outputs": {"output": '{"partial": true}'}}]}
        assert _contract_result(detail) == {"partial": True}

    def test_returns_none_when_a_child_produced_nothing(self):
        assert _contract_result({"activityRuns": [{"outputs": {"output": ""}}]}) is None
        assert _contract_result({}) is None


# --------------------------------------------------------------------------- #
# Flattening a finished run
# --------------------------------------------------------------------------- #


class TestCollectRunOutputs:
    @pytest.fixture
    def payload(self) -> dict:
        return {
            "workflowRun": {
                "id": "019fdf8f-07d0-7c40-abd6-4c859dc6ffe2",
                "status": "completed",
                "activityRuns": [
                    subworkflow_step("step_intake", "11111111-1111-7111-8111-111111111111"),
                    {"kind": "condition", "stepId": "step_intake",
                     "outputs": {"output": "True\n", "conditionMet": True}},
                    subworkflow_step("step_bank_screen",
                                     "22222222-2222-7222-8222-222222222222"),
                    {"kind": "step", "stepId": "step_decide_verdict", "outputs": {
                        "output": '{"verdict": "PAYMENT_HOLD",'
                                  ' "combined_reason_codes": ["BANK_MISMATCH", "BEC_SUSPECTED"],'
                                  ' "module_statuses": {"bank_result": "FAIL"}}',
                        "displayData": {"html": "<p>Final</p>"},
                    }},
                ],
            }
        }

    @pytest.fixture
    def children(self) -> dict:
        return {
            "11111111-1111-7111-8111-111111111111": {
                "activityRuns": [{"outputs": {"output": _json(contract(
                    "AP - Intake and Normalize", "PASS",
                    canonical_invoice={"belnr": "5110000150", "lifnr": "4110006",
                                       "amount": 1234293.69, "waers": "MYR",
                                       "confidence": 0.55},
                ))}}]
            },
            "22222222-2222-7222-8222-222222222222": {
                "activityRuns": [{"outputs": {"output": _json(contract(
                    "AP - Bank Change Verification", "FAIL", protected=1234293.69,
                ))}}]
            },
        }

    def test_walks_child_runs_to_recover_operator_evidence(
        self, client, payload, children, monkeypatch
    ):
        async def fake_get_run(run_id: str) -> dict:
            return children[run_id]

        monkeypatch.setattr(client, "get_run", fake_get_run)
        flat = asyncio.run(client.collect_run_outputs(payload))

        assert flat["intake_result"]["operator_name"] == "AP - Intake and Normalize"
        assert flat["bank_result"]["status"] == "FAIL"
        assert flat["bank_result"]["protected_value_candidate"] == 1234293.69

    def test_lifts_the_canonical_invoice_out_of_the_intake_contract(
        self, client, payload, children, monkeypatch
    ):
        monkeypatch.setattr(client, "get_run", lambda rid: _async(children[rid]))
        flat = asyncio.run(client.collect_run_outputs(payload))

        assert flat["canonical_invoice"]["belnr"] == "5110000150"
        assert flat["canonical_invoice"]["amount"] == 1234293.69

    def test_renames_combined_reason_codes_to_the_key_we_store(
        self, client, payload, children, monkeypatch
    ):
        monkeypatch.setattr(client, "get_run", lambda rid: _async(children[rid]))
        flat = asyncio.run(client.collect_run_outputs(payload))

        assert flat["verdict"] == "PAYMENT_HOLD"
        assert flat["reason_codes"] == ["BANK_MISMATCH", "BEC_SUSPECTED"]

    def test_an_unreadable_child_is_dropped_never_invented(
        self, client, payload, monkeypatch
    ):
        from app.services.supervity import SupervityError

        async def always_fails(run_id: str) -> dict:
            raise SupervityError("boom")

        monkeypatch.setattr(client, "get_run", always_fails)
        flat = asyncio.run(client.collect_run_outputs(payload))

        # A missing Operator must be absent, not present with a passing status.
        assert "intake_result" not in flat
        assert "bank_result" not in flat
        assert flat["verdict"] == "PAYMENT_HOLD"

    def test_carries_the_workflow_run_id_for_the_audit_trail(
        self, client, payload, children, monkeypatch
    ):
        monkeypatch.setattr(client, "get_run", lambda rid: _async(children[rid]))
        flat = asyncio.run(client.collect_run_outputs(payload))

        assert flat["runId"] == "019fdf8f-07d0-7c40-abd6-4c859dc6ffe2"
        assert flat["run_status"] == "completed"


# --------------------------------------------------------------------------- #
# Live frames
# --------------------------------------------------------------------------- #


class TestBuildEvent:
    def test_names_the_operator_from_the_step_id(self):
        event = SupervityClient._build_event(
            1, "activity-run",
            '{"content": {"stepId": "step_bank_screen", "status": "running"}}',
        )
        assert event.operator_name == "AP - Bank Change Verification"
        assert event.event_type == "activity"
        assert event.summary == "running"

    def test_unknown_step_ids_still_show_something_useful(self):
        event = SupervityClient._build_event(
            1, "activity-run", '{"content": {"stepId": "step_future_operator"}}'
        )
        assert event.operator_name == "step_future_operator"

    def test_reads_thinking_text_from_a_bare_content_string(self):
        event = SupervityClient._build_event(
            1, "thinking", '{"content": "Getting your workspace ready"}'
        )
        assert event.event_type == "reasoning"
        assert event.summary == "Getting your workspace ready"

    def test_result_and_error_frames_are_terminal(self):
        assert SupervityClient._build_event(1, "result", '{"success": true}').is_terminal
        assert SupervityClient._build_event(1, "error", '{"message": "x"}').is_terminal
        assert not SupervityClient._build_event(1, "ping", '{"content": "ping"}').is_terminal

    def test_every_orchestrator_step_has_a_readable_name(self):
        from app.services.supervity import STEP_TO_OPERATOR_KEY

        assert set(STEP_TO_OPERATOR_KEY) <= set(STEP_DISPLAY_NAMES)


# --------------------------------------------------------------------------- #
# Configuration
# --------------------------------------------------------------------------- #


class TestConfig:
    def test_points_at_the_api_host_not_the_web_app(self):
        # auto.supervity.ai is the Remix front end. It answers /api/v1/* with a
        # generic 400 whether or not credentials are sent, so this default being
        # wrong is indistinguishable from a bad key.
        assert SupervityConfig(api_key="k", active_org="o").base_url == \
            "https://auto-workflow-api.supervity.ai"

    def test_missing_credentials_fail_loudly(self):
        from app.services.supervity import SupervityNotConfigured

        with pytest.raises(SupervityNotConfigured):
            SupervityConfig(api_key="", active_org="").headers()

    def test_sends_the_three_headers_auto_requires(self):
        headers = SupervityConfig(api_key="k", active_org="Sixteen").headers()
        assert headers["Authorization"] == "Bearer k"
        assert headers["x-source"] == "external"
        assert headers["x-active-org"] == "Sixteen"


def _json(value: dict) -> str:
    import json

    return json.dumps(value)


async def _async(value):
    return value
