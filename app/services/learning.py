# app/services/learning.py
"""Self-learning: a human correction at the Workbench changes future behaviour.

The agent proposes the same verdict every time it meets the same facts. That is
correct — but it means a reviewer who has cleared the same harmless exception for
the same vendor three times will be asked a fourth time, and a fifth. The
knowledge lives in the reviewer's head and never reaches the system.

This module closes that loop. Every Workbench approval is already recorded on the
decision it resolved (`Decision.resolution_action`), so the evidence is sitting in
one table. We read it back as a *learned signal*: this vendor, this reason, N
prior human approvals. The policy gate then treats a well-evidenced signal as
grounds to soften its next verdict by exactly one step.

Three rules keep this safe, and each has a test:

  1. Allowlist, never blocklist. Only the codes in LEARNABLE_CODES can ever be
     learned away. A reason code we have not explicitly classified — including any
     new one the Orchestrator starts emitting — is not learnable by default. Given
     Auto's vocabulary has already drifted once, a blocklist would be a standing
     invitation to learn away a control nobody remembered to exclude.
  2. Every blocking code must be covered. An invoice is only softened when all of
     its codes are learnable AND each one is independently well-evidenced. One
     unlearned code on the invoice and the human still gets called.
  3. One step, never two. HUMAN_REVIEW may become PAY_READY; PAYMENT_HOLD may
     become HUMAN_REVIEW. A held payment can never jump straight to paid.

What is deliberately NOT learnable: anything about bank details, vendor blocks,
duplicates, entity or currency mismatches, delegation of authority, and low
extraction confidence. Approving a bank change three times must never teach the
system to stop asking about bank changes — that is precisely the pattern a
payment-redirect fraud would exploit.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:  # pragma: no cover
    from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)

# Codes a human may teach us to stop asking about. Each is a recurring property of
# a vendor or its data — not a control. They are safe to learn because a repeat
# approval genuinely means "this is how this vendor always looks", not "ignore the
# risk this time".
LEARNABLE_CODES = {
    # The vendor exists twice in the vendor master. A data-quality artefact that
    # will be true for every invoice this vendor ever sends, until master data is
    # cleaned up.
    "VENDOR_MASTER_DUPLICATE",
    # Delivered quantity routinely differs from the ordered quantity for this
    # vendor (part shipments, weight-based goods).
    "RECEIPT_VARIANCE",
    # This vendor habitually invoices against an expired or retroactive PO. The
    # RETRO-PO policy already treats that as advisory rather than blocking.
    "PO_OUT_OF_VALIDITY",
    "RETRO_PO",
    # The vendor's date format is ambiguous in a consistent, known way.
    "DATE_AMBIGUOUS",
}

# Named explicitly so the intent is visible in code review and in the tests, rather
# than being implied by absence from the set above.
NEVER_LEARNABLE = {
    "BEC_SUSPECTED",
    "BANK_MISMATCH",
    "BANK_ACCOUNT_UNKNOWN",
    "BANK_CHANGE_UNVERIFIED",
    "VENDOR_BLOCKED",
    "VENDOR_DELETED",
    "DUP_LATER_COPY",
    "NEAR_DUP_SUSPECT",
    "PO_VENDOR_MISMATCH",
    "PO_CURRENCY_MISMATCH",
    "PO_LINE_NO_MATCH",
    "PO_LINE_AMBIGUOUS",
    "ENTITY_MISMATCH",
    "NON_PO_APPROVAL",
    "DOA_BAND_NOT_FOUND",
    "LOW_CONFIDENCE",
    "MISSING_INPUT",
    "GL_CODING_REQUIRED",
    "CREDIT_MEMO",
}

# One softening step. Absent from this map — PAY_READY, DATA_ERROR — means no
# softening: PAY_READY needs none, and DATA_ERROR is a broken invoice, not a
# judgement call a human can teach us to skip.
_SOFTEN_ONE_STEP = {
    "PAYMENT_HOLD": "HUMAN_REVIEW",
    "HUMAN_REVIEW": "PAY_READY",
}


def is_learnable(code: str) -> bool:
    """True only for codes explicitly classified as safe to learn."""
    return code in LEARNABLE_CODES and code not in NEVER_LEARNABLE


@dataclass
class LearnedSignal:
    """Prior human approvals of one reason code for one vendor."""

    code: str
    lifnr: str
    confirmations: int
    examples: list[str] = field(default_factory=list)

    def meets(self, threshold: int) -> bool:
        return self.confirmations >= threshold


def learned_signals(
    db: "Session",
    lifnr: str | None,
    codes: list[str],
    *,
    exclude_belnr: str | None = None,
) -> dict[str, LearnedSignal]:
    """Count prior Workbench approvals for this vendor, per learnable code.

    Only approvals count. A rejection teaches the opposite lesson and a parked
    "request_info" teaches nothing, so neither is evidence for softening.

    `exclude_belnr` keeps an invoice from being evidence for itself on a re-run.
    """
    from ..models.ap import Decision

    learnable = [c for c in dict.fromkeys(codes or []) if is_learnable(c)]
    if not lifnr or not learnable:
        return {}

    query = (
        db.query(Decision.belnr, Decision.reason_codes)
        .filter(
            Decision.lifnr == lifnr,
            Decision.resolution_action == "approve",
            Decision.source == "auto_run",
        )
        .order_by(Decision.resolved_at)
    )
    if exclude_belnr:
        query = query.filter(Decision.belnr != exclude_belnr)

    signals: dict[str, LearnedSignal] = {
        code: LearnedSignal(code=code, lifnr=lifnr, confirmations=0) for code in learnable
    }
    seen: dict[str, set[str]] = {code: set() for code in learnable}

    for belnr, prior_codes in query.all():
        for code in set(prior_codes or []):
            if code not in signals or belnr in seen[code]:
                continue
            seen[code].add(belnr)
            signal = signals[code]
            signal.confirmations += 1
            if len(signal.examples) < 5:
                signal.examples.append(belnr)

    return {code: s for code, s in signals.items() if s.confirmations > 0}


@dataclass
class LearningOutcome:
    """What the learning rule concluded, whether or not it changed anything."""

    applied: bool
    verdict: str
    covered: list[LearnedSignal]
    blocked_by: list[str]
    explanation: str

    @property
    def observed(self) -> dict[str, Any] | None:
        if not self.covered and not self.blocked_by:
            return None
        return {
            "confirmed": {s.code: s.confirmations for s in self.covered},
            "examples": {s.code: s.examples for s in self.covered},
            "not_learned": self.blocked_by,
        }


def apply_learning(
    verdict: str,
    codes: list[str],
    signals: dict[str, LearnedSignal],
    *,
    mode: str,
    threshold: int,
) -> LearningOutcome:
    """Decide whether prior human approvals justify softening this verdict.

    Pure — no database, no clock — so the safety rules can be tested exhaustively.
    """
    codes = list(dict.fromkeys(codes or []))
    softened = _SOFTEN_ONE_STEP.get(verdict)

    # Which codes are still standing in the way, and which are well-evidenced?
    covered: list[LearnedSignal] = []
    blocked_by: list[str] = []
    for code in codes:
        signal = signals.get(code)
        if is_learnable(code) and signal is not None and signal.meets(threshold):
            covered.append(signal)
        else:
            blocked_by.append(code)

    if mode == "off":
        return LearningOutcome(
            False, verdict, covered, blocked_by,
            "Learning from human decisions is switched off.",
        )

    if not covered:
        return LearningOutcome(
            False, verdict, covered, blocked_by,
            f"No reason on this invoice has been cleared by a human "
            f"{threshold} or more times for this vendor.",
        )

    evidence = "; ".join(
        f"{s.code} approved {s.confirmations}x (e.g. {', '.join(s.examples[:3])})"
        for s in covered
    )

    if blocked_by:
        return LearningOutcome(
            False, verdict, covered, blocked_by,
            f"Past approvals cover {len(covered)} of {len(codes)} reasons "
            f"({evidence}), but {', '.join(blocked_by)} has not been learned, "
            f"so a human is still required.",
        )

    if softened is None:
        return LearningOutcome(
            False, verdict, covered, blocked_by,
            f"Every reason is well-evidenced ({evidence}), but a {verdict} "
            f"verdict is never softened by learning.",
        )

    if mode == "advise":
        return LearningOutcome(
            False, verdict, covered, blocked_by,
            f"A human has cleared every reason on this invoice for this vendor "
            f"before ({evidence}). Learning is in advise mode, so the verdict is "
            f"unchanged — set it to 'apply' to act on this.",
        )

    return LearningOutcome(
        True, softened, covered, blocked_by,
        f"A human has cleared every reason on this invoice for this vendor at "
        f"least {threshold} times ({evidence}), so {verdict} was softened to "
        f"{softened}.",
    )
