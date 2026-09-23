"""
agent/decisions/next_best_action.py — Next Best Action selection engine.

Combines policy evaluation, LLM suggestion (if available), action guard,
and approval routing to produce the final recommended action.

If an LLM API key is present, the LLM's suggestion is considered but
the PolicyEvaluator + ActionGuard always have final veto.
If no API key, the policy engine output is used directly.
"""

from __future__ import annotations

import json
import logging
import os
from typing import Any

from agent.policy.approvals import ApprovalRouter
from agent.policy.action_guard import ActionGuard
from agent.state.models import (
    ActionType,
    ApprovalRoute,
    CandidateAction,
    PolicyDecision,
    SufficiencyResult,
    UncertaintyAssessment,
)

log = logging.getLogger(__name__)


class NextBestActionEngine:
    """
    Selects the best action from policy candidates, optionally consulting the LLM.
    Always applies ActionGuard as the final safety gate.
    """

    def __init__(self) -> None:
        self._router = ApprovalRouter()
        self._guard = ActionGuard()
        self._llm = None
        self._try_init_llm()

    def _try_init_llm(self) -> None:
        """Try to initialise the LLM. Silently skip if no API key available."""
        api_key = os.environ.get("ANTHROPIC_API_KEY") or os.environ.get("OPENAI_API_KEY")
        if not api_key:
            log.info("No LLM API key found — using policy engine only for NBA")
            return
        try:
            from langchain_anthropic import ChatAnthropic
            self._llm = ChatAnthropic(
                model=os.environ.get("LLM_MODEL", "claude-3-haiku-20240307"),
                temperature=0.0,
                timeout=int(os.environ.get("LLM_TIMEOUT", "30")),
            )
            log.info("LLM initialised for NBA")
        except Exception as exc:
            log.warning(f"LLM init failed: {exc} — falling back to policy only")

    def select(
        self,
        policy_decision: PolicyDecision,
        candidates: list[CandidateAction],
        context: str,
        sufficiency: SufficiencyResult,
        uncertainty: UncertaintyAssessment,
        supporting_count: int,
        total_exposure_usd: float,
    ) -> CandidateAction:
        """
        Select the final recommended action.

        Parameters
        ----------
        policy_decision : PolicyDecision
            Output from PolicyEvaluator (deterministic best action)
        candidates : list[CandidateAction]
            All candidate actions from policy
        context : str
            Decision context string from ContextBuilder
        sufficiency : SufficiencyResult
        uncertainty : UncertaintyAssessment
        supporting_count : int
        total_exposure_usd : float

        Returns
        -------
        CandidateAction — the final safe recommended action
        """
        # Start with policy decision
        best_action = next(
            (c for c in candidates if c.action == policy_decision.action),
            candidates[0] if candidates else self._fallback_action(),
        )

        # Optionally refine with LLM
        if self._llm is not None:
            best_action = self._llm_refine(best_action, candidates, context, sufficiency)

        # Apply approval routing
        route = self._router.route(
            action=best_action.action,
            total_exposure_usd=total_exposure_usd,
            uncertainty_level=uncertainty.level.value,
        )
        best_action.approval_route = route
        best_action.approval_required = self._router.requires_approval(route)

        # Final safety gate
        best_action = self._guard.validate(
            action=best_action,
            sufficiency=sufficiency,
            uncertainty=uncertainty,
            supporting_count=supporting_count,
        )

        log.info(
            f"NBA: {best_action.action} | "
            f"approval={best_action.approval_route} | "
            f"required={best_action.approval_required}"
        )
        return best_action

    def _llm_refine(
        self,
        policy_best: CandidateAction,
        candidates: list[CandidateAction],
        context: str,
        sufficiency: SufficiencyResult,
    ) -> CandidateAction:
        """Ask the LLM if it agrees with the policy recommendation."""
        from agent.graphrag.prompts import SYSTEM_FRAUD_INVESTIGATOR, DECISION_PROMPT_TEMPLATE
        from langchain_core.messages import HumanMessage, SystemMessage

        prompt = DECISION_PROMPT_TEMPLATE.format(context=context)
        try:
            response = self._llm.invoke([
                SystemMessage(content=SYSTEM_FRAUD_INVESTIGATOR),
                HumanMessage(content=prompt),
            ])
            raw = response.content.strip()
            # Extract JSON
            if "```" in raw:
                raw = raw.split("```")[1].lstrip("json").strip()
            data = json.loads(raw)
            llm_action_str = data.get("recommended_action", "").strip()

            # Only accept the LLM suggestion if it maps to a known ActionType
            # AND it's among the policy candidates
            try:
                llm_action = ActionType(llm_action_str)
                candidate_actions = {c.action for c in candidates}
                if llm_action in candidate_actions:
                    matched = next(c for c in candidates if c.action == llm_action)
                    matched.reason = data.get("reason", matched.reason)
                    log.info(f"LLM refined action: {llm_action}")
                    return matched
                else:
                    log.warning(
                        f"LLM suggested {llm_action_str!r} but it's not in policy candidates. "
                        "Keeping policy recommendation."
                    )
            except ValueError:
                log.warning(f"LLM returned unknown action {llm_action_str!r}")

        except Exception as exc:
            log.warning(f"LLM NBA refinement failed: {exc} — keeping policy recommendation")

        return policy_best

    def _fallback_action(self) -> CandidateAction:
        return CandidateAction(
            action=ActionType.MONITOR,
            reason="Fallback: no candidates available",
            policy_basis="FALLBACK",
            approval_required=False,
            approval_route=ApprovalRoute.NONE,
            risk_level="low",
        )
