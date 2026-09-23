"""
agent/policy/rules.py — Deterministic policy rules.

Rules are derived from actual closed_cases_history.csv action patterns:
  CREATE_CASE|BLOCK_CARD              — 4,268 cases (most common)
  VERIFY_WITH_CUSTOMER|CLOSE_NO_FRAUD — 900 cases
  CREATE_CASE|BLOCK_CARD|FILE_REPORT  — 397 cases

Rules are purely deterministic. No LLM involved.
"""

from __future__ import annotations

from agent.state.models import ActionType, ApprovalRoute, SufficiencyLevel, UncertaintyLevel


# ── Rule definitions ──────────────────────────────────────────────────────────
# Each rule is (condition_description, action, approval_route, risk_level)

POLICY_RULES: list[dict] = [
    {
        "rule_id": "RULE-001",
        "name": "Block card on confirmed fraud pattern + sufficient evidence",
        "action": ActionType.BLOCK_CARD,
        "conditions": {
            "sufficiency": [SufficiencyLevel.SUFFICIENT],
            "min_supporting": 2,
            "min_exposure": 0.0,
            "trigger_types": ["risk_score", "customer_report", "analyst_request"],
        },
        "approval_route": ApprovalRoute.FRAUD_ANALYST,
        "risk_level": "high",
    },
    {
        "rule_id": "RULE-002",
        "name": "File report on high-exposure confirmed fraud",
        "action": ActionType.FILE_REPORT,
        "conditions": {
            "sufficiency": [SufficiencyLevel.SUFFICIENT],
            "min_supporting": 3,
            "min_exposure": 500.0,
        },
        "approval_route": ApprovalRoute.SENIOR_ANALYST,
        "risk_level": "high",
    },
    {
        "rule_id": "RULE-003",
        "name": "Verify with customer on customer-reported case",
        "action": ActionType.VERIFY_WITH_CUSTOMER,
        "conditions": {
            "sufficiency": [SufficiencyLevel.PARTIAL, SufficiencyLevel.SUFFICIENT],
            "trigger_types": ["customer_report"],
            "min_supporting": 0,
        },
        "approval_route": ApprovalRoute.NONE,
        "risk_level": "low",
    },
    {
        "rule_id": "RULE-004",
        "name": "Monitor on low-confidence partial evidence",
        "action": ActionType.MONITOR,
        "conditions": {
            "sufficiency": [SufficiencyLevel.PARTIAL],
            "max_uncertainty": UncertaintyLevel.MEDIUM,
            "min_supporting": 1,
        },
        "approval_route": ApprovalRoute.NONE,
        "risk_level": "low",
    },
    {
        "rule_id": "RULE-005",
        "name": "Close no fraud on strong contradictory evidence",
        "action": ActionType.CLOSE_NO_FRAUD,
        "conditions": {
            "min_contradictory": 2,
            "max_supporting": 1,
        },
        "approval_route": ApprovalRoute.FRAUD_ANALYST,
        "risk_level": "medium",
    },
    {
        "rule_id": "RULE-006",
        "name": "Escalate on high uncertainty + high exposure",
        "action": ActionType.ESCALATE,
        "conditions": {
            "uncertainty": [UncertaintyLevel.HIGH],
            "min_exposure": 500.0,
        },
        "approval_route": ApprovalRoute.SENIOR_ANALYST,
        "risk_level": "high",
    },
    {
        "rule_id": "RULE-007",
        "name": "Request more evidence on insufficient evidence",
        "action": ActionType.REQUEST_MORE_EVIDENCE,
        "conditions": {
            "sufficiency": [SufficiencyLevel.INSUFFICIENT],
        },
        "approval_route": ApprovalRoute.NONE,
        "risk_level": "low",
    },
]
