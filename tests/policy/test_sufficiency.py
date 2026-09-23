"""
tests/policy/test_sufficiency.py — Sufficiency engine tests.

Mandatory assertions required by the task:
  1. Insufficient evidence remains INSUFFICIENT after retry limit.
  2. Retry exhaustion does NOT authorize a disruptive action.
  3. New evidence CAN legitimately change INSUFFICIENT → SUFFICIENT.
  4. BLOCK_CARD is only recommended when sufficiency/policy requirements are met.
"""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

import unittest

from agent.evidence.extractor import reset_counter
from agent.state.models import (
    ActionType,
    ApprovalRoute,
    CandidateAction,
    Evidence,
    EvidenceSourceType,
    SufficiencyLevel,
    SufficiencyResult,
    UncertaintyAssessment,
    UncertaintyLevel,
)
from agent.sufficiency.engine import SufficiencyEngine
from agent.sufficiency.config import MAX_REASSESSMENTS
from agent.policy.evaluator import PolicyEvaluator
from agent.policy.action_guard import ActionGuard


# ── Helpers ───────────────────────────────────────────────────────────────────

def _make_evidence(source: EvidenceSourceType, claim: str, value=None) -> Evidence:
    reset_counter()
    return Evidence(
        evidence_id="EV-T01",
        source_type=source,
        source_id="C99999",
        claim=claim,
        value=value,
        retrieval_method=source.value,
    )


def _zero_evidence_result() -> tuple:
    """Evidence state with no items — genuinely insufficient."""
    return [], [], [], set()


def _partial_evidence_result() -> tuple:
    """Covers TRANSACTION + CUSTOMER but not HISTORICAL or EXPOSURE."""
    ev1 = Evidence(
        evidence_id="EV-001",
        source_type=EvidenceSourceType.MCP_GET_CASE,
        source_id="C99999",
        claim="Case HHG-T has risk score 0.75",
        value=0.75,
        retrieval_method="get_case",
    )
    ev2 = Evidence(
        evidence_id="EV-002",
        source_type=EvidenceSourceType.MCP_CUSTOMER_HISTORY,
        source_id="C99999",
        claim="Customer C99999 has 5 transactions",
        value=5,
        retrieval_method="get_customer_history",
    )
    ev2_support = Evidence(
        evidence_id="EV-003",
        source_type=EvidenceSourceType.MCP_CUSTOMER_HISTORY,
        source_id="C99999",
        claim="Customer C99999 has 2 prior confirmed fraud cases",
        value=2,
        retrieval_method="get_customer_history",
    )
    evidence = [ev1, ev2, ev2_support]
    supporting = [ev2_support]
    contradictory = []
    tools_called = {"get_case", "get_customer_history"}
    return evidence, supporting, contradictory, tools_called


def _full_evidence_result() -> tuple:
    """Covers TRANSACTION + CUSTOMER + HISTORICAL + EXPOSURE — genuinely sufficient."""
    ev1 = Evidence(
        evidence_id="EV-001",
        source_type=EvidenceSourceType.MCP_GET_CASE,
        source_id="C99999",
        claim="Case HHG-T has risk score 0.87",
        value=0.87,
        retrieval_method="get_case",
    )
    ev2 = Evidence(
        evidence_id="EV-002",
        source_type=EvidenceSourceType.MCP_CUSTOMER_HISTORY,
        source_id="C99999",
        claim="Customer C99999 has 50 transactions",
        value=50,
        retrieval_method="get_customer_history",
    )
    ev3 = Evidence(
        evidence_id="EV-003",
        source_type=EvidenceSourceType.MCP_PRIOR_CASES,
        source_id="C99999",
        claim="Found 3 prior fraud cases",
        value={"total_cases": 3, "fraud_cases": 3, "exposure_usd": 450.0},
        retrieval_method="find_prior_cases",
    )
    ev4 = Evidence(
        evidence_id="EV-004",
        source_type=EvidenceSourceType.MCP_EXPOSURE,
        source_id="C99999",
        claim="Financial exposure: $450.00 confirmed",
        value={"confirmed_usd": 450.0, "pending_usd": 0.0, "total_usd": 450.0},
        retrieval_method="calculate_exposure",
    )
    evidence = [ev1, ev2, ev3, ev4]
    supporting = [ev1, ev3, ev4]
    contradictory = []
    tools_called = {
        "get_case", "get_customer_history", "find_prior_cases", "calculate_exposure"
    }
    return evidence, supporting, contradictory, tools_called


