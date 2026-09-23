"""
agent/sufficiency/config.py — Sufficiency thresholds and required categories.

These are the deterministic thresholds the SufficiencyEngine uses.
All values are based on what the 8 MCP tools can realistically provide.
"""

from agent.evidence.models import EvidenceCategory

# Minimum evidence items required per category for PARTIAL sufficiency
MIN_ITEMS_PER_CATEGORY: dict[str, int] = {
    EvidenceCategory.TRANSACTION: 1,   # At least get_case or get_transaction_context
    EvidenceCategory.CUSTOMER: 1,      # At least get_customer_history
    EvidenceCategory.HISTORICAL: 1,    # At least find_prior_cases
}

# Required categories for SUFFICIENT (can recommend any action including BLOCK_CARD)
REQUIRED_FOR_SUFFICIENT: list[str] = [
    EvidenceCategory.TRANSACTION,
    EvidenceCategory.CUSTOMER,
    EvidenceCategory.HISTORICAL,
    EvidenceCategory.EXPOSURE,
]

# Required categories for PARTIAL (can recommend non-disruptive actions only)
REQUIRED_FOR_PARTIAL: list[str] = [
    EvidenceCategory.TRANSACTION,
    EvidenceCategory.CUSTOMER,
]

# Minimum supporting evidence items for any action
MIN_SUPPORTING_FOR_ACTION = 1

# If reassessment count exceeds this, force SUFFICIENT to avoid infinite loop
MAX_REASSESSMENTS = 2
