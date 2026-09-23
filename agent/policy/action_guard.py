"""
agent/policy/action_guard.py — Final safety gate before action recommendation.

Validates the recommended action one last time before it leaves the agent.
Prevents contradictory or unsafe recommendations.
"""

from __future__ import annotations

import logging

from agent.state.models import (
    ActionType,
    CandidateAction,
    SufficiencyLevel,
    SufficiencyResult,
    UncertaintyLevel,
    UncertaintyAssessment,
)

log = logging.getLogger(__name__)


class ActionGuard:
    """
    Final validation gate. Blocks unsafe recommendations and
    substitutes a safe fallback if needed.
    """

    def validate(
        self,
        action: CandidateAction,
        sufficiency: SufficiencyResult,
        uncertainty: UncertaintyAssessment,
        supporting_count: int,
    ) -> CandidateAction:
        """
        Validate a recommended action. Returns the action if safe,
        or a safer fallback if not.

        Parameters
        ----------
        action : CandidateAction
        sufficiency : SufficiencyResult
        uncertainty : UncertaintyAssessment
        supporting_count : int

        Returns
        -------
        CandidateAction — original or substituted safe action
        """
        # Block BLOCK_CARD if evidence is insufficient
        if (
            action.action == ActionType.BLOCK_CARD
            and sufficiency.level == SufficiencyLevel.INSUFFICIENT
        ):
            log.warning(
                "ActionGuard: BLOCK_CARD rejected — evidence is INSUFFICIENT. "
                "Substituting VERIFY_WITH_CUSTOMER."
            )
            return CandidateAction(
                action=ActionType.VERIFY_WITH_CUSTOMER,
                reason="ActionGuard: downgraded from BLOCK_CARD — evidence insufficient",
                policy_basis="ACTION_GUARD_SAFETY",
                approval_required=False,
                risk_level="low",
            )

        # Block FILE_REPORT if no supporting evidence
        if action.action == ActionType.FILE_REPORT and supporting_count == 0:
            log.warning(
                "ActionGuard: FILE_REPORT rejected — no supporting evidence."
            )
            return CandidateAction(
                action=ActionType.MONITOR,
                reason="ActionGuard: FILE_REPORT blocked — zero supporting evidence",
                policy_basis="ACTION_GUARD_SAFETY",
                approval_required=False,
                risk_level="low",
            )

        # Block CLOSE_NO_FRAUD if there's supporting evidence
        if action.action == ActionType.CLOSE_NO_FRAUD and supporting_count > 0:
            log.warning(
                f"ActionGuard: CLOSE_NO_FRAUD blocked — {supporting_count} supporting evidence items exist."
            )
            return CandidateAction(
                action=ActionType.VERIFY_WITH_CUSTOMER,
                reason="ActionGuard: CLOSE_NO_FRAUD blocked — supporting evidence present",
                policy_basis="ACTION_GUARD_SAFETY",
                approval_required=False,
                risk_level="low",
            )

        return action
