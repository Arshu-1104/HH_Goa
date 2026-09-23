"""
agent/policy/evaluator.py — Deterministic policy evaluation engine.

Evaluates which actions are permitted given current evidence state.
Returns a PolicyDecision with the recommended action, whether it's
allowed, and which policy rules were applied.
"""

from __future__ import annotations

import logging
from typing import Any

from agent.state.models import (
    ActionType,
    ApprovalRoute,
    CandidateAction,
    PolicyDecision,
    SufficiencyLevel,
    SufficiencyResult,
    UncertaintyAssessment,
    UncertaintyLevel,
)
from agent.policy.rules import POLICY_RULES

log = logging.getLogger(__name__)


class PolicyEvaluator:
    """
    Evaluates which actions are permitted under the deterministic policy.
    Returns the best allowed action as a PolicyDecision.
    """

    def evaluate(
        self,
        sufficiency: SufficiencyResult,
        uncertainty: UncertaintyAssessment,
        supporting_count: int,
        contradictory_count: int,
        total_exposure_usd: float,
        trigger_type: str,
        top_hypothesis_name: str = "",
    ) -> tuple[PolicyDecision, list[CandidateAction]]:
        """
        Evaluate policy and return the best permitted action + all candidates.

        Returns
        -------
        tuple[PolicyDecision, list[CandidateAction]]
        """
        candidates: list[CandidateAction] = []
        applied_rules: list[str] = []

        for rule in POLICY_RULES:
            if self._rule_matches(
                rule, sufficiency, uncertainty,
                supporting_count, contradictory_count,
                total_exposure_usd, trigger_type
            ):
                action = rule["action"]
                candidates.append(CandidateAction(
                    action=action,
                    reason=rule["name"],
                    policy_basis=rule["rule_id"],
                    approval_required=rule["approval_route"] != ApprovalRoute.NONE,
                    approval_route=rule["approval_route"],
                    risk_level=rule["risk_level"],
                ))
                applied_rules.append(rule["rule_id"])
                log.debug(f"Rule matched: {rule['rule_id']} → {action}")

        if not candidates:
            # Fallback: monitor
            candidates.append(CandidateAction(
                action=ActionType.MONITOR,
                reason="Fallback: no specific policy rule matched",
                policy_basis="FALLBACK",
                approval_required=False,
                approval_route=ApprovalRoute.NONE,
                risk_level="low",
            ))
            applied_rules.append("FALLBACK")

        # Select best candidate: prefer highest impact that is allowed
        best = self._select_best(candidates, sufficiency, uncertainty)

        decision = PolicyDecision(
            action=best.action,
            allowed=True,
            reason=best.reason,
            approval_required=best.approval_required,
            approval_route=best.approval_route,
            policy_rules_applied=applied_rules,
        )

        log.info(
            f"Policy decision: {decision.action} | "
            f"approval={decision.approval_route} | "
            f"rules={applied_rules}"
        )
        return decision, candidates

    def _rule_matches(
        self,
        rule: dict,
        sufficiency: SufficiencyResult,
        uncertainty: UncertaintyAssessment,
        supporting_count: int,
        contradictory_count: int,
        total_exposure_usd: float,
        trigger_type: str,
    ) -> bool:
        cond = rule.get("conditions", {})

        # Sufficiency check
        if "sufficiency" in cond:
            if sufficiency.level not in cond["sufficiency"]:
                return False

        # Uncertainty check
        if "uncertainty" in cond:
            if uncertainty.level not in cond["uncertainty"]:
                return False

        # Max uncertainty check
        if "max_uncertainty" in cond:
            level_order = {
                UncertaintyLevel.LOW: 0,
                UncertaintyLevel.MEDIUM: 1,
                UncertaintyLevel.HIGH: 2,
            }
            if level_order[uncertainty.level] > level_order[cond["max_uncertainty"]]:
                return False

        # Min supporting evidence
        if "min_supporting" in cond:
            if supporting_count < cond["min_supporting"]:
                return False

        # Max supporting (for close_no_fraud)
        if "max_supporting" in cond:
            if supporting_count > cond["max_supporting"]:
                return False

        # Min contradictory (for close_no_fraud)
        if "min_contradictory" in cond:
            if contradictory_count < cond["min_contradictory"]:
                return False

        # Min exposure
        if "min_exposure" in cond:
            if total_exposure_usd < cond["min_exposure"]:
                return False

        # Trigger type whitelist
        if "trigger_types" in cond:
            if trigger_type not in cond["trigger_types"]:
                return False

        return True

    def _select_best(
        self,
        candidates: list[CandidateAction],
        sufficiency: SufficiencyResult,
        uncertainty: UncertaintyAssessment,
    ) -> CandidateAction:
        """
        Select the best action from candidates.
        Priority: BLOCK_CARD > FILE_REPORT > ESCALATE > VERIFY > MONITOR > CLOSE > REQUEST
        If uncertainty is HIGH, prefer ESCALATE or VERIFY over BLOCK_CARD.
        """
        priority = {
            ActionType.BLOCK_CARD: 7,
            ActionType.FILE_REPORT: 6,
            ActionType.ESCALATE: 5,
            ActionType.VERIFY_WITH_CUSTOMER: 4,
            ActionType.CLOSE_NO_FRAUD: 3,
            ActionType.MONITOR: 2,
            ActionType.REQUEST_MORE_EVIDENCE: 1,
        }

        # If uncertainty is HIGH, reduce BLOCK_CARD priority
        adjusted: dict[ActionType, int] = {}
        for c in candidates:
            p = priority.get(c.action, 0)
            if uncertainty.level == UncertaintyLevel.HIGH and c.action == ActionType.BLOCK_CARD:
                p = 3  # same level as CLOSE_NO_FRAUD — don't block under high uncertainty
            adjusted[c.action] = p

        return max(candidates, key=lambda c: adjusted.get(c.action, 0))