def _make_uncertainty(level: UncertaintyLevel = UncertaintyLevel.MEDIUM) -> UncertaintyAssessment:
    return UncertaintyAssessment(
        level=level,
        reason=f"Test uncertainty: {level.value}",
    )


# ── Test 1: Insufficient remains INSUFFICIENT after retry limit ───────────────

class TestRetryLimitPreservesInsufficiency(unittest.TestCase):
    """
    REQUIREMENT: Retry exhaustion must NOT change INSUFFICIENT → SUFFICIENT.
    The retry limit prevents an infinite loop; it does not change the
    meaning of the evidence.
    """

    def setUp(self):
        self.engine = SufficiencyEngine()

    def test_zero_evidence_is_insufficient_at_retry_0(self):
        ev, sup, contra, tools = _zero_evidence_result()
        result = self.engine.evaluate(ev, sup, contra, tools, reassessment_count=0)
        self.assertEqual(result.level, SufficiencyLevel.INSUFFICIENT)
        self.assertFalse(result.sufficient)

    def test_zero_evidence_is_still_insufficient_at_retry_limit(self):
        """CRITICAL: retry limit must not upgrade INSUFFICIENT to SUFFICIENT."""
        ev, sup, contra, tools = _zero_evidence_result()
        result = self.engine.evaluate(
            ev, sup, contra, tools,
            reassessment_count=MAX_REASSESSMENTS
        )
        self.assertEqual(
            result.level, SufficiencyLevel.INSUFFICIENT,
            "Retry limit must not change INSUFFICIENT to SUFFICIENT"
        )
        self.assertFalse(
            result.sufficient,
            "sufficient=True must never be returned for zero evidence regardless of retry count"
        )

    def test_zero_evidence_is_still_insufficient_well_above_retry_limit(self):
        """Even if reassessment_count is far above MAX, evidence state is truthful."""
        ev, sup, contra, tools = _zero_evidence_result()
        result = self.engine.evaluate(
            ev, sup, contra, tools,
            reassessment_count=MAX_REASSESSMENTS + 10
        )
        self.assertFalse(result.sufficient)
        self.assertEqual(result.level, SufficiencyLevel.INSUFFICIENT)

    def test_partial_evidence_stays_partial_at_retry_limit(self):
        """PARTIAL evidence is not upgraded to SUFFICIENT by retry exhaustion."""
        ev, sup, contra, tools = _partial_evidence_result()
        result = self.engine.evaluate(
            ev, sup, contra, tools,
            reassessment_count=MAX_REASSESSMENTS
        )
        # With TRANSACTION + CUSTOMER but no HISTORICAL/EXPOSURE → PARTIAL
        self.assertIn(result.level, [SufficiencyLevel.PARTIAL, SufficiencyLevel.INSUFFICIENT],
                      "Partial evidence must not be upgraded to SUFFICIENT by retry")
        self.assertNotEqual(
            result.level, SufficiencyLevel.SUFFICIENT,
            "SUFFICIENT must not be returned for partial evidence at retry limit"
        )

    def test_retry_note_in_reason_when_limit_reached(self):
        """Reason string must mention retry limit when it is reached."""
        ev, sup, contra, tools = _zero_evidence_result()
        result = self.engine.evaluate(
            ev, sup, contra, tools,
            reassessment_count=MAX_REASSESSMENTS
        )
        self.assertIn(
            str(MAX_REASSESSMENTS), result.reason,
            "Reason should mention the retry count when limit is reached"
        )


# ── Test 2: Retry exhaustion cannot authorize BLOCK_CARD ─────────────────────

