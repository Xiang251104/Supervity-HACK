# app/services/slack.py
"""Outbound Slack messages sent by a human, not by the agent.

The Orchestrator raises its own alerts through Auto's native Slack connector.
This module covers the other direction: a reviewer in the Workbench asking
someone to supply what is missing before an invoice can be decided.

Two rules hold here:

  * Bank details are never sent in full. Anything that looks like an account
    number is reduced to its last four characters before it leaves the process.
  * A failed or unconfigured send must never fail the human's action. The
    decision is what matters; the notification is best-effort and its outcome is
    recorded either way.
"""

from __future__ import annotations

import logging
import os
import re
from dataclasses import dataclass

import httpx

logger = logging.getLogger(__name__)

TIMEOUT_SECONDS = 8.0

# Account-shaped, in the two forms that actually occur:
#
#   grouped  6406-8941-4832 / 6406 8941 4832 -- three or more groups of 3-6
#            digits sharing one separator
#   plain    640689414832 -- an unbroken run of 12 or more digits
#
# Both thresholds are set to clear the things that must stay readable: a
# ten-digit invoice number, an ISO date (2026-07-15 groups as 4-2-2), and any
# comma-formatted amount. Redacting those would make the message useless.
_ACCOUNT_GROUPED = re.compile(r"\b\d{3,6}([- ])\d{3,6}(?:\1\d{3,6})+\b")
_ACCOUNT_PLAIN = re.compile(r"\b\d{12,}\b")


def redact_account_numbers(text: str) -> str:
    """Reduce anything account-shaped to its last four digits."""

    def mask(match: re.Match[str]) -> str:
        digits = re.sub(r"\D", "", match.group(0))
        return f"****{digits[-4:]}" if len(digits) >= 4 else "****"

    return _ACCOUNT_PLAIN.sub(mask, _ACCOUNT_GROUPED.sub(mask, text))


@dataclass
class SlackResult:
    """Outcome of one send. `sent` is False for both "off" and "failed"."""

    sent: bool
    outcome: str  # success | not_configured | failed
    detail: str

    @property
    def configured(self) -> bool:
        return self.outcome != "not_configured"


def webhook_url() -> str:
    return os.getenv("SLACK_WEBHOOK_URL", "").strip()


def is_configured() -> bool:
    return bool(webhook_url())


def build_information_request(
    *,
    belnr: str,
    vendor: str | None,
    amount: str | None,
    reason: str | None,
    question: str,
    reviewer: str,
) -> str:
    """The message a reviewer sends when an invoice cannot be decided yet."""
    lines = [
        f"*More information needed — invoice {belnr}*",
        "",
        f"*Vendor:* {vendor or 'Not recorded'}",
        f"*Amount:* {amount or 'Not recorded'}",
    ]
    if reason:
        lines.append(f"*Why it was flagged:* {reason}")
    lines += [
        "",
        f"*{reviewer} asks:*",
        f"> {question}",
        "",
        "_Sent from the AP Control Tower Workbench. The invoice stays on hold "
        "until this is answered._",
    ]
    return redact_account_numbers("\n".join(lines))


def build_exception_alert(
    *,
    run_id: str,
    belnr: str,
    vendor: str | None,
    amount: str | None,
    verdict: str,
    reason_codes: list[str],
) -> str:
    """Build the automatic alert for a newly opened AP exception."""
    lines = [
        f"*AP exception opened — run {run_id}*",
        "",
        f"*Invoice:* {belnr}",
        f"*Vendor:* {vendor or 'Not recorded'}",
        f"*Amount:* {amount or 'Not recorded'}",
        f"*Verdict:* {verdict}",
        f"*Reason codes:* {', '.join(reason_codes) or 'Not recorded'}",
        "",
        "_Sent from the AP Control Tower after opening a Workbench exception._",
    ]
    return redact_account_numbers("\n".join(lines))


def send(text: str) -> SlackResult:
    """Post to the configured webhook. Never raises."""
    url = webhook_url()
    if not url:
        return SlackResult(
            sent=False,
            outcome="not_configured",
            detail="SLACK_WEBHOOK_URL is not set, so no message was sent.",
        )

    try:
        response = httpx.post(url, json={"text": text}, timeout=TIMEOUT_SECONDS)
    except httpx.HTTPError as exc:
        logger.warning("Slack send failed: %s", exc)
        return SlackResult(sent=False, outcome="failed", detail=str(exc)[:300])

    if response.status_code >= 400:
        logger.warning("Slack returned %s: %s", response.status_code, response.text[:200])
        return SlackResult(
            sent=False,
            outcome="failed",
            detail=f"Slack returned {response.status_code}: {response.text[:200]}",
        )

    return SlackResult(sent=True, outcome="success", detail="Message delivered to Slack.")
