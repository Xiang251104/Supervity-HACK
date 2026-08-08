"""Does changing a policy actually change what the agent may do?

A judge will edit a threshold in the UI and ask to see different behaviour on the
next run. Every test here holds the invoice and the agent's proposal constant and
changes only the policy value — so a policy that stops gating fails a test rather
than quietly becoming decoration.

The counterpart matters just as much: no policy value may release a hard hold.
Thresholds tune judgement, they do not wave through blocked vendors or suspected
fraud.
"""

from __future__ import annotations

import pytest

from app.services.policies import PolicySnapshot, evaluate

BASE = {
    "PRICE-TOLERANCE": 2, "BANK-CHANGE-FREEZE": 30, "DOA-BAND": 5000,
    "GR-POLICY": "fo_aware", "RETRO-PO": "advisory", "MIN-CONFIDENCE": 0.70,
    "AS-OF-DATE": "2026-07-15", "HIGH-VALUE-THRESHOLD": 500000,
    "NEAR-DUP-TOLERANCE": 0.1, "DEFAULT-KOSTL": "CC100",
}

PO_INVOICE = {"amount": 50000, "is_po": True, "confidence": 0.95}


def snap(**overrides) -> PolicySnapshot:
    values = {**BASE, **overrides}
    return PolicySnapshot(label="test", values=values, versions={k: 1 for k in values})


def verdict_for(codes, invoice=None, proposed="PAY_READY", **policy) -> str:
    return evaluate(snap(**policy), proposed, list(codes), dict(invoice or PO_INVOICE)).verdict


def row_for(key, codes, invoice=None, proposed="PAY_READY", **policy) -> dict:
    result = evaluate(snap(**policy), proposed, list(codes), dict(invoice or PO_INVOICE))
    return next(e for e in result.evaluated if e["policy_key"] == key)


class TestGoodsReceiptPolicy:
    """fo_aware exempts framework orders; strict_require_gr withdraws that."""

    def test_framework_order_clears_under_fo_aware(self):
        assert verdict_for(["GR_EXEMPT_FRAMEWORK"], **{"GR-POLICY": "fo_aware"}) == "PAY_READY"

    def test_tightening_to_strict_escalates_the_same_invoice(self):
        assert verdict_for(
            ["GR_EXEMPT_FRAMEWORK"], **{"GR-POLICY": "strict_require_gr"}
        ) == "HUMAN_REVIEW"

    @pytest.mark.parametrize("setting", ["fo_aware", "strict_require_gr"])
    @pytest.mark.parametrize("code", ["RECEIPT_MISSING", "RECEIPT_PARTIAL"])
    def test_a_genuinely_missing_receipt_escalates_under_every_setting(self, setting, code):
        # fo_aware exempts framework orders only. It is not a way to switch the
        # goods-receipt control off entirely.
        assert verdict_for([code], **{"GR-POLICY": setting}) == "HUMAN_REVIEW"

    def test_the_withdrawn_exemption_is_explained(self):
        row = row_for("GR-POLICY", ["GR_EXEMPT_FRAMEWORK"], **{"GR-POLICY": "strict_require_gr"})
        assert row["outcome"] == "escalate"
        assert "withdrawn" in row["explanation"]


class TestBankChangeFreeze:
    def test_recent_change_escalates_while_the_window_is_open(self):
        assert verdict_for(["BANK_CHANGE_UNVERIFIED"], **{"BANK-CHANGE-FREEZE": 30}) \
            == "HUMAN_REVIEW"

    def test_zero_window_switches_the_recency_control_off(self):
        # Setting the window to zero is how a business disables the freeze, and it
        # has to visibly do so or the number means nothing.
        assert verdict_for(["BANK_CHANGE_UNVERIFIED"], **{"BANK-CHANGE-FREEZE": 0}) \
            == "PAY_READY"

    @pytest.mark.parametrize("code", ["BANK_MISMATCH", "BANK_ACCOUNT_UNKNOWN"])
    def test_a_wrong_account_escalates_whatever_the_window(self, code):
        # These are not about recency, so the freeze window does not govern them.
        assert verdict_for([code], **{"BANK-CHANGE-FREEZE": 0}) == "HUMAN_REVIEW"


