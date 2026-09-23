"""
agent/uncertainty/engine.py — Uncertainty derivation engine.

Derives qualitative uncertainty (LOW / MEDIUM / HIGH) from:
  - Evidence completeness (categories covered)
  - Evidence conflicts (supporting vs contradictory)
  - Missing data (no device info, no prior cases, etc.)
  - Hypothesis confidence spread

All outputs are grounded in actual evidence — nothing is fabricated.
"""

from __future__ import annotations

import logging

from agent.state.models import (
    Evidence,
    Hypothesis,
    UncertaintyAssessment,
    UncertaintyLevel,
)

log = logging.getLogger(__name__)


class UncertaintyEngine:
    """Derives uncertainty level from the current evidence state."""

    def assess(
        self,
        evidence: list[Evidence],
        supporting: list[Evidence],
        contradictory: list[Evidence],
        hypotheses: list[Hypothesis],
        tools_called: set[str],
    ) -> UncertaintyAssessment:
        """
        Assess uncertainty for the current investigation state.

        Parameters
        ----------
        evidence : list[Evidence]
            All gathered evidence
        supporting : list[Evidence]
            Evidence supporting fraud
        contradictory : list[Evidence]
            Evidence against fraud
        hypotheses : list[Hypothesis]
            Current hypothesis list
        tools_called : set[str]
            MCP tools already called

        Returns
        -------
        UncertaintyAssessment
        """
        known: list[str] = []
        unknown: list[str] = []
        conflicts: list[str] = []
        missing: list[str] = []
        reduction_steps: list[str] = []

        # ── What we know ──────────────────────────────────────────────────
        for ev in supporting:
            known.append(ev.claim[:120])

        # ── Conflicts ─────────────────────────────────────────────────────
        if supporting and contradictory:
            conflicts.append(
                f"{len(supporting)} supporting vs {len(contradictory)} contradictory evidence items"
            )
            for ev in contradictory:
                conflicts.append(f"Contradicts fraud: {ev.claim[:100]}")

        # ── Missing data signals ───────────────────────────────────────────
        has_device_info = any(
            "device" in ev.claim.lower() and "no device" not in ev.claim.lower()
            for ev in evidence
        )
        has_no_device = any("no device identity record" in ev.claim.lower() for ev in evidence)
        if has_no_device or not has_device_info:
            missing.append("Device/identity information is absent or incomplete")
            reduction_steps.append("Call get_transaction_context for device details")

        # Check if prior cases have been retrieved
        has_prior = "find_prior_cases" in tools_called
        if not has_prior:
            missing.append("Prior closed case history not retrieved")
            reduction_steps.append("Call find_prior_cases to retrieve historical context")

        # Check if exposure has been calculated
        has_exposure = "calculate_exposure" in tools_called
        if not has_exposure:
            missing.append("Financial exposure not calculated")
            reduction_steps.append("Call calculate_exposure for financial context")

        # Check hypothesis confidence spread
        if hypotheses:
            confidences = [h.confidence for h in hypotheses if h.confidence > 0]
            if confidences:
                max_conf = max(confidences)
                if max_conf < 0.4:
                    unknown.append("No hypothesis has sufficient confidence (all < 0.4)")
                elif max_conf < 0.6:
                    unknown.append(f"Top hypothesis confidence is low ({max_conf:.2f})")
                else:
                    known.append(f"Top hypothesis has confidence {max_conf:.2f}")

        # ── Derive level ──────────────────────────────────────────────────
        level = self._derive_level(
            has_missing=bool(missing),
            has_conflicts=bool(conflicts),
            supporting_count=len(supporting),
            contradictory_count=len(contradictory),
            evidence_count=len(evidence),
            hypotheses=hypotheses,
        )

        reason = self._build_reason(level, known, unknown, conflicts, missing)

        return UncertaintyAssessment(
            level=level,
            known=known[:10],       # cap to avoid very long lists
            unknown=unknown[:5],
            conflicts=conflicts[:5],
            missing=missing[:5],
            reduction_steps=reduction_steps[:5],
            reason=reason,
        )

    def _derive_level(
        self,
        has_missing: bool,
        has_conflicts: bool,
        supporting_count: int,
        contradictory_count: int,
        evidence_count: int,
        hypotheses: list[Hypothesis],
    ) -> UncertaintyLevel:
        """Derive the qualitative uncertainty level."""
        # HIGH uncertainty: many conflicts, very little evidence, or no supporting
        if supporting_count == 0 and evidence_count > 0:
            return UncertaintyLevel.HIGH
        if has_conflicts and contradictory_count >= supporting_count:
            return UncertaintyLevel.HIGH
        if evidence_count < 2:
            return UncertaintyLevel.HIGH

        # MEDIUM: some missing data or minor conflicts
        if has_missing or (has_conflicts and contradictory_count < supporting_count):
            return UncertaintyLevel.MEDIUM

        # Check hypothesis confidence
        if hypotheses:
            top_conf = max((h.confidence for h in hypotheses), default=0.0)
            if top_conf < 0.5:
                return UncertaintyLevel.MEDIUM

        # LOW: complete evidence, consistent signals
        return UncertaintyLevel.LOW

    def _build_reason(
        self,
        level: UncertaintyLevel,
        known: list[str],
        unknown: list[str],
        conflicts: list[str],
        missing: list[str],
    ) -> str:
        parts: list[str] = [f"Uncertainty level: {level.value.upper()}."]
        if known:
            parts.append(f"Known facts: {len(known)} items.")
        if conflicts:
            parts.append(f"Conflicts: {conflicts[0]}")
        if missing:
            parts.append(f"Missing: {'; '.join(missing[:2])}")
        if unknown:
            parts.append(f"Unknown: {unknown[0]}")
        return " ".join(parts)
