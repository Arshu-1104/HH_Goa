"""
agent/hypotheses/manager.py — Hypothesis creation and update.

Creates a hypothesis for each relevant fraud pattern at investigation start,
then updates hypothesis status and confidence as evidence comes in.
Only the 7 official FraudPattern values are used — no invented patterns.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone

from agent.state.models import (
    Evidence,
    FraudPattern,
    Hypothesis,
    HypothesisStatus,
)

log = logging.getLogger(__name__)

# Human-readable descriptions for each fraud pattern
_PATTERN_DESCRIPTIONS: dict[str, str] = {
    FraudPattern.CARD_NOT_PRESENT_FRAUD: (
        "Card used online or by phone without the physical card present"
    ),
    FraudPattern.CARD_NOT_PRESENT_NEW_DEVICE: (
        "Card-not-present transaction from an unrecognized new device"
    ),
    FraudPattern.CARD_TESTING: (
        "Multiple small transactions used to test if a stolen card is active"
    ),
    FraudPattern.ACCOUNT_TAKEOVER: (
        "Fraudster gained control of a legitimate customer account"
    ),
    FraudPattern.OUT_OF_REGION_USE: (
        "Card used far outside the customer's normal geographic region"
    ),
    FraudPattern.UNDOCUMENTED: (
        "Fraud confirmed but specific pattern not documented"
    ),
}

# Trigger-type to likely hypothesis names
_TRIGGER_HYPOTHESES: dict[str, list[str]] = {
    "risk_score": [
        FraudPattern.CARD_NOT_PRESENT_FRAUD,
        FraudPattern.CARD_NOT_PRESENT_NEW_DEVICE,
        FraudPattern.CARD_TESTING,
        FraudPattern.OUT_OF_REGION_USE,
    ],
    "customer_report": [
        FraudPattern.CARD_NOT_PRESENT_FRAUD,
        FraudPattern.ACCOUNT_TAKEOVER,
        FraudPattern.CARD_NOT_PRESENT_NEW_DEVICE,
    ],
    "analyst_request": [
        FraudPattern.CARD_NOT_PRESENT_FRAUD,
        FraudPattern.ACCOUNT_TAKEOVER,
        FraudPattern.CARD_TESTING,
        FraudPattern.CARD_NOT_PRESENT_NEW_DEVICE,
    ],
}


class HypothesisManager:
    """
    Creates and updates fraud hypotheses during an investigation.
    """

    def __init__(self) -> None:
        self._counter = 0

    def _next_id(self) -> str:
        self._counter += 1
        return f"HYP-{self._counter:03d}"

    def _now(self) -> str:
        return datetime.now(timezone.utc).isoformat()

    def create_hypotheses(self, trigger_type: str) -> list[Hypothesis]:
        """
        Create initial hypothesis set based on trigger type.

        Parameters
        ----------
        trigger_type : str
            The case trigger type (risk_score / customer_report / analyst_request)

        Returns
        -------
        list[Hypothesis]
            One hypothesis per relevant fraud pattern
        """
        patterns = _TRIGGER_HYPOTHESES.get(
            trigger_type,
            list(_PATTERN_DESCRIPTIONS.keys()),
        )
        hypotheses: list[Hypothesis] = []
        now = self._now()

        for pattern in patterns:
            hyp = Hypothesis(
                hypothesis_id=self._next_id(),
                name=str(pattern),
                description=_PATTERN_DESCRIPTIONS.get(pattern, str(pattern)),
                status=HypothesisStatus.ACTIVE,
                confidence=0.3,  # prior before any evidence
                last_updated=now,
            )
            hypotheses.append(hyp)
            log.debug(f"Created hypothesis {hyp.hypothesis_id}: {hyp.name}")

        return hypotheses

    def update_hypotheses(
        self,
        hypotheses: list[Hypothesis],
        supporting: list[Evidence],
        contradictory: list[Evidence],
    ) -> list[Hypothesis]:
        """
        Update hypothesis status and confidence based on classified evidence.

        Parameters
        ----------
        hypotheses : list[Hypothesis]
            Current hypotheses
        supporting : list[Evidence]
            Evidence that supports fraud
        contradictory : list[Evidence]
            Evidence that contradicts fraud

        Returns
        -------
        list[Hypothesis]
            Updated hypotheses
        """
        now = self._now()
        hyp_by_id: dict[str, Hypothesis] = {h.hypothesis_id: h for h in hypotheses}

        # Count supporting and contradictory evidence per hypothesis
        support_counts: dict[str, int] = {}
        contradict_counts: dict[str, int] = {}

        for ev in supporting:
            for hid in ev.supports:
                support_counts[hid] = support_counts.get(hid, 0) + 1
                if hid not in hyp_by_id[hid].supporting_evidence_ids if hid in hyp_by_id else True:
                    if hid in hyp_by_id:
                        hyp_by_id[hid].supporting_evidence_ids.append(ev.evidence_id)

        for ev in contradictory:
            for hid in ev.contradicts:
                contradict_counts[hid] = contradict_counts.get(hid, 0) + 1
                if hid in hyp_by_id:
                    hyp_by_id[hid].contradictory_evidence_ids.append(ev.evidence_id)

        # Update status and confidence for each hypothesis
        for hyp in hypotheses:
            hid = hyp.hypothesis_id
            s_count = support_counts.get(hid, 0)
            c_count = contradict_counts.get(hid, 0)
            total = s_count + c_count

            if total == 0:
                continue  # no new evidence — keep current state

            # Bayesian-style update: confidence increases with support, decreases with contradiction
            prior = hyp.confidence
            if total > 0:
                likelihood_ratio = (s_count + 0.5) / (c_count + 0.5)
                # Clamp confidence between 0.05 and 0.95
                new_conf = min(0.95, max(0.05, prior * likelihood_ratio / (prior * likelihood_ratio + (1 - prior))))
                hyp.confidence = round(new_conf, 3)

            # Update status
            if s_count > 0 and c_count == 0:
                hyp.status = HypothesisStatus.STRENGTHENED
                hyp.reasoning = f"{s_count} supporting, 0 contradictory evidence items"
            elif s_count > 0 and c_count > 0:
                if s_count >= c_count:
                    hyp.status = HypothesisStatus.STRENGTHENED
                    hyp.reasoning = f"{s_count} supporting vs {c_count} contradictory"
                else:
                    hyp.status = HypothesisStatus.WEAKENED
                    hyp.reasoning = f"{s_count} supporting vs {c_count} contradictory"
            elif c_count > 0 and s_count == 0:
                hyp.status = HypothesisStatus.WEAKENED
                hyp.reasoning = f"0 supporting, {c_count} contradictory evidence items"
                if hyp.confidence < 0.1:
                    hyp.status = HypothesisStatus.REJECTED

            hyp.last_updated = now
            log.debug(
                f"Hypothesis {hid} ({hyp.name}): "
                f"confidence={hyp.confidence:.3f} status={hyp.status}"
            )

        return hypotheses

    def get_top_hypothesis(self, hypotheses: list[Hypothesis]) -> Hypothesis | None:
        """Return the hypothesis with highest confidence that is not rejected."""
        active = [
            h for h in hypotheses
            if h.status != HypothesisStatus.REJECTED
        ]
        if not active:
            return None
        return max(active, key=lambda h: h.confidence)