class TestMinimumConfidence:
    def test_relaxing_the_bar_clears_the_agents_own_flag(self):
        # The agent flagged LOW_CONFIDENCE against the old threshold. Once the
        # business lowers the bar the measured value passes, and the control must
        # honour that or it looks broken to whoever just changed it.
        invoice = {"amount": 50000, "is_po": True, "confidence": 0.67}
        assert verdict_for(["LOW_CONFIDENCE"], invoice, **{"MIN-CONFIDENCE": 0.70}) \
            == "HUMAN_REVIEW"
        assert verdict_for(["LOW_CONFIDENCE"], invoice, **{"MIN-CONFIDENCE": 0.50}) \
            == "PAY_READY"

    def test_tightening_the_bar_catches_what_the_agent_passed(self):
        invoice = {"amount": 50000, "is_po": True, "confidence": 0.75}
        assert verdict_for([], invoice, **{"MIN-CONFIDENCE": 0.70}) == "PAY_READY"
        assert verdict_for([], invoice, **{"MIN-CONFIDENCE": 0.80}) == "HUMAN_REVIEW"

    def test_without_a_number_the_agents_judgement_stands(self):
        # No confidence reported means there is nothing to apply a threshold to.
        invoice = {"amount": 50000, "is_po": True, "confidence": None}
        assert verdict_for(["LOW_CONFIDENCE"], invoice, **{"MIN-CONFIDENCE": 0.10}) \
            == "HUMAN_REVIEW"


class TestDelegationBand:
    def test_non_po_spend_above_the_band_needs_an_approver(self):
        invoice = {"amount": 67922.68, "is_po": False, "confidence": 0.83}
        assert verdict_for(["NON_PO_APPROVAL"], invoice, **{"DOA-BAND": 5000}) \
            == "HUMAN_REVIEW"

    def test_raising_the_band_lets_it_clear(self):
        invoice = {"amount": 67922.68, "is_po": False, "confidence": 0.83}
        assert verdict_for(["NON_PO_APPROVAL"], invoice, **{"DOA-BAND": 100000}) \
            == "PAY_READY"

    def test_a_matched_po_invoice_is_not_subject_to_the_band(self):
        # The approved PO is the authorization; re-applying the band to matched
        # spend would send essentially the whole book to a human.
        invoice = {"amount": 943523.28, "is_po": True, "confidence": 0.95}
        assert verdict_for([], invoice, **{"DOA-BAND": 5000}) == "PAY_READY"


class TestRetroactivePO:
    def test_advisory_records_without_holding(self):
        assert verdict_for(["PO_OUT_OF_VALIDITY"], **{"RETRO-PO": "advisory"}) == "PAY_READY"

    def test_review_escalates_the_same_invoice(self):
        assert verdict_for(["PO_OUT_OF_VALIDITY"], **{"RETRO-PO": "review"}) == "HUMAN_REVIEW"


class TestHoldsAreAbsolute:
    """No threshold may release a hard hold — that is the whole point of one."""

    @pytest.mark.parametrize("code", [
        "BEC_SUSPECTED", "VENDOR_BLOCKED", "VENDOR_DELETED",
        "PO_CURRENCY_MISMATCH", "PO_VENDOR_MISMATCH", "ENTITY_MISMATCH",
        "PO_LINE_NO_MATCH", "DUP_LATER_COPY",
    ])
    def test_no_relaxed_policy_can_release(self, code):
        relaxed = {
            "BANK-CHANGE-FREEZE": 0, "DOA-BAND": 10**9, "MIN-CONFIDENCE": 0.0,
            "PRICE-TOLERANCE": 100, "GR-POLICY": "fo_aware", "RETRO-PO": "advisory",
        }
        assert verdict_for([code], **relaxed) == "PAYMENT_HOLD"


class TestEveryEvaluationIsLogged:
    def test_all_six_gate_policies_are_recorded_even_when_silent(self):
        result = evaluate(snap(), "PAY_READY", [], dict(PO_INVOICE))
        keys = {e["policy_key"] for e in result.evaluated}
        assert keys == {"PRICE-TOLERANCE", "BANK-CHANGE-FREEZE", "GR-POLICY",
                        "RETRO-PO", "MIN-CONFIDENCE", "DOA-BAND"}

    def test_a_clean_invoice_logs_evaluations_with_nothing_fired(self):
        result = evaluate(snap(), "PAY_READY", [], dict(PO_INVOICE))
        assert result.verdict == "PAY_READY"
        assert result.fired == []
        assert len(result.evaluated) == 6

    def test_the_threshold_in_force_is_captured_for_the_audit_trail(self):
        row = row_for("MIN-CONFIDENCE", [], **{"MIN-CONFIDENCE": 0.85})
        assert row["threshold_value"] == 0.85
        assert row["observed_value"] == 0.95
