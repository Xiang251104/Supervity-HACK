"""Supervity client tests that do not need the live API.

Two things are locked in here because they are the parts most likely to be wrong
until we see a real run on 3 Aug:

  1. The request really is multipart/form-data. httpx only encodes multipart when
     `files` is truthy — `files={}` silently degrades to urlencoded and Auto rejects
     it with a 4xx. That mistake costs hours, so it is asserted.
  2. The SSE frame parser never drops a frame, whatever Auto calls its events.
"""

import json

import httpx
import pytest

from app.services.supervity import (
    EXECUTE_STREAM,
    AutoEvent,
    SupervityClient,
    SupervityConfig,
    SupervityNotConfigured,
    _normalize_type,
)


def cfg():
    return SupervityConfig(
        api_key="test-key",
        active_org="test-org",
        orchestrator_workflow_id="wf_test",
    )


# --------------------------------------------------------------------- headers
def test_headers_carry_the_three_required_values():
    h = cfg().headers()
    assert h["Authorization"] == "Bearer test-key"
    assert h["x-source"] == "external"
    assert h["x-active-org"] == "test-org"


def test_missing_credentials_fail_loudly_not_silently():
    with pytest.raises(SupervityNotConfigured):
        SupervityConfig(api_key="", active_org="").headers()


# ------------------------------------------------------------------- multipart
def test_execute_body_is_multipart_not_urlencoded():
    """The single most expensive mistake available on this endpoint."""
    form = {
        "workflowId": (None, "wf_test"),
        "inputs": (None, json.dumps({"invoice_ref": "X"})),
    }
    req = httpx.Request("POST", f"https://auto.supervity.ai{EXECUTE_STREAM}", files=form)
    assert req.headers["content-type"].startswith("multipart/form-data")
    body = req.read().decode()
    assert 'name="workflowId"' in body
    assert 'name="inputs"' in body


def test_empty_files_dict_would_degrade_to_urlencoded():
    """Guards the regression: this is what the code must NOT do."""
    bad = httpx.Request("POST", "https://x/y", data={"workflowId": "wf"}, files={})
    assert bad.headers["content-type"] == "application/x-www-form-urlencoded"


# ------------------------------------------------------------------ event type
@pytest.mark.parametrize(
    "raw,expected",
    [
        ("activity", "activity"),
        ("activity_update", "activity"),
        ("workflow_status", "status"),
        ("ai_reasoning", "reasoning"),
        ("result", "result"),
        ("completed", "result"),
        ("error", "error"),
        ("ping", "ping"),
        ("something_auto_invented", "activity"),  # unknown -> keep, don't drop
    ],
)
def test_event_type_normalization(raw, expected):
    assert _normalize_type(raw) == expected


# ---------------------------------------------------------------- frame parser
def test_frame_parses_operator_and_summary():
    payload = {
        "type": "activity",
        "operatorName": "AP - Three Way Match",
        "summary": "Matched invoice to PO line 20",
        "detail": {"ebelp": "20"},
    }
    ev = SupervityClient._build_event(1, "activity", json.dumps(payload))
    assert isinstance(ev, AutoEvent)
    assert ev.operator_name == "AP - Three Way Match"
    assert ev.summary == "Matched invoice to PO line 20"
    assert ev.payload == payload          # raw frame always preserved
    assert not ev.is_terminal


def test_frame_finds_nested_fields():
    """Auto may nest the interesting values; the parser digs one level."""
    payload = {"data": {"agentName": "AP - Bank Change Verification", "message": "Frozen"}}
    ev = SupervityClient._build_event(2, "activity", json.dumps(payload))
    assert ev.operator_name == "AP - Bank Change Verification"
    assert ev.summary == "Frozen"


def test_event_name_can_come_from_the_body():
    ev = SupervityClient._build_event(3, "message", json.dumps({"type": "result", "ok": True}))
    assert ev.event_type == "result"
    assert ev.is_terminal


def test_non_json_frame_is_kept_not_dropped():
    ev = SupervityClient._build_event(4, "activity", "plain text heartbeat")
    assert ev is not None
    assert ev.payload["raw"] == "plain text heartbeat"


def test_empty_and_done_frames_are_ignored():
    assert SupervityClient._build_event(5, "activity", "") is None
    assert SupervityClient._build_event(6, "activity", "[DONE]") is None


def test_error_frame_is_terminal():
    ev = SupervityClient._build_event(7, "error", json.dumps({"message": "operator failed"}))
    assert ev.event_type == "error"
    assert ev.is_terminal
    assert ev.summary == "operator failed"


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-v"]))
