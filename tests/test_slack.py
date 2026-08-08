"""Outbound Slack messages from the Workbench.

Two properties matter more than delivery itself: an account number must never
leave the process in full, and a failed send must never cost the reviewer their
decision.
"""

from __future__ import annotations

import httpx
import pytest

from app.services import slack


class TestRedaction:
    @pytest.mark.parametrize(
        "raw",
        [
            "6406-8941-4832",
            "6406 8941 4832",
            "640689414832",
            "7455-5754-8099",
        ],
    )
    def test_account_numbers_are_reduced_to_their_last_four(self, raw: str):
        result = slack.redact_account_numbers(f"Account {raw} on file")
        assert raw not in result
        assert "****" in result
        # The tail is kept so a human can still match it against a statement.
        assert result.strip().endswith("on file")

    def test_the_surviving_tail_is_the_real_last_four(self):
        assert "****4832" in slack.redact_account_numbers("6406-8941-4832")

    def test_ordinary_numbers_are_left_alone(self):
        # Over-redaction is not "safe" — it strips the context that makes the
        # message actionable. Invoice numbers, dates and amounts must survive.
        text = "Invoice 5110000150 for MYR 1,234,293.69 dated 2026-07-15"
        result = slack.redact_account_numbers(text)
        assert result == text

    @pytest.mark.parametrize(
        "keep",
        ["5110000150", "2026-07-15", "1,234,293.69", "PO 46200048", "MY20"],
    )
    def test_business_references_survive(self, keep: str):
        assert keep in slack.redact_account_numbers(f"Context: {keep} here")

    def test_redaction_runs_over_the_whole_composed_message(self):
        message = slack.build_information_request(
            belnr="5110000150",
            vendor="Acme Supplies",
            amount="MYR 1,234,293.69",
            reason="possible payment-redirect fraud",
            question="Can you confirm the account 6406-8941-4832 belongs to you?",
            reviewer="reviewer@example.com",
        )
        assert "6406-8941-4832" not in message
        assert "****4832" in message


class TestMessage:
    def test_exception_alert_carries_real_context_and_redacts_account_like_content(self):
        message = slack.build_exception_alert(
            run_id="RUN-20260808-AB12CD34",
            belnr="5110000150",
            vendor="6406-8941-4832 Vendor",
            amount="MYR 250.00",
            verdict="PAYMENT_HOLD",
            reason_codes=["BANK_MISMATCH", "BEC_SUSPECTED"],
        )

        assert "RUN-20260808-AB12CD34" in message
        assert "5110000150" in message
        assert "****4832 Vendor" in message
        assert "6406-8941-4832" not in message
        assert "MYR 250.00" in message
        assert "PAYMENT_HOLD" in message
        assert "BANK_MISMATCH, BEC_SUSPECTED" in message

    def test_exception_alert_uses_safe_vendor_fallback(self):
        message = slack.build_exception_alert(
            run_id="RUN-20260808-AB12CD34",
            belnr="5110000150",
            vendor=None,
            amount=None,
            verdict="HUMAN_REVIEW",
            reason_codes=[],
        )

        assert "*Vendor:* Not recorded" in message
        assert "*Amount:* Not recorded" in message

    def test_carries_what_the_recipient_needs_to_act(self):
        message = slack.build_information_request(
            belnr="5110000007",
            vendor="Acme Supplies",
            amount="MYR 330,252.07",
            reason="spend without a purchase order",
            question="Which cost centre should this go to?",
            reviewer="ku@example.com",
        )
        assert "5110000007" in message
        assert "Acme Supplies" in message
        assert "MYR 330,252.07" in message
        assert "spend without a purchase order" in message
        assert "Which cost centre should this go to?" in message
        assert "ku@example.com" in message

    def test_survives_missing_optional_context(self):
        message = slack.build_information_request(
            belnr="5110000011",
            vendor=None,
            amount=None,
            reason=None,
            question="Please send the delivery note.",
            reviewer="ku@example.com",
        )
        assert "Not recorded" in message
        assert "Please send the delivery note." in message


class TestSend:
    def test_transport_failure_does_not_log_exception_text(self, monkeypatch, caplog):
        secret = "https://hooks.example.test/services/SECRET-DO-NOT-LOG"
        monkeypatch.setenv("SLACK_WEBHOOK_URL", "https://hooks.example.test/ap-alerts")

        def explode(*args, **kwargs):
            raise httpx.ConnectError(secret)

        monkeypatch.setattr(slack.httpx, "post", explode)

        result = slack.send("hello")

        assert result.outcome == "failed"
        assert secret not in caplog.text

    def test_reports_not_configured_rather_than_pretending_to_send(self, monkeypatch):
        monkeypatch.delenv("SLACK_WEBHOOK_URL", raising=False)
        result = slack.send("anything")
        assert result.sent is False
        assert result.outcome == "not_configured"
        assert result.configured is False

    def test_a_blank_webhook_counts_as_unconfigured(self, monkeypatch):
        monkeypatch.setenv("SLACK_WEBHOOK_URL", "   ")
        assert slack.send("anything").outcome == "not_configured"

    def test_success_when_slack_accepts_the_message(self, monkeypatch):
        monkeypatch.setenv("SLACK_WEBHOOK_URL", "https://hooks.example.com/abc")
        monkeypatch.setattr(
            slack.httpx, "post", lambda *a, **k: httpx.Response(200, text="ok")
        )
        result = slack.send("hello")
        assert result.sent is True
        assert result.outcome == "success"

    def test_a_transport_error_is_reported_never_raised(self, monkeypatch):
        monkeypatch.setenv("SLACK_WEBHOOK_URL", "https://hooks.example.com/abc")

        def explode(*args, **kwargs):
            raise httpx.ConnectError("no route to host")

        monkeypatch.setattr(slack.httpx, "post", explode)
        result = slack.send("hello")
        assert result.sent is False
        assert result.outcome == "failed"
        assert "no route" in result.detail

    def test_a_4xx_from_slack_is_a_failure_not_a_success(self, monkeypatch):
        monkeypatch.setenv("SLACK_WEBHOOK_URL", "https://hooks.example.com/abc")
        monkeypatch.setattr(
            slack.httpx, "post", lambda *a, **k: httpx.Response(403, text="invalid_token")
        )
        result = slack.send("hello")
        assert result.sent is False
        assert result.outcome == "failed"
        assert "403" in result.detail
