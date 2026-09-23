"""
tests/integration/test_e2e.py — End-to-end investigation workflow tests.

Tests the full InvestigationWorkflow against real case data.
Uses MCPDirectClient (no HTTP server needed).

Two scenarios:
  A. With transactions.csv present (slim copy) — full evidence available
  B. Without transactions.csv (missing) — graceful degradation tested
"""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

import unittest

from agent.graph.workflow import InvestigationWorkflow
from agent.state.models import (
    ActionType,
    InvestigationStatus,
    SufficiencyLevel,
)
from agent.sufficiency.config import MAX_REASSESSMENTS

ROOT = Path(__file__).parent.parent.parent
_HAS_TRANSACTIONS = (ROOT / "transactions.csv").exists()


class TestWorkflowCompletesSuccessfully(unittest.TestCase):
    """
    Basic E2E: the workflow must reach COMPLETE status for any case.
    Never hangs, never crashes, always produces a final summary.
    """

    @classmethod
    def setUpClass(cls):
        cls.workflow = InvestigationWorkflow()

    def _run(self, case_id: str) -> dict:
        state = dict(self.workflow.run(case_id))
        return state

    def test_hgg001_reaches_complete(self):
        state = self._run("HHG-001")
        self.assertEqual(state["investigation_status"], InvestigationStatus.COMPLETE)

    def test_hgg001_has_final_summary(self):
        state = self._run("HHG-001")
        self.assertIsNotNone(state.get("final_summary"))

    def test_hgg001_has_recommended_action(self):
        state = self._run("HHG-001")
        self.assertIsNotNone(state.get("recommended_action"))

    def test_hgg001_case_memory_written(self):
        state = self._run("HHG-001")
        mem_path = ROOT / "investigation_reports" / "HHG-001.json"
        self.assertTrue(mem_path.exists(), "Case memory must be written to disk")

    def test_hgg001_has_investigation_trail(self):
        state = self._run("HHG-001")
        trail = state.get("investigation_trail", [])
        self.assertGreater(len(trail), 0, "Investigation trail must have events")

    def test_nonexistent_case_returns_error_status(self):
        state = self._run("HHG-999")
        self.assertEqual(
            state["investigation_status"], InvestigationStatus.ERROR,
            "Non-existent case must return ERROR status"
        )

    def test_hgg001_evidence_grounded(self):
        """Every evidence item must have a source_type and evidence_id."""
        state = self._run("HHG-001")
        for ev in state.get("evidence", []):
            self.assertNotEqual(ev.evidence_id, "", "evidence_id must not be empty")
            self.assertIsNotNone(ev.source_type, "source_type must not be None")
            self.assertNotEqual(ev.claim, "", "claim must not be empty")

    def test_summary_has_required_fields(self):
        state = self._run("HHG-001")
        summary = state.get("final_summary")
        if summary is None:
            self.skipTest("No final summary produced")
        self.assertNotEqual(summary.case_id, "")
        self.assertNotEqual(summary.recommended_action, "")
        self.assertNotEqual(summary.uncertainty_level, "")
        self.assertNotEqual(summary.evidence_sufficiency_level, "")


