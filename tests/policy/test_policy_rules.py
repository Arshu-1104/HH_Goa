"""
tests/policy/test_policy_rules.py — Policy evaluator and action guard tests.
"""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

import unittest

from agent.state.models import (
    ActionType, ApprovalRoute, CandidateAction,
    SufficiencyLevel, SufficiencyResult, UncertaintyAssessment, UncertaintyLevel,
)
from agent.policy.evaluator import PolicyEvaluator
from agent.policy.action_guard import ActionGuard
from agent.policy.approvals import ApprovalRouter


def _suf(level: SufficiencyLevel, sup: int = 2, contra: int = 0) -> SufficiencyResult:
    return SufficiencyResult(
        sufficient=level != SufficiencyLevel.INSUFFICIENT,
        level=level,
        supporting_count=sup,
        contradictory_count=contra,
        reason="test",
    )


def _unc(level: UncertaintyLevel = UncertaintyLevel.MEDIUM) -> UncertaintyAssessment:
    return UncertaintyAssessment(level=level, reason="test")


class TestPolicyEvaluatorRules(unittest.TestCase):

    def setUp(self):
        self.ev = PolicyEvaluator()

    # RULE-001: BLOCK_CARD requires SUFFICIENT + min 2 supporting
    def test_rule_001_fires_on_sufficient(self):
        decision, candidates = self.ev.evaluate(
            sufficiency=_suf(SufficiencyLevel.SUFFICIENT, sup=3),
            uncertainty=_unc(UncertaintyLevel.LOW),
            supporting_count=3, contradictory_count=0,
            total_exposure_usd=100.0, trigger_type="risk_score",
        )
        actions = [c.action for c in candidates]
        self.assertIn(ActionType.BLOCK_CARD, actions)

    def test_rule_001_does_not_fire_on_insufficient(self):
        _, candidates = self.ev.evaluate(
            sufficiency=_suf(SufficiencyLevel.INSUFFICIENT, sup=0),
            uncertainty=_unc(), supporting_count=0, contradictory_count=0,
            total_exposure_usd=0.0, trigger_type="risk_score",
        )
        self.assertNotIn(ActionType.BLOCK_CARD, [c.action for c in candidates])

    def test_rule_001_does_not_fire_on_partial(self):
        _, candidates = self.ev.evaluate(
            sufficiency=_suf(SufficiencyLevel.PARTIAL, sup=2),
            uncertainty=_unc(), supporting_count=2, contradictory_count=0,
            total_exposure_usd=100.0, trigger_type="risk_score",
        )
        self.assertNotIn(ActionType.BLOCK_CARD, [c.action for c in candidates])

    # RULE-002: FILE_REPORT requires SUFFICIENT + min 3 supporting + $500 exposure
    def test_rule_002_fires_on_high_exposure(self):
        _, candidates = self.ev.evaluate(
            sufficiency=_suf(SufficiencyLevel.SUFFICIENT, sup=4),
            uncertainty=_unc(UncertaintyLevel.LOW),
            supporting_count=4, contradictory_count=0,
            total_exposure_usd=600.0, trigger_type="risk_score",
        )
        self.assertIn(ActionType.FILE_REPORT, [c.action for c in candidates])

    def test_rule_002_does_not_fire_below_exposure_threshold(self):
        _, candidates = self.ev.evaluate(
            sufficiency=_suf(SufficiencyLevel.SUFFICIENT, sup=4),
            uncertainty=_unc(UncertaintyLevel.LOW),
            supporting_count=4, contradictory_count=0,
            total_exposure_usd=100.0, trigger_type="risk_score",  # below $500
        )
        self.assertNotIn(ActionType.FILE_REPORT, [c.action for c in candidates])

    # RULE-003: VERIFY_WITH_CUSTOMER on customer_report trigger
    def test_rule_003_fires_on_customer_report(self):
        _, candidates = self.ev.evaluate(
            sufficiency=_suf(SufficiencyLevel.PARTIAL, sup=1),
            uncertainty=_unc(), supporting_count=1, contradictory_count=0,
            total_exposure_usd=0.0, trigger_type="customer_report",
        )
        self.assertIn(ActionType.VERIFY_WITH_CUSTOMER, [c.action for c in candidates])

    # RULE-007: REQUEST_MORE_EVIDENCE on INSUFFICIENT
    def test_rule_007_fires_on_insufficient(self):
        _, candidates = self.ev.evaluate(
            sufficiency=_suf(SufficiencyLevel.INSUFFICIENT, sup=0),
            uncertainty=_unc(), supporting_count=0, contradictory_count=0,
            total_exposure_usd=0.0, trigger_type="risk_score",
        )
        self.assertIn(ActionType.REQUEST_MORE_EVIDENCE, [c.action for c in candidates])

    def test_fallback_always_produces_candidates(self):
        """Even a pathological state produces at least one candidate."""
        # Use a trigger type not in any rule's whitelist and PARTIAL with no supporting
        _, candidates = self.ev.evaluate(
            sufficiency=_suf(SufficiencyLevel.PARTIAL, sup=0),
            uncertainty=_unc(), supporting_count=0, contradictory_count=0,
            total_exposure_usd=0.0, trigger_type="unknown_xyz",
        )
        self.assertGreater(len(candidates), 0)

    def test_high_uncertainty_reduces_block_card_priority(self):
        """
        Under HIGH uncertainty, BLOCK_CARD priority is reduced from 7 to 3.
        When other candidates (FILE_REPORT priority 6, ESCALATE priority 5)
        are present, BLOCK_CARD must lose.
        We verify: (a) BLOCK_CARD is not the decision, (b) a higher-priority
        safe alternative wins.
        """
        decision, candidates = self.ev.evaluate(
            sufficiency=_suf(SufficiencyLevel.SUFFICIENT, sup=4),
            uncertainty=_unc(UncertaintyLevel.HIGH),
            supporting_count=4, contradictory_count=0,
            total_exposure_usd=600.0,  # triggers RULE-002 (FILE_REPORT) + RULE-006 (ESCALATE)
            trigger_type="risk_score",
        )
        # BLOCK_CARD priority reduced to 3 under HIGH uncertainty.
        # FILE_REPORT (6) or ESCALATE (5) should win.
        self.assertNotEqual(
            decision.action, ActionType.BLOCK_CARD,
            "Under HIGH uncertainty, BLOCK_CARD must not be the best pick "
            "when higher-priority candidates are available"
        )
        # Winning action must be FILE_REPORT or ESCALATE
        self.assertIn(
            decision.action, {ActionType.FILE_REPORT, ActionType.ESCALATE},
            f"Expected FILE_REPORT or ESCALATE to win under HIGH uncertainty, got {decision.action}"
        )


