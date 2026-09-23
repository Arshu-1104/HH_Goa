"""Tests for agent state models and initial state creation."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

import unittest
from agent.state.state import create_initial_state, InvestigationState
from agent.state.models import (
    InvestigationStatus, Evidence, Hypothesis, HypothesisStatus,
    EvidenceSourceType, ActionType, FraudPattern,
)


class TestCreateInitialState(unittest.TestCase):

    def test_case_id_set(self):
        s = create_initial_state("HHG-001")
        self.assertEqual(s["case_id"], "HHG-001")

    def test_status_is_pending(self):
        s = create_initial_state("HHG-001")
        self.assertEqual(s["investigation_status"], InvestigationStatus.PENDING)

    def test_evidence_empty(self):
        s = create_initial_state("HHG-001")
        self.assertEqual(s["evidence"], [])

    def test_errors_empty(self):
        s = create_initial_state("HHG-001")
        self.assertEqual(s["errors"], [])

    def test_reassessment_count_zero(self):
        s = create_initial_state("HHG-001")
        self.assertEqual(s["reassessment_count"], 0)

    def test_started_at_set(self):
        s = create_initial_state("HHG-001")
        self.assertNotEqual(s["started_at"], "")

    def test_messages_empty(self):
        s = create_initial_state("HHG-001")
        self.assertEqual(s["messages"], [])


class TestEvidenceModel(unittest.TestCase):

    def test_evidence_creation(self):
        ev = Evidence(
            evidence_id="EV-001",
            source_type=EvidenceSourceType.MCP_GET_CASE,
            source_id="HHG-001",
            claim="Case has risk score 0.87",
            value=0.87,
            retrieval_method="get_case",
        )
        self.assertEqual(ev.evidence_id, "EV-001")
        self.assertEqual(ev.confidence, 1.0)
        self.assertEqual(ev.supports, [])
        self.assertEqual(ev.contradicts, [])

    def test_evidence_supports_links(self):
        ev = Evidence(
            evidence_id="EV-002",
            source_type=EvidenceSourceType.MCP_PRIOR_CASES,
            source_id="C12382",
            claim="4 prior fraud cases",
            value=4,
        )
        ev.supports.append("HYP-001")
        self.assertIn("HYP-001", ev.supports)


class TestHypothesisModel(unittest.TestCase):

    def test_default_status_active(self):
        h = Hypothesis(
            hypothesis_id="HYP-001",
            name="card_not_present_fraud",
            description="CNP fraud",
        )
        self.assertEqual(h.status, HypothesisStatus.ACTIVE)
        self.assertEqual(h.confidence, 0.5)

    def test_confidence_clamped(self):
        # Pydantic should reject values outside [0, 1]
        import pytest
        from pydantic import ValidationError
        with self.assertRaises(ValidationError):
            Hypothesis(
                hypothesis_id="HYP-X",
                name="test",
                description="test",
                confidence=1.5,  # invalid
            )


class TestFraudPatternEnum(unittest.TestCase):

    def test_all_official_patterns_present(self):
        expected = {
            "account_takeover", "card_not_present_fraud",
            "card_not_present_new_device", "card_testing",
            "out_of_region_use", "undocumented", "none",
        }
        actual = {p.value for p in FraudPattern}
        self.assertEqual(actual, expected)


if __name__ == "__main__":
    unittest.main(verbosity=2)