class TestRetryExhaustionCannotAuthorizeBLOCK_CARD(unittest.TestCase):
    """
    REQUIREMENT: An INSUFFICIENT case must never result in BLOCK_CARD,
    even after retry exhaustion. This is enforced by:
      - SufficiencyEngine returning truthful INSUFFICIENT
      - PolicyEvaluator's RULE-001 requiring SUFFICIENT
      - ActionGuard blocking BLOCK_CARD on INSUFFICIENT
    """

    def setUp(self):
        self.engine = SufficiencyEngine()
        self.evaluator = PolicyEvaluator()
        self.guard = ActionGuard()

    def _run_policy(self, suf: SufficiencyResult) -> CandidateAction:
        unc = _make_uncertainty(UncertaintyLevel.HIGH)
        decision, candidates = self.evaluator.evaluate(
            sufficiency=suf,
            uncertainty=unc,
            supporting_count=suf.supporting_count,
            contradictory_count=suf.contradictory_count,
            total_exposure_usd=0.0,
            trigger_type="risk_score",
        )
        best = next(
            (c for c in candidates if c.action == decision.action), candidates[0]
        )
        return self.guard.validate(
            action=best,
            sufficiency=suf,
            uncertainty=unc,
            supporting_count=suf.supporting_count,
        )

    def test_block_card_not_in_policy_candidates_for_insufficient(self):
        ev, sup, contra, tools = _zero_evidence_result()
        suf = self.engine.evaluate(ev, sup, contra, tools, reassessment_count=MAX_REASSESSMENTS)
        _, candidates = self.evaluator.evaluate(
            sufficiency=suf,
            uncertainty=_make_uncertainty(),
            supporting_count=0,
            contradictory_count=0,
            total_exposure_usd=0.0,
            trigger_type="risk_score",
        )
        candidate_actions = [c.action for c in candidates]
        self.assertNotIn(
            ActionType.BLOCK_CARD, candidate_actions,
            "BLOCK_CARD must not appear in policy candidates for INSUFFICIENT evidence"
        )

    def test_action_guard_blocks_block_card_on_insufficient(self):
        """ActionGuard must downgrade BLOCK_CARD to safe action when evidence is INSUFFICIENT."""
        suf = SufficiencyResult(
            sufficient=False,
            level=SufficiencyLevel.INSUFFICIENT,
            supporting_count=0,
            contradictory_count=0,
            reason="test",
        )
        dangerous = CandidateAction(
            action=ActionType.BLOCK_CARD,
            reason="hypothetically trying to block",
            policy_basis="TEST",
        )
        result = self.guard.validate(
            action=dangerous,
            sufficiency=suf,
            uncertainty=_make_uncertainty(),
            supporting_count=0,
        )
        self.assertNotEqual(
            result.action, ActionType.BLOCK_CARD,
            "ActionGuard must not allow BLOCK_CARD when evidence is INSUFFICIENT"
        )

    def test_final_action_for_retry_exhausted_case_is_safe(self):
        """Full pipeline: zero evidence + retry limit → safe action, not BLOCK_CARD."""
        ev, sup, contra, tools = _zero_evidence_result()
        suf = self.engine.evaluate(ev, sup, contra, tools, reassessment_count=MAX_REASSESSMENTS)
        final = self._run_policy(suf)
        self.assertNotEqual(
            final.action, ActionType.BLOCK_CARD,
            "A retry-exhausted insufficient case must never result in BLOCK_CARD"
        )
        # The safe actions for INSUFFICIENT are:
        safe_actions = {
            ActionType.REQUEST_MORE_EVIDENCE,
            ActionType.MONITOR,
            ActionType.ESCALATE,
            ActionType.VERIFY_WITH_CUSTOMER,
        }
        self.assertIn(
            final.action, safe_actions,
            f"Expected a safe action but got: {final.action}"
        )

    def test_request_more_evidence_rule_fires_on_insufficient(self):
        """RULE-007 must match INSUFFICIENT and produce REQUEST_MORE_EVIDENCE."""
        suf = SufficiencyResult(
            sufficient=False,
            level=SufficiencyLevel.INSUFFICIENT,
            supporting_count=0,
            contradictory_count=0,
            reason="test",
        )
        _, candidates = self.evaluator.evaluate(
            sufficiency=suf,
            uncertainty=_make_uncertainty(),
            supporting_count=0,
            contradictory_count=0,
            total_exposure_usd=0.0,
            trigger_type="risk_score",
        )
        candidate_actions = [c.action for c in candidates]
        self.assertIn(
            ActionType.REQUEST_MORE_EVIDENCE, candidate_actions,
            "RULE-007 must produce REQUEST_MORE_EVIDENCE for INSUFFICIENT evidence"
        )