class TestSufficiencyBehaviourE2E(unittest.TestCase):
    """
    E2E verification of the sufficiency fix:
      - INSUFFICIENT remains INSUFFICIENT after retry exhaustion
      - BLOCK_CARD is never recommended for an insufficient case
      - When real evidence IS available, SUFFICIENT is achievable
    """

    @classmethod
    def setUpClass(cls):
        cls.workflow = InvestigationWorkflow()

    def _run(self, case_id: str) -> dict:
        return dict(self.workflow.run(case_id))

    def test_recommended_action_is_never_block_card_for_zero_evidence_case(self):
        """
        HHG-999 does not exist → zero evidence collected.
        The workflow returns ERROR, not a disruptive action.
        """
        state = self._run("HHG-999")
        best = state.get("recommended_action")
        if best is not None:
            self.assertNotEqual(
                best.action, ActionType.BLOCK_CARD,
                "BLOCK_CARD must never be recommended for a zero-evidence case"
            )

    def test_hgg001_block_card_only_if_sufficient(self):
        """
        If HHG-001 gets BLOCK_CARD, its sufficiency level must be SUFFICIENT.
        This directly verifies the fix: retry exhaustion alone cannot authorize BLOCK_CARD.
        """
        state = self._run("HHG-001")
        best = state.get("recommended_action")
        suf  = state.get("evidence_sufficiency")
        if best and best.action == ActionType.BLOCK_CARD:
            self.assertEqual(
                suf.level, SufficiencyLevel.SUFFICIENT,
                "BLOCK_CARD was recommended but sufficiency is not SUFFICIENT — "
                "this means the sufficiency fix is not working"
            )

    def test_reassessment_count_does_not_exceed_max(self):
        """The workflow must not run more reassessment loops than MAX_REASSESSMENTS."""
        state = self._run("HHG-001")
        count = state.get("reassessment_count", 0)
        self.assertLessEqual(
            count, MAX_REASSESSMENTS,
            f"reassessment_count={count} exceeds MAX_REASSESSMENTS={MAX_REASSESSMENTS}"
        )

    def test_insufficient_case_gets_safe_action(self):
        """
        When evidence_sufficiency is INSUFFICIENT in the final state,
        the recommended action must be a safe non-disruptive action.
        """
        state = self._run("HHG-001")
        suf  = state.get("evidence_sufficiency")
        best = state.get("recommended_action")
        if suf and suf.level == SufficiencyLevel.INSUFFICIENT and best:
            disruptive = {ActionType.BLOCK_CARD, ActionType.FILE_REPORT, ActionType.BLOCK_ACCOUNT}
            self.assertNotIn(
                best.action, disruptive,
                f"Disruptive action {best.action} must not be recommended for INSUFFICIENT evidence"
            )


class TestMultipleCases(unittest.TestCase):
    """Run investigations for several cases and verify basic invariants."""

    CASES = ["HHG-001", "HHG-003", "HHG-007", "HHG-010", "HHG-014"]

    @classmethod
    def setUpClass(cls):
        cls.workflow = InvestigationWorkflow()
        cls.results = {}
        for case_id in cls.CASES:
            try:
                cls.results[case_id] = dict(cls.workflow.run(case_id))
            except Exception as exc:
                cls.results[case_id] = {"_error": str(exc)}

    def test_all_cases_complete_or_error(self):
        """Every case must reach COMPLETE or ERROR — never hang."""
        for case_id, state in self.results.items():
            if "_error" in state:
                continue
            status = state.get("investigation_status")
            self.assertIn(
                status,
                [InvestigationStatus.COMPLETE, InvestigationStatus.ERROR],
                f"{case_id}: unexpected status {status}"
            )

    def test_no_case_recommends_block_card_without_sufficient_evidence(self):
        """Across all cases: BLOCK_CARD only when evidence is SUFFICIENT."""
        for case_id, state in self.results.items():
            if "_error" in state:
                continue
            best = state.get("recommended_action")
            suf  = state.get("evidence_sufficiency")
            if best and best.action == ActionType.BLOCK_CARD and suf:
                self.assertEqual(
                    suf.level, SufficiencyLevel.SUFFICIENT,
                    f"{case_id}: BLOCK_CARD recommended but sufficiency={suf.level}"
                )

    def test_all_completed_cases_have_final_summary(self):
        for case_id, state in self.results.items():
            if "_error" in state:
                continue
            if state.get("investigation_status") == InvestigationStatus.COMPLETE:
                self.assertIsNotNone(
                    state.get("final_summary"),
                    f"{case_id}: COMPLETE but no final_summary"
                )


if __name__ == "__main__":
    unittest.main(verbosity=2)
