"""
agent/evidence/classifier.py — Classify evidence as supporting or contradictory.

Determines whether each Evidence item supports fraud or contradicts it,
and links it to the relevant hypothesis IDs.

Classification is deterministic — based on the evidence source type,
claim content, and numeric values. No LLM required for this step.
"""

from __future__ import annotations

import logging
from typing import Any

from agent.state.models import Evidence, EvidenceSourceType, Hypothesis

log = logging.getLogger(__name__)

# ── Signal thresholds (deterministic rules) ────────────────────────────────────

# Risk score above this → supports fraud hypothesis
RISK_SCORE_THRESHOLD = 0.5

# More than this many prior fraud cases → strongly supports fraud
PRIOR_FRAUD_THRESHOLD = 0

# More than this many shared devices → supports fraud ring
SHARED_DEVICE_THRESHOLD = 0

# More than this many connected entities → supports fraud ring
CONNECTED_ENTITY_THRESHOLD = 5

# Minimum micro-transaction count for card testing signal
CARD_TESTING_MICRO_TXN_THRESHOLD = 3


def classify_evidence(
    evidence_items: list[Evidence],
    hypotheses: list[Hypothesis],
) -> tuple[list[Evidence], list[Evidence]]:
    """
    Classify evidence as supporting or contradicting fraud hypotheses.

    Updates the `supports` and `contradicts` fields on each Evidence item
    in place, then returns two lists.

    Parameters
    ----------
    evidence_items : list[Evidence]
        All evidence items gathered so far
    hypotheses : list[Hypothesis]
        Active fraud hypotheses (names are FraudPattern values)

    Returns
    -------
    tuple[list[Evidence], list[Evidence]]
        (supporting_evidence, contradictory_evidence)
    """
    hyp_ids_by_name: dict[str, str] = {h.name: h.hypothesis_id for h in hypotheses}
    supporting: list[Evidence] = []
    contradictory: list[Evidence] = []

    for ev in evidence_items:
        is_supporting, is_contradictory = _classify_single(ev, hyp_ids_by_name)
        if is_supporting:
            supporting.append(ev)
        elif is_contradictory:
            contradictory.append(ev)
        # Evidence with neither classification is neutral — not added to either list
        # but still kept in the full evidence list

    log.debug(
        f"Classified {len(evidence_items)} items: "
        f"{len(supporting)} supporting, {len(contradictory)} contradictory"
    )
    return supporting, contradictory


