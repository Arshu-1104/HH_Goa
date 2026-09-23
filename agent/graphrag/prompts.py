"""
agent/graphrag/prompts.py — LLM prompt templates for investigation nodes.

All prompts are strictly grounded. The LLM receives only facts that appear
in the context pack built from real MCP evidence. Instructions forbid
inventing facts not in the provided context.
"""

from __future__ import annotations

SYSTEM_FRAUD_INVESTIGATOR = """You are a fraud investigation AI assistant.
You reason strictly from provided evidence. You NEVER invent facts, amounts,
customer IDs, transaction IDs, or device details that are not explicitly stated
in the context you are given. Every factual claim in your response must cite
an evidence ID (e.g. [EV-001]).

You produce structured JSON responses only. Do not add commentary outside the JSON."""

ANALYSIS_PROMPT_TEMPLATE = """{context}

Based on the evidence above, respond with a JSON object:
{{
  "key_findings": ["finding 1 [EV-xxx]", "finding 2 [EV-xxx]", ...],
  "identified_patterns": ["pattern_name", ...],
  "reasoning": "brief explanation citing evidence IDs"
}}

Only include patterns from this list: account_takeover, card_not_present_fraud,
card_not_present_new_device, card_testing, out_of_region_use, undocumented, none.
"""

DECISION_PROMPT_TEMPLATE = """{context}

Based on the evidence and policy context above, respond with a JSON object:
{{
  "recommended_action": "ACTION_NAME",
  "reason": "explanation citing evidence IDs",
  "supporting_evidence_ids": ["EV-001", ...],
  "risk_level": "low|medium|high",
  "confidence": 0.0
}}

Only use these actions: BLOCK_CARD, VERIFY_WITH_CUSTOMER, FILE_REPORT,
CLOSE_NO_FRAUD, ESCALATE, MONITOR, REQUEST_MORE_EVIDENCE.
"""

SUMMARY_PROMPT_TEMPLATE = """{context}

Write a final investigation summary as a JSON object:
{{
  "key_findings": ["finding [EV-xxx]", ...],
  "identified_patterns": ["pattern_name", ...],
  "supporting_evidence_summary": "2-3 sentences citing EV-ids",
  "contradictory_evidence_summary": "1-2 sentences or 'None'",
  "decision_reasoning": "Why this action was chosen, citing evidence",
  "case_outcome": "Outcome description"
}}
"""
