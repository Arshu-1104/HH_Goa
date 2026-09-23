"""
agent/graphrag/context_builder.py — Assembles a grounded context pack for LLM nodes.

ANTI-HALLUCINATION RULE: The context pack contains ONLY facts that appear
in actual Evidence objects extracted from real MCP tool results.
The LLM is never given open-ended instructions that could lead to invention.
Every factual claim in the prompt is sourced from an evidence_id.
"""

from __future__ import annotations

from typing import Any

from agent.state.models import (
    Evidence,
    FinalSummary,
    Hypothesis,
    SufficiencyResult,
    UncertaintyAssessment,
)


class ContextBuilder:
    """Builds grounded LLM context packs from investigation state."""

    def build_analysis_context(
        self,
        case_id: str,
        customer_id: str,
        transaction_id: str,
        trigger_text: str,
        evidence: list[Evidence],
        hypotheses: list[Hypothesis],
        uncertainty: UncertaintyAssessment | None,
    ) -> str:
        """
        Build context for the evidence analysis node.
        Returns a structured string the LLM uses to reason about the case.
        All factual claims include their evidence_id for traceability.
        """
        lines: list[str] = [
            f"FRAUD INVESTIGATION: {case_id}",
            f"Customer: {customer_id}  |  Transaction: {transaction_id}",
            f"Trigger: {trigger_text}",
            "",
            "=== EVIDENCE (grounded facts only — do not invent) ===",
        ]

        for ev in evidence:
            lines.append(
                f"[{ev.evidence_id}] {ev.claim}"
                + (f" (value: {ev.value})" if ev.value is not None else "")
            )

        lines += ["", "=== ACTIVE HYPOTHESES ==="]
        for h in hypotheses:
            lines.append(
                f"[{h.hypothesis_id}] {h.name}: "
                f"confidence={h.confidence:.2f} status={h.status}"
            )
            if h.supporting_evidence_ids:
                lines.append(f"  Supporting: {', '.join(h.supporting_evidence_ids)}")
            if h.contradictory_evidence_ids:
                lines.append(f"  Contradicting: {', '.join(h.contradictory_evidence_ids)}")

        if uncertainty:
            lines += [
                "",
                f"=== UNCERTAINTY: {uncertainty.level.value.upper()} ===",
                uncertainty.reason,
            ]

        return "\n".join(lines)

    def build_decision_context(
        self,
        case_id: str,
        customer_id: str,
        evidence: list[Evidence],
        supporting: list[Evidence],
        contradictory: list[Evidence],
        hypotheses: list[Hypothesis],
        sufficiency: SufficiencyResult,
        uncertainty: UncertaintyAssessment,
        prior_actions: list[str],
    ) -> str:
        """
        Build context for the next-best-action decision node.
        Includes sufficiency, uncertainty, and policy context.
        """
        top_hyp = max(hypotheses, key=lambda h: h.confidence) if hypotheses else None

        lines: list[str] = [
            f"DECISION CONTEXT: {case_id}",
            "",
            f"Evidence: {len(evidence)} total | {len(supporting)} supporting fraud | "
            f"{len(contradictory)} contradictory",
            f"Sufficiency: {sufficiency.level.value} — {sufficiency.reason}",
            f"Uncertainty: {uncertainty.level.value} — {uncertainty.reason}",
            "",
        ]

        if top_hyp:
            lines.append(
                f"Top hypothesis: {top_hyp.name} "
                f"(confidence={top_hyp.confidence:.2f}, status={top_hyp.status})"
            )

        lines += ["", "KEY SUPPORTING EVIDENCE:"]
        for ev in supporting[:5]:
            lines.append(f"  [{ev.evidence_id}] {ev.claim[:120]}")

        if contradictory:
            lines += ["", "KEY CONTRADICTORY EVIDENCE:"]
            for ev in contradictory[:3]:
                lines.append(f"  [{ev.evidence_id}] {ev.claim[:120]}")

        if prior_actions:
            lines += ["", f"Historical precedent actions: {', '.join(prior_actions[:3])}"]

        lines += [
            "",
            "AVAILABLE ACTIONS (from policy):",
            "  BLOCK_CARD — Requires: sufficient evidence + high exposure/fraud risk",
            "  VERIFY_WITH_CUSTOMER — Requires: some evidence + customer report trigger",
            "  FILE_REPORT — Requires: confirmed fraud pattern + sufficient exposure",
            "  CLOSE_NO_FRAUD — Requires: strong contradictory evidence",
            "  ESCALATE — Use when: uncertainty HIGH + exposure > $500",
            "  MONITOR — Use when: partial evidence + low risk score",
            "",
            "INSTRUCTION: Based ONLY on the evidence above (cite evidence_ids), "
            "select ONE action and explain your reasoning. "
            "Do NOT invent facts not listed above.",
        ]

        return "\n".join(lines)

    def build_summary_context(
        self,
        case_id: str,
        customer_id: str,
        transaction_id: str,
        trigger_text: str,
        evidence: list[Evidence],
        supporting: list[Evidence],
        contradictory: list[Evidence],
        hypotheses: list[Hypothesis],
        recommended_action: str,
        policy_basis: str,
        uncertainty: UncertaintyAssessment,
        sufficiency: SufficiencyResult,
    ) -> str:
        """Build context for the final summary generation node."""
        lines: list[str] = [
            f"FINAL SUMMARY CONTEXT: {case_id}",
            f"Customer: {customer_id} | Transaction: {transaction_id}",
            f"Trigger: {trigger_text}",
            f"Recommended Action: {recommended_action}",
            f"Policy basis: {policy_basis}",
            f"Uncertainty: {uncertainty.level.value}",
            f"Sufficiency: {sufficiency.level.value}",
            "",
            "ALL EVIDENCE (cite by evidence_id in your summary):",
        ]
        for ev in evidence:
            lines.append(f"  [{ev.evidence_id}] {ev.claim}")

        lines += ["", "HYPOTHESES:"]
        for h in hypotheses:
            lines.append(f"  {h.name}: {h.status} (conf={h.confidence:.2f})")

        lines += [
            "",
            "INSTRUCTION: Write a structured investigation summary. "
            "Cite evidence_ids for every factual claim. "
            "Do NOT add facts not present above.",
        ]
        return "\n".join(lines)