def _classify_single(
    ev: Evidence,
    hyp_ids_by_name: dict[str, str],
) -> tuple[bool, bool]:
    """
    Classify a single evidence item.

    Returns (is_supporting, is_contradictory).
    Both can be False (neutral evidence).
    Both should not both be True.
    """
    claim_lower = ev.claim.lower()
    source = ev.source_type
    value = ev.value

    # ── Supporting signals ────────────────────────────────────────────────

    # High risk score
    if source == EvidenceSourceType.MCP_GET_CASE:
        if "risk score" in claim_lower and isinstance(value, (int, float)):
            if value > RISK_SCORE_THRESHOLD:
                _link_support(ev, hyp_ids_by_name, [
                    "card_not_present_fraud", "card_not_present_new_device",
                    "account_takeover", "card_testing", "out_of_region_use",
                ])
                return True, False
        if "online" in claim_lower:
            _link_support(ev, hyp_ids_by_name, [
                "card_not_present_fraud", "card_not_present_new_device",
            ])
            return True, False

    # Prior fraud cases
    if source == EvidenceSourceType.MCP_CUSTOMER_HISTORY:
        if "prior confirmed fraud" in claim_lower and isinstance(value, (int, float)):
            if value > PRIOR_FRAUD_THRESHOLD:
                _link_support(ev, hyp_ids_by_name, [
                    "card_not_present_fraud", "account_takeover",
                ])
                return True, False
        if "0 prior confirmed fraud" in claim_lower:
            _link_contradict(ev, hyp_ids_by_name, [
                "card_not_present_fraud", "account_takeover",
            ])
            return False, True

    # Transaction context — device missing (supports account takeover / new device)
    if source == EvidenceSourceType.MCP_TRANSACTION_CONTEXT:
        if "no device identity record" in claim_lower:
            _link_support(ev, hyp_ids_by_name, [
                "card_not_present_new_device", "account_takeover",
            ])
            return True, False
        if "device:" in claim_lower:
            # Device present — slight evidence against new device hypothesis
            _link_contradict(ev, hyp_ids_by_name, ["card_not_present_new_device"])
            return False, True

    # Connected entities (fraud ring signal)
    if source == EvidenceSourceType.MCP_CONNECTED_ENTITIES:
        if isinstance(value, (int, float)) and value > CONNECTED_ENTITY_THRESHOLD:
            _link_support(ev, hyp_ids_by_name, [
                "account_takeover", "card_not_present_fraud",
            ])
            return True, False
        if isinstance(value, (int, float)) and value == 0:
            _link_contradict(ev, hyp_ids_by_name, ["account_takeover"])
            return False, True

    # Prior cases
    if source == EvidenceSourceType.MCP_PRIOR_CASES:
        if "0 prior cases" in claim_lower or (
            "confirmed fraud" in claim_lower and isinstance(value, dict)
            and value.get("fraud_cases", 0) > 0
        ):
            if isinstance(value, dict) and value.get("fraud_cases", 0) > 0:
                _link_support(ev, hyp_ids_by_name, [
                    "card_not_present_fraud", "account_takeover",
                ])
                return True, False
        # Most frequent pattern in history → supports that pattern hypothesis
        if "most frequent historical fraud pattern" in claim_lower and isinstance(value, str):
            pattern_name = value
            if pattern_name in hyp_ids_by_name:
                ev.supports.append(hyp_ids_by_name[pattern_name])
            return True, False

    # Temporal patterns — card testing
    if source == EvidenceSourceType.MCP_TEMPORAL_PATTERNS:
        if "card testing signal detected" in claim_lower:
            _link_support(ev, hyp_ids_by_name, ["card_testing"])
            return True, False
        if "burst activity" in claim_lower:
            _link_support(ev, hyp_ids_by_name, [
                "card_testing", "card_not_present_fraud",
            ])
            return True, False
        if "no temporal fraud signals" in claim_lower:
            _link_contradict(ev, hyp_ids_by_name, [
                "card_testing", "card_not_present_fraud",
            ])
            return False, True

    # Exposure — high exposure → supports taking action
    if source == EvidenceSourceType.MCP_EXPOSURE:
        if isinstance(value, dict):
            total = value.get("total_usd", 0.0)
            if total > 0:
                _link_support(ev, hyp_ids_by_name, [
                    "card_not_present_fraud", "account_takeover",
                ])
                return True, False

    # Shared devices
    if source == EvidenceSourceType.MCP_SHARED_DEVICES:
        if "does not share devices" in claim_lower:
            _link_contradict(ev, hyp_ids_by_name, ["account_takeover"])
            return False, True
        if "shares" in claim_lower and isinstance(value, dict):
            if value.get("devices_shared", 0) > SHARED_DEVICE_THRESHOLD:
                _link_support(ev, hyp_ids_by_name, [
                    "account_takeover", "card_not_present_fraud",
                ])
                return True, False

    return False, False  # neutral


def _link_support(
    ev: Evidence,
    hyp_ids_by_name: dict[str, str],
    pattern_names: list[str],
) -> None:
    for name in pattern_names:
        hid = hyp_ids_by_name.get(name)
        if hid and hid not in ev.supports:
            ev.supports.append(hid)


def _link_contradict(
    ev: Evidence,
    hyp_ids_by_name: dict[str, str],
    pattern_names: list[str],
) -> None:
    for name in pattern_names:
        hid = hyp_ids_by_name.get(name)
        if hid and hid not in ev.contradicts:
            ev.contradicts.append(hid)
