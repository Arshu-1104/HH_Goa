"""Tests for evidence extractor — verifies evidence is grounded in MCP output."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

import unittest
from agent.tools.adapters import adapt
from agent.evidence.extractor import extract_evidence, reset_counter
from agent.state.models import EvidenceSourceType


def _make_get_case_result(risk_score=0.75, trigger="risk_score", channel="online", amt=250.0):
    raw = {
        "found": True,
        "case_id": "HHG-TEST",
        "case": {
            "case_id": "HHG-TEST",
            "opened_at": "2016-12-01",
            "trigger_type": trigger,
            "trigger_text": f"Test trigger. Risk={risk_score}",
            "flagged_txn_id": "TXN-001",
            "card_id": "C99999-K1",
            "customer_id": "C99999",
            "risk_score": risk_score,
        },
        "flagged_transaction": {
            "TransactionID": "TXN-001",
            "TransactionAmt": amt,
            "channel": channel,
        },
    }
    return adapt("get_case", raw)


def _make_prior_cases_result(fraud_cases=3, total_exposure=450.0):
    raw = {
        "customer_id": "C99999",
        "card_id": None,
        "total_cases": fraud_cases,
        "fraud_cases": fraud_cases,
        "cleared_cases": 0,
        "total_exposure_usd": total_exposure,
        "cases": [
            {"case_id": f"CHC-{i}", "outcome": "confirmed_fraud",
             "pattern": "card_not_present_fraud", "exposure_usd": 150.0}
            for i in range(fraud_cases)
        ],
    }
    return adapt("find_prior_cases", raw)


def _make_temporal_result(card_testing=True, burst=False):
    raw = {
        "customer_id": "C99999",
        "total_transactions": 50,
        "window_hours": 24,
        "transactions_in_window": 3 if burst else 1,
        "micro_transaction_count": 5 if card_testing else 0,
        "online_transaction_count": 10,
        "in_person_transaction_count": 5,
        "signals": {
            "card_testing": card_testing,
            "burst_activity": burst,
            "channel_switching": True,
        },
        "avg_transaction_amt": 45.0,
        "max_transaction_amt": 250.0,
        "min_transaction_amt": 1.0,
        "window_transaction_ids": [],
    }
    return adapt("detect_temporal_patterns", raw)


class TestExtractGetCase(unittest.TestCase):

    def setUp(self):
        reset_counter()

    def test_extracts_risk_score(self):
        result = _make_get_case_result(risk_score=0.75)
        evs = extract_evidence(result)
        claims = [e.claim for e in evs]
        self.assertTrue(any("0.75" in c for c in claims))

    def test_extracts_trigger_type(self):
        result = _make_get_case_result(trigger="customer_report")
        evs = extract_evidence(result)
        self.assertTrue(any("customer_report" in e.claim for e in evs))

    def test_extracts_channel(self):
        result = _make_get_case_result(channel="online")
        evs = extract_evidence(result)
        self.assertTrue(any("online" in e.claim.lower() for e in evs))

    def test_all_items_have_source_type(self):
        result = _make_get_case_result()
        evs = extract_evidence(result)
        for ev in evs:
            self.assertEqual(ev.source_type, EvidenceSourceType.MCP_GET_CASE)

    def test_all_items_have_retrieval_method(self):
        result = _make_get_case_result()
        evs = extract_evidence(result)
        for ev in evs:
            self.assertEqual(ev.retrieval_method, "get_case")

    def test_evidence_ids_unique(self):
        result = _make_get_case_result()
        evs = extract_evidence(result)
        ids = [e.evidence_id for e in evs]
        self.assertEqual(len(ids), len(set(ids)))

    def test_failed_result_returns_empty(self):
        raw = {"found": False, "case_id": "HHG-999", "error": "Not found"}
        result = adapt("get_case", raw)
        evs = extract_evidence(result)
        self.assertEqual(evs, [])


class TestExtractPriorCases(unittest.TestCase):

    def setUp(self):
        reset_counter()

    def test_extracts_fraud_count(self):
        result = _make_prior_cases_result(fraud_cases=4)
        evs = extract_evidence(result)
        self.assertTrue(any("4" in e.claim for e in evs))

    def test_extracts_top_pattern(self):
        result = _make_prior_cases_result(fraud_cases=3)
        evs = extract_evidence(result)
        self.assertTrue(any("card_not_present_fraud" in e.claim for e in evs))

    def test_source_type_correct(self):
        result = _make_prior_cases_result()
        evs = extract_evidence(result)
        for ev in evs:
            self.assertEqual(ev.source_type, EvidenceSourceType.MCP_PRIOR_CASES)


class TestExtractTemporalPatterns(unittest.TestCase):

    def setUp(self):
        reset_counter()

    def test_card_testing_signal_extracted(self):
        result = _make_temporal_result(card_testing=True)
        evs = extract_evidence(result)
        self.assertTrue(any("card testing" in e.claim.lower() for e in evs))

    def test_no_signals_produces_negative_evidence(self):
        raw = {
            "customer_id": "C99999",
            "total_transactions": 10,
            "window_hours": 24,
            "transactions_in_window": 1,
            "micro_transaction_count": 0,
            "online_transaction_count": 1,
            "in_person_transaction_count": 0,
            "signals": {"card_testing": False, "burst_activity": False, "channel_switching": False},
            "avg_transaction_amt": 100.0,
            "max_transaction_amt": 100.0,
            "min_transaction_amt": 100.0,
            "window_transaction_ids": [],
        }
        result = adapt("detect_temporal_patterns", raw)
        evs = extract_evidence(result)
        self.assertTrue(any("no temporal fraud signals" in e.claim.lower() for e in evs))


class TestAntiHallucination(unittest.TestCase):
    """Verify extractor never invents values not in the raw result."""

    def setUp(self):
        reset_counter()

    def test_risk_score_matches_raw(self):
        result = _make_get_case_result(risk_score=0.61)
        evs = extract_evidence(result)
        risk_evs = [e for e in evs if "risk score" in e.claim.lower()]
        self.assertTrue(len(risk_evs) > 0)
        self.assertAlmostEqual(float(risk_evs[0].value), 0.61)

    def test_exposure_matches_raw(self):
        raw = {
            "customer_id": "C99999",
            "card_id": None,
            "confirmed_fraud_cases": 2,
            "total_confirmed_exposure_usd": 321.45,
            "avg_fraud_exposure_usd": 160.72,
            "pending_investigation_txns": [],
            "pending_exposure_usd": 0.0,
            "fraud_cases_detail": [],
        }
        result = adapt("calculate_exposure", raw)
        evs = extract_evidence(result)
        exposure_evs = [e for e in evs if isinstance(e.value, dict) and "total_usd" in e.value]
        self.assertTrue(len(exposure_evs) > 0)
        self.assertAlmostEqual(exposure_evs[0].value["total_usd"], 321.45)


if __name__ == "__main__":
    unittest.main(verbosity=2)
