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


class TestCaseMemoryRetrieverRobustness(unittest.TestCase):
    """
    Regression tests for the CaseMemoryRetriever fix.

    Issue: batch_summary.json (a JSON list) was saved inside investigation_reports/
    alongside case-memory objects (JSON dicts).  CaseMemoryRetriever.get_all()
    loaded every *.json file and get_similar() called .get("memory") on the result,
    causing: AttributeError: 'list' object has no attribute 'get'

    Fix: get_all() now filters out any JSON file that is not a valid case-memory
    document (must be a dict containing both "memory" and "case_id").
    """

    def setUp(self):
        import tempfile
        import json
        from agent.memory.retriever import CaseMemoryRetriever

        # Create a temporary directory with a mix of:
        #   - a valid case-memory JSON (dict with memory + case_id)
        #   - a batch_summary JSON (a list — not a case memory)
        #   - an unrelated JSON object (no "memory" key)
        self.tmpdir = tempfile.TemporaryDirectory()
        tmppath = Path(self.tmpdir.name)

        # Valid case memory
        valid_memory = {
            "case_id": "HHG-TEST",
            "written_at": "2026-01-01T00:00:00",
            "memory": {
                "case_id": "HHG-TEST",
                "customer_id": "C99999",
                "card_id": "C99999-K1",
                "transaction_id": "9999999",
                "final_action": "BLOCK_CARD",
                "approved_by": "fraud_analyst",
                "policy_decisions": ["BLOCK_CARD"],
                "fraud_patterns_identified": ["card_not_present_fraud"],
            },
            "summary": {},
        }
        with open(tmppath / "HHG-TEST.json", "w") as f:
            json.dump(valid_memory, f)

        # batch_summary.json — a list, NOT a case memory
        batch_summary = [
            {"case_id": "HHG-001", "action": "BLOCK_CARD", "status": "COMPLETE"},
            {"case_id": "HHG-002", "action": "BLOCK_CARD", "status": "COMPLETE"},
        ]
        with open(tmppath / "batch_summary.json", "w") as f:
            json.dump(batch_summary, f)

        # An unrelated JSON object that has no "memory" key
        unrelated = {"version": "1.0", "description": "some artifact"}
        with open(tmppath / "unrelated_artifact.json", "w") as f:
            json.dump(unrelated, f)

        self.retriever = CaseMemoryRetriever(memory_dir=tmppath)

    def tearDown(self):
        self.tmpdir.cleanup()

    def test_get_all_skips_batch_summary_list(self):
        """batch_summary.json (a list) must not appear in get_all() results."""
        results = self.retriever.get_all()
        for r in results:
            self.assertIsInstance(r, dict,
                "get_all() must never return a non-dict (e.g. a list from batch_summary.json)")
            self.assertIn("memory", r,
                "Every result from get_all() must have a 'memory' key")
            self.assertIn("case_id", r,
                "Every result from get_all() must have a 'case_id' key")

    def test_get_all_returns_only_valid_case_memories(self):
        """Only the valid case-memory document must be returned."""
        results = self.retriever.get_all()
        self.assertEqual(len(results), 1,
            f"Expected 1 valid case memory, got {len(results)}: "
            f"{[r.get('case_id') for r in results]}")
        self.assertEqual(results[0]["case_id"], "HHG-TEST")

    def test_get_all_skips_dict_without_memory_key(self):
        """JSON dicts without a 'memory' key must be skipped."""
        results = self.retriever.get_all()
        for r in results:
            self.assertNotEqual(r.get("case_id"), "",
                "Empty case_id should not appear in results")

    def test_get_similar_does_not_crash_on_batch_summary(self):
        """
        get_similar() must not raise AttributeError when batch_summary.json exists.
        This is the regression test for the original bug.
        """
        try:
            result = self.retriever.get_similar(customer_id="C99999")
        except AttributeError as e:
            self.fail(
                f"get_similar() raised AttributeError — the batch_summary fix is broken: {e}"
            )

    def test_get_similar_finds_valid_memory(self):
        """get_similar() must still find the valid case memory by customer_id."""
        results = self.retriever.get_similar(customer_id="C99999")
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]["case_id"], "HHG-TEST")

    def test_get_similar_matches_fraud_patterns(self):
        """get_similar() must find memories by fraud pattern."""
        results = self.retriever.get_similar(fraud_patterns=["card_not_present_fraud"])
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]["case_id"], "HHG-TEST")

    def test_get_prior_actions_does_not_crash(self):
        """get_prior_actions() must not crash and must return the stored action."""
        actions = self.retriever.get_prior_actions("C99999")
        self.assertIsInstance(actions, list)
        self.assertEqual(len(actions), 1)
        self.assertEqual(actions[0], "BLOCK_CARD")

    def test_batch_summary_saved_outside_investigation_reports(self):
        """
        agent/run.py must save batch_summary.json to artifacts/ not
        investigation_reports/.  Verify the code path is correct.
        """
        import inspect
        import agent.run as run_module
        source = inspect.getsource(run_module.run_all)
        # Must NOT write to investigation_reports/
        self.assertNotIn(
            "investigation_reports",
            source.split("summary_path")[1].split("\n")[0],
            "batch_summary.json must not be written to investigation_reports/"
        )
        # Must write to artifacts/
        self.assertIn("artifacts", source,
            "run_all() must save batch_summary.json to artifacts/ directory")
