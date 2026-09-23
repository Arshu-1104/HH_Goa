"""
agent/policy/approvals.py — Approval routing logic.

Determines who (if anyone) must approve the recommended action
before it can be executed.
"""

from __future__ import annotations

from agent.state.models import ActionType, ApprovalRoute


# Actions that always require at least fraud_analyst approval
_REQUIRES_FRAUD_ANALYST: set[ActionType] = {
    ActionType.BLOCK_CARD,
    ActionType.BLOCK_ACCOUNT,
    ActionType.CLOSE_NO_FRAUD,
}

# Actions that require senior_analyst when exposure is high
_REQUIRES_SENIOR_HIGH_EXPOSURE: set[ActionType] = {
    ActionType.BLOCK_CARD,
    ActionType.FILE_REPORT,
    ActionType.ESCALATE,
}

# Threshold above which senior analyst is required
HIGH_EXPOSURE_THRESHOLD_USD = 1000.0


class ApprovalRouter:
    """Routes decisions to the appropriate approver."""

    def route(
        self,
        action: ActionType,
        total_exposure_usd: float,
        uncertainty_level: str,
    ) -> ApprovalRoute:
        """
        Determine the approval route for a given action.

        Parameters
        ----------
        action : ActionType
            The recommended action
        total_exposure_usd : float
            Total financial exposure
        uncertainty_level : str
            'low' / 'medium' / 'high'

        Returns
        -------
        ApprovalRoute
        """
        # Senior analyst for high-exposure disruptive actions
        if (
            action in _REQUIRES_SENIOR_HIGH_EXPOSURE
            and total_exposure_usd >= HIGH_EXPOSURE_THRESHOLD_USD
        ):
            return ApprovalRoute.SENIOR_ANALYST

        # Senior analyst for any action under high uncertainty
        if uncertainty_level == "high" and action in _REQUIRES_FRAUD_ANALYST:
            return ApprovalRoute.SENIOR_ANALYST

        # Standard fraud analyst approval
        if action in _REQUIRES_FRAUD_ANALYST:
            return ApprovalRoute.FRAUD_ANALYST

        # Low-risk actions are auto-executable
        return ApprovalRoute.NONE

    def requires_approval(self, route: ApprovalRoute) -> bool:
        return route != ApprovalRoute.NONE
