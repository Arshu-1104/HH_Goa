"""
agent/evidence/models.py — Evidence category definitions.

Evidence categories are used by the sufficiency engine to determine
whether enough evidence has been gathered in each dimension.
"""

from __future__ import annotations

from enum import Enum


class EvidenceCategory(str, Enum):
    """
    Categories of evidence relevant to fraud investigation.

    Each category corresponds to a different dimension of the investigation.
    The sufficiency engine checks that required categories have evidence.
    """
    TRANSACTION = "transaction"         # Evidence from the flagged transaction itself
    BEHAVIOR = "behavior"               # Evidence from customer behavior patterns
    IDENTITY = "identity"               # Evidence from device/identity data
    RELATIONSHIP = "relationship"       # Evidence from graph relationships (shared devices, etc.)
    HISTORICAL = "historical"           # Evidence from prior cases
    CUSTOMER = "customer"               # Evidence about the customer profile
    EXPOSURE = "exposure"               # Evidence about financial exposure
    POLICY = "policy"                   # Evidence relevant to policy decisions


# Maps evidence source types to their categories
EVIDENCE_SOURCE_TO_CATEGORY = {
    "get_case": [EvidenceCategory.TRANSACTION],
    "get_customer_history": [EvidenceCategory.CUSTOMER, EvidenceCategory.HISTORICAL],
    "get_transaction_context": [EvidenceCategory.TRANSACTION, EvidenceCategory.IDENTITY],
    "find_connected_entities": [EvidenceCategory.RELATIONSHIP],
    "find_prior_cases": [EvidenceCategory.HISTORICAL],
    "detect_temporal_patterns": [EvidenceCategory.BEHAVIOR],
    "calculate_exposure": [EvidenceCategory.EXPOSURE],
    "find_shared_devices": [EvidenceCategory.RELATIONSHIP, EvidenceCategory.IDENTITY],
    "injected": [EvidenceCategory.CUSTOMER],
    "derived": [],
}
