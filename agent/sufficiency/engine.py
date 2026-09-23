"""
agent/sufficiency/engine.py — Evidence Sufficiency Engine.

Determines whether the gathered evidence is sufficient to make a decision.
Output is INSUFFICIENT, PARTIAL, or SUFFICIENT.

INSUFFICIENT → only non-disruptive safe actions are available
PARTIAL      → can recommend non-disruptive actions (MONITOR, VERIFY_WITH_CUSTOMER)
SUFFICIENT   → can recommend any permitted action (including BLOCK_CARD, FILE_REPORT)

IMPORTANT — retry limit behaviour:
  The reassessment_count parameter is used ONLY to prevent an infinite loop.
  When the retry limit is reached, the engine still returns the TRUTHFUL
  sufficiency level — it does NOT upgrade INSUFFICIENT to SUFFICIENT.
  The workflow loop handles the retry exhaustion by breaking out of the loop
  and passing the truthful result to the policy engine. The policy engine
  then selects an appropriate safe action (ESCALATE or REQUEST_MORE_EVIDENCE)
  for the INSUFFICIENT case, rather than a disruptive action.
"""

from __future__ import annotations

import logging

from agent.evidence.models import EvidenceCategory, EVIDENCE_SOURCE_TO_CATEGORY
from agent.state.models import Evidence, SufficiencyLevel, SufficiencyResult
from agent.sufficiency.config import (
    MAX_REASSESSMENTS,
    MIN_SUPPORTING_FOR_ACTION,
    REQUIRED_FOR_PARTIAL,
    REQUIRED_FOR_SUFFICIENT,
)

log = logging.getLogger(__name__)


class SufficiencyEngine:
    """
    Evaluates whether gathered evidence is sufficient for a decision.

    The retry limit (reassessment_count >= MAX_REASSESSMENTS) prevents an
    infinite loop in the workflow but does NOT change the truthful result.
    When retries are exhausted, the engine logs a warning and returns the
    actual evidence state so the policy engine can select a safe action.
    """

    def evaluate(
        self,
        evidence: list[Evidence],
        supporting: list[Evidence],
        contradictory: list[Evidence],
        tools_called: set[str],
        reassessment_count: int = 0,
    ) -> SufficiencyResult:
        """
        Evaluate evidence sufficiency.

        Parameters
        ----------
        evidence : list[Evidence]
            All gathered evidence items
        supporting : list[Evidence]
            Evidence that supports fraud
        contradictory : list[Evidence]
            Evidence against fraud
        tools_called : set[str]
            Names of MCP tools already called
        reassessment_count : int
            How many times we've already reassessed.
            When >= MAX_REASSESSMENTS the loop will stop requesting more
            evidence, but this does NOT change the truthful sufficiency level.

        Returns
        -------
        SufficiencyResult — truthful assessment of the actual evidence state
        """
        retry_limit_reached = reassessment_count >= MAX_REASSESSMENTS

        if retry_limit_reached:
            log.warning(
                f"Reassessment limit reached ({reassessment_count}/{MAX_REASSESSMENTS}). "
                "Returning truthful evidence state — NOT upgrading to SUFFICIENT. "
                "Policy engine will select a safe action for the actual evidence level."
            )

        # Build a map of which evidence categories are covered
        covered: set[str] = set()
        for ev in evidence:
            source_str = (
                ev.source_type.value
                if hasattr(ev.source_type, "value")
                else str(ev.source_type)
            )
            cats = EVIDENCE_SOURCE_TO_CATEGORY.get(source_str, [])
            for cat in cats:
                covered.add(str(cat) if not isinstance(cat, str) else cat)

        # Normalise required lists to strings for comparison
        req_sufficient = [
            str(c) if not isinstance(c, str) else c
            for c in REQUIRED_FOR_SUFFICIENT
        ]
        req_partial = [
            str(c) if not isinstance(c, str) else c
            for c in REQUIRED_FOR_PARTIAL
        ]

        satisfied_sufficient = [c for c in req_sufficient if c in covered]
        satisfied_partial    = [c for c in req_partial    if c in covered]
        unsatisfied_sufficient = [c for c in req_sufficient if c not in covered]

        # ── SUFFICIENT ────────────────────────────────────────────────────
        if (
            len(satisfied_sufficient) == len(req_sufficient)
            and len(supporting) >= MIN_SUPPORTING_FOR_ACTION
        ):
            return SufficiencyResult(
                sufficient=True,
                level=SufficiencyLevel.SUFFICIENT,
                supporting_count=len(supporting),
                contradictory_count=len(contradictory),
                satisfied_categories=satisfied_sufficient,
                unsatisfied_categories=[],
                reason=(
                    f"All required evidence categories covered "
                    f"({', '.join(satisfied_sufficient)}). "
                    f"{len(supporting)} supporting items."
                ),
            )

        # ── PARTIAL ───────────────────────────────────────────────────────
        if (
            len(satisfied_partial) == len(req_partial)
            and len(supporting) >= MIN_SUPPORTING_FOR_ACTION
        ):
            missing = [
                f"Missing evidence category: {c}"
                for c in unsatisfied_sufficient
            ]
            return SufficiencyResult(
                sufficient=True,   # sufficient for non-disruptive actions only
                level=SufficiencyLevel.PARTIAL,
                supporting_count=len(supporting),
                contradictory_count=len(contradictory),
                satisfied_categories=satisfied_partial,
                unsatisfied_categories=unsatisfied_sufficient,
                missing_evidence=missing,
                reason=(
                    f"Partial evidence: {', '.join(satisfied_partial)} covered. "
                    f"Missing: {', '.join(unsatisfied_sufficient)}. "
                    "Only non-disruptive actions available."
                ),
            )

        # ── INSUFFICIENT ──────────────────────────────────────────────────
        all_missing = [
            f"Missing evidence category: {c}"
            for c in req_partial
            if c not in covered
        ]

        # Identify specific uncalled tools that would help fill the gaps
        helpful_uncalled: list[str] = []
        _txn_covered = any(
            "transaction" in c.lower() for c in covered
        )
        _cust_covered = any(
            "customer" in c.lower() for c in covered
        )
        _hist_covered = any(
            "historical" in c.lower() for c in covered
        )
        _exp_covered = any(
            "exposure" in c.lower() for c in covered
        )

        if not _txn_covered and "get_transaction_context" not in tools_called:
            helpful_uncalled.append("get_transaction_context")
        if not _cust_covered and "get_customer_history" not in tools_called:
            helpful_uncalled.append("get_customer_history")
        if not _hist_covered and "find_prior_cases" not in tools_called:
            helpful_uncalled.append("find_prior_cases")
        if not _exp_covered and "calculate_exposure" not in tools_called:
            helpful_uncalled.append("calculate_exposure")

        if helpful_uncalled:
            all_missing.append(
                f"Uncalled tools that would help: {', '.join(helpful_uncalled)}"
            )

        retry_note = (
            f" Retry limit reached ({reassessment_count}/{MAX_REASSESSMENTS}) — "
            "no further evidence requests will be made. "
            "Policy engine will select a safe escalation action."
            if retry_limit_reached
            else ""
        )

        return SufficiencyResult(
            sufficient=False,
            level=SufficiencyLevel.INSUFFICIENT,
            supporting_count=len(supporting),
            contradictory_count=len(contradictory),
            satisfied_categories=list(covered),
            unsatisfied_categories=unsatisfied_sufficient,
            missing_evidence=all_missing,
            reason=(
                f"Insufficient evidence. "
                f"Covered: {', '.join(covered) or 'none'}. "
                f"Required: {', '.join(req_partial)}."
                + retry_note
            ),
        )