# ── Test 3: New evidence can legitimately change INSUFFICIENT → SUFFICIENT ────

class TestNewEvidenceCanAchieveSufficiency(unittest.TestCase):
    """
    REQUIREMENT: The engine must return SUFFICIENT when genuine additional
    evidence covers all required categories, regardless of retry count.
    """

    def setUp(self):
        self.engine = SufficiencyEngine()

    def test_full_evidence_is_sufficient(self):
        ev, sup, contra, tools = _full_evidence_result()
        result = self.engine.evaluate(ev, sup, contra, tools, reassessment_count=0)
        self.assertEqual(result.level, SufficiencyLevel.SUFFICIENT)
        self.assertTrue(result.sufficient)

    def test_full_evidence_is_sufficient_even_at_retry_limit(self):
        """
        When real evidence covers all categories, SUFFICIENT is returned
        even if reassessment_count == MAX_REASSESSMENTS.
        This proves the fix is not over-restrictive.
        """
        ev, sup, contra, tools = _full_evidence_result()
        result = self.engine.evaluate(
            ev, sup, contra, tools,
            reassessment_count=MAX_REASSESSMENTS
        )
        self.assertEqual(
            result.level, SufficiencyLevel.SUFFICIENT,
            "Full evidence must be SUFFICIENT regardless of retry count"
        )
        self.assertTrue(result.sufficient)

    def test_adding_historical_and_exposure_upgrades_partial_to_sufficient(self):
        """Adding evidence to a PARTIAL case must upgrade it to SUFFICIENT."""
        ev_p, sup_p, contra_p, tools_p = _partial_evidence_result()
        result_partial = self.engine.evaluate(ev_p, sup_p, contra_p, tools_p)
        # Should be PARTIAL or INSUFFICIENT without history/exposure
        self.assertNotEqual(result_partial.level, SufficiencyLevel.SUFFICIENT)

        # Now add historical + exposure evidence
        ev_hist = Evidence(
            evidence_id="EV-H01",
            source_type=EvidenceSourceType.MCP_PRIOR_CASES,
            source_id="C99999",
            claim="3 prior fraud cases",
            value={"total_cases": 3, "fraud_cases": 3, "exposure_usd": 400.0},
            retrieval_method="find_prior_cases",
        )
        ev_exp = Evidence(
            evidence_id="EV-X01",
            source_type=EvidenceSourceType.MCP_EXPOSURE,
            source_id="C99999",
            claim="Financial exposure: $400.00",
            value={"confirmed_usd": 400.0, "pending_usd": 0.0, "total_usd": 400.0},
            retrieval_method="calculate_exposure",
        )
        full_ev = ev_p + [ev_hist, ev_exp]
        full_sup = sup_p + [ev_hist, ev_exp]
        full_tools = tools_p | {"find_prior_cases", "calculate_exposure"}

        result_full = self.engine.evaluate(full_ev, full_sup, contra_p, full_tools)
        self.assertEqual(
            result_full.level, SufficiencyLevel.SUFFICIENT,
            "Adding historical+exposure evidence must upgrade to SUFFICIENT"
        )

    def test_zero_supporting_prevents_sufficient_even_with_all_categories(self):
        """
        All categories covered but zero supporting evidence → not SUFFICIENT.
        Evidence categories alone are not enough; there must be supporting items.
        """
        ev, _, contra, tools = _full_evidence_result()
        result = self.engine.evaluate(
            evidence=ev,
            supporting=[],      # zero supporting
            contradictory=contra,
            tools_called=tools,
            reassessment_count=0,
        )
        # With MIN_SUPPORTING_FOR_ACTION=1 and 0 supporting items,
        # should be PARTIAL or INSUFFICIENT (not SUFFICIENT)
        self.assertNotEqual(
            result.level, SufficiencyLevel.SUFFICIENT,
            "Zero supporting evidence must not yield SUFFICIENT even with all categories covered"
        )