class TestActionGuard(unittest.TestCase):

    def setUp(self):
        self.guard = ActionGuard()
        self.suf_insuf = _suf(SufficiencyLevel.INSUFFICIENT, sup=0)
        self.suf_suf   = _suf(SufficiencyLevel.SUFFICIENT, sup=3)
        self.unc       = _unc()

    def _action(self, action: ActionType) -> CandidateAction:
        return CandidateAction(action=action, reason="test", policy_basis="TEST")

    def test_block_card_blocked_on_insufficient(self):
        result = self.guard.validate(self._action(ActionType.BLOCK_CARD),
                                     self.suf_insuf, self.unc, 0)
        self.assertNotEqual(result.action, ActionType.BLOCK_CARD)

    def test_block_card_allowed_on_sufficient(self):
        result = self.guard.validate(self._action(ActionType.BLOCK_CARD),
                                     self.suf_suf, self.unc, 3)
        self.assertEqual(result.action, ActionType.BLOCK_CARD)

    def test_file_report_blocked_with_zero_supporting(self):
        result = self.guard.validate(self._action(ActionType.FILE_REPORT),
                                     self.suf_suf, self.unc, 0)
        self.assertNotEqual(result.action, ActionType.FILE_REPORT)

    def test_file_report_allowed_with_supporting_evidence(self):
        result = self.guard.validate(self._action(ActionType.FILE_REPORT),
                                     self.suf_suf, self.unc, 2)
        self.assertEqual(result.action, ActionType.FILE_REPORT)

    def test_close_no_fraud_blocked_with_supporting_evidence(self):
        result = self.guard.validate(self._action(ActionType.CLOSE_NO_FRAUD),
                                     self.suf_suf, self.unc, 2)
        self.assertNotEqual(result.action, ActionType.CLOSE_NO_FRAUD)

    def test_monitor_passes_through_unchanged(self):
        result = self.guard.validate(self._action(ActionType.MONITOR),
                                     self.suf_insuf, self.unc, 0)
        self.assertEqual(result.action, ActionType.MONITOR)

    def test_verify_with_customer_passes_through(self):
        result = self.guard.validate(self._action(ActionType.VERIFY_WITH_CUSTOMER),
                                     self.suf_insuf, self.unc, 0)
        self.assertEqual(result.action, ActionType.VERIFY_WITH_CUSTOMER)


class TestApprovalRouter(unittest.TestCase):

    def setUp(self):
        self.router = ApprovalRouter()

    def test_block_card_requires_fraud_analyst(self):
        route = self.router.route(ActionType.BLOCK_CARD, 100.0, "low")
        self.assertEqual(route, ApprovalRoute.FRAUD_ANALYST)

    def test_block_card_high_exposure_requires_senior_analyst(self):
        route = self.router.route(ActionType.BLOCK_CARD, 1500.0, "low")
        self.assertEqual(route, ApprovalRoute.SENIOR_ANALYST)

    def test_monitor_requires_no_approval(self):
        route = self.router.route(ActionType.MONITOR, 0.0, "low")
        self.assertEqual(route, ApprovalRoute.NONE)

    def test_verify_requires_no_approval(self):
        route = self.router.route(ActionType.VERIFY_WITH_CUSTOMER, 0.0, "low")
        self.assertEqual(route, ApprovalRoute.NONE)

    def test_requires_approval_true_for_fraud_analyst(self):
        self.assertTrue(self.router.requires_approval(ApprovalRoute.FRAUD_ANALYST))

    def test_requires_approval_false_for_none(self):
        self.assertFalse(self.router.requires_approval(ApprovalRoute.NONE))


if __name__ == "__main__":
    unittest.main(verbosity=2)
