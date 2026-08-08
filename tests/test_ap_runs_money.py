"""How a run turns Operator results into money.

The rule this file exists to defend: protected value is the single largest
candidate among the Operators that FAILED, never the sum. Three Operators
flagging the same 1,234,293.69 invoice protect 1,234,293.69 -- claiming
3,702,881.07 would overstate the AI Employee's value by 3x on one invoice.
"""

from __future__ import annotations

from app.routers.ap_runs import (
    _collect_operator_results,
    _combined_reason_codes,
    _find,
    _money_protected,
)


def result(status: str, protected: float | None = None, codes: list[str] | None = None) -> dict:
    return {
        "operator_name": "AP - Something",
        "status": status,
        "reason_codes": codes or [],
        "protected_value_candidate": protected,
        "protected_value_currency": "MYR",
    }


class TestMoneyProtected:
    def test_overlapping_flags_are_never_added_together(self):
        results = {
            "duplicate_result": result("FAIL", 1234293.69),
            "bank_result": result("FAIL", 1234293.69),
            "entity_result": result("FAIL", 1234293.69),
        }
        assert _money_protected(results, "PAYMENT_HOLD") == 1234293.69

    def test_takes_the_largest_candidate_when_they_differ(self):
        results = {
            "bank_result": result("FAIL", 800000.0),
            "match_result": result("FAIL", 1234293.69),
        }
        assert _money_protected(results, "PAYMENT_HOLD") == 1234293.69

    def test_only_failing_operators_contribute(self):
        results = {
            "bank_result": result("PASS", 999999.0),
            "match_result": result("REVIEW", 888888.0),
            "entity_result": result("FAIL", 1000.0),
        }
        assert _money_protected(results, "PAYMENT_HOLD") == 1000.0

    def test_review_protects_nothing_because_the_money_is_not_held(self):
        # Spend under review is not money protected -- the invoice may still be paid.
        results = {"match_result": result("FAIL", 500000.0)}
        assert _money_protected(results, "HUMAN_REVIEW") == 0.0

    def test_a_cleared_invoice_protects_nothing(self):
        assert _money_protected({"bank_result": result("PASS", 0.0)}, "PAY_READY") == 0.0

    def test_a_hold_with_no_candidate_reports_zero_not_a_guess(self):
        results = {"bank_result": result("FAIL", None)}
        assert _money_protected(results, "PAYMENT_HOLD") == 0.0

    def test_unparseable_candidates_do_not_crash_the_run(self):
        results = {"bank_result": result("FAIL", "not a number")}  # type: ignore[arg-type]
        assert _money_protected(results, "PAYMENT_HOLD") == 0.0

    def test_status_is_matched_case_insensitively(self):
        results = {"bank_result": {"status": "fail", "protected_value_candidate": 42.0}}
        assert _money_protected(results, "PAYMENT_HOLD") == 42.0


class TestReasonCodes:
    def test_prefers_the_orchestrators_own_combined_list(self):
        payload = {"reason_codes": ["BANK_MISMATCH", "BEC_SUSPECTED"]}
        assert _combined_reason_codes(payload, {}) == ["BANK_MISMATCH", "BEC_SUSPECTED"]

    def test_merges_operator_codes_without_repeating_any(self):
        payload = {"reason_codes": ["BANK_MISMATCH"]}
        results = {
            "bank_result": result("FAIL", codes=["BANK_MISMATCH", "BEC_SUSPECTED"]),
            "intake_result": result("REVIEW", codes=["LOW_CONFIDENCE"]),
        }
        assert _combined_reason_codes(payload, results) == [
            "BANK_MISMATCH", "BEC_SUSPECTED", "LOW_CONFIDENCE",
        ]

    def test_recovers_codes_when_the_orchestrator_published_none(self):
        results = {"bank_result": result("FAIL", codes=["BANK_MISMATCH"])}
        assert _combined_reason_codes({}, results) == ["BANK_MISMATCH"]

    def test_no_codes_at_all_is_an_empty_list(self):
        assert _combined_reason_codes({}, {}) == []


class TestCollectOperatorResults:
    def test_picks_up_every_operator_the_orchestrator_reported(self):
        payload = {
            "intake_result": result("PASS"),
            "duplicate_result": result("PASS"),
            "bank_result": result("FAIL", 1000.0),
            "match_result": result("PASS"),
            "entity_result": result("PASS"),
            "po_entity_result": result("PASS"),
        }
        assert set(_collect_operator_results(payload)) == set(payload)

    def test_ignores_a_status_string_masquerading_as_a_result(self):
        # module_statuses maps the same keys to plain strings; those are not evidence.
        payload = {"module_statuses": {"intake_result": "PASS", "bank_result": "FAIL"}}
        assert _collect_operator_results(payload) == {}

    def test_a_missing_operator_is_simply_absent(self):
        payload = {"intake_result": result("PASS")}
        assert list(_collect_operator_results(payload)) == ["intake_result"]


class TestFind:
    def test_finds_a_key_nested_inside_the_payload(self):
        assert _find({"a": {"b": {"verdict": "PAY_READY"}}}, "verdict") == "PAY_READY"

    def test_searches_through_lists(self):
        assert _find({"steps": [{"x": 1}, {"verdict": "PAYMENT_HOLD"}]}, "verdict") == "PAYMENT_HOLD"

    def test_treats_empty_values_as_not_found(self):
        assert _find({"verdict": ""}, "verdict") is None

    def test_gives_up_rather_than_hanging_on_a_deep_payload(self):
        deep: dict = {"verdict": "PAY_READY"}
        for _ in range(20):
            deep = {"nested": deep}
        assert _find(deep, "verdict") is None