# ── Test 4: BLOCK_CARD only authorized when requirements are genuinely met ────

class TestBLOCK_CARDRequiresGenuineSufficiency(unittest.TestCase):
    """
    REQUIREMENT: BLOCK_CARD must only be recommended when actual
    sufficiency + policy requirements are satisfied.
    """

    def setUp(self):
        self.engine = SufficiencyEngine()
        self.evaluator = PolicyEvaluator()
        self.guard = ActionGuard()

    def test_block_card_is_available_for_genuinely_sufficient_case(self):
        """BLOCK_CARD must appear in candidates when evidence is genuinely SUFFICIENT."""
        ev, sup, contra, tools = _full_evidence_result()
        suf = self.engine.evaluate(ev, sup, contra, tools, reassessment_count=0)
        self.assertEqual(suf.level, SufficiencyLevel.SUFFICIENT)

        _, candidates = self.evaluator.evaluate(
            sufficiency=suf,
            uncertainty=_make_uncertainty(UncertaintyLevel.LOW),
            supporting_count=len(sup),
            contradictory_count=len(contra),
            total_exposure_usd=450.0,
            trigger_type="risk_score",
        )
        candidate_actions = [c.action for c in candidates]
        self.assertIn(
            ActionType.BLOCK_CARD, candidate_actions,
            "BLOCK_CARD must be available when evidence is genuinely SUFFICIENT"
        )

    def test_block_card_survives_action_guard_for_sufficient_case(self):
        """ActionGuard must NOT block BLOCK_CARD when evidence is SUFFICIENT."""
        ev, sup, contra, tools = _full_evidence_result()
        suf = self.engine.evaluate(ev, sup, contra, tools)
        block_action = CandidateAction(
            action=ActionType.BLOCK_CARD,
            reason="Sufficient evidence supports block",
            policy_basis="RULE-001",
            approval_required=True,
            approval_route=ApprovalRoute.FRAUD_ANALYST,
            risk_level="high",
        )
        result = self.guard.validate(
            action=block_action,
            sufficiency=suf,
            uncertainty=_make_uncertainty(UncertaintyLevel.LOW),
            supporting_count=len(sup),
        )
        self.assertEqual(
            result.action, ActionType.BLOCK_CARD,
            "ActionGuard must allow BLOCK_CARD when evidence is genuinely SUFFICIENT"
        )

    def test_block_card_requires_min_2_supporting_items(self):
        """RULE-001 requires min_supporting=2 for BLOCK_CARD."""
        ev, sup, contra, tools = _full_evidence_result()
        suf = self.engine.evaluate(ev, sup, contra, tools)
        # Only 1 supporting item — RULE-001 should not fire
        _, candidates = self.evaluator.evaluate(
            sufficiency=suf,
            uncertainty=_make_uncertainty(UncertaintyLevel.LOW),
            supporting_count=1,   # below RULE-001 min_supporting=2
            contradictory_count=0,
            total_exposure_usd=0.0,
            trigger_type="risk_score",
        )
        candidate_actions = [c.action for c in candidates]
        self.assertNotIn(
            ActionType.BLOCK_CARD, candidate_actions,
            "BLOCK_CARD (RULE-001) requires min_supporting=2, not 1"
        )

    def test_block_card_requires_correct_trigger_type(self):
        """RULE-001 only fires for risk_score/customer_report/analyst_request triggers."""
        ev, sup, contra, tools = _full_evidence_result()
        suf = self.engine.evaluate(ev, sup, contra, tools)
        _, candidates = self.evaluator.evaluate(
            sufficiency=suf,
            uncertainty=_make_uncertainty(UncertaintyLevel.LOW),
            supporting_count=3,
            contradictory_count=0,
            total_exposure_usd=100.0,
            trigger_type="unknown_trigger",  # not in allowed list
        )
        candidate_actions = [c.action for c in candidates]
        self.assertNotIn(
            ActionType.BLOCK_CARD, candidate_actions,
            "BLOCK_CARD must not fire for unknown trigger type"
        )


if __name__ == "__main__":
    unittest.main(verbosity=2)
