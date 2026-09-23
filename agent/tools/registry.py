"""
agent/tools/registry.py — Tool selection logic.

The agent does NOT blindly call all 8 tools on every case.
This module contains logic for:
1. Mapping trigger types to initial tool sets
2. Selecting additional tools based on evidence gaps
3. Determining when tools have already been called

The agent calls tools in logical order:
  ALWAYS: get_case, get_transaction_context, get_customer_history
  USUALLY: find_prior_cases, detect_temporal_patterns
  CONDITIONAL: find_connected_entities, find_shared_devices, calculate_exposure
"""

from __future__ import annotations

from typing import Any


# ── Tool groups by investigation phase ───────────────────────────────────────

# These tools are ALWAYS called in every investigation
MANDATORY_TOOLS = [
    "get_case",
    "get_transaction_context",
    "get_customer_history",
]

# These tools are called based on trigger type and evidence gaps
STANDARD_TOOLS = [
    "find_prior_cases",
    "detect_temporal_patterns",
    "calculate_exposure",
]

# These tools are called when specific evidence signals are present
CONDITIONAL_TOOLS = [
    "find_connected_entities",
    "find_shared_devices",
]


# ── Trigger-based tool selection ──────────────────────────────────────────────

# Maps trigger_type from case_pack to recommended tool sets
TRIGGER_TOOL_MAP: dict[str, list[str]] = {
    "risk_score": [
        "get_case",
        "get_transaction_context",
        "get_customer_history",
        "find_prior_cases",
        "detect_temporal_patterns",
        "calculate_exposure",
    ],
    "customer_report": [
        "get_case",
        "get_transaction_context",
        "get_customer_history",
        "find_prior_cases",
        "calculate_exposure",
    ],
    "analyst_request": [
        "get_case",
        "get_transaction_context",
        "get_customer_history",
        "find_connected_entities",
        "find_shared_devices",
        "find_prior_cases",
        "detect_temporal_patterns",
        "calculate_exposure",
    ],
}

# Default tool set for unknown trigger types
DEFAULT_TOOL_SET = [
    "get_case",
    "get_transaction_context",
    "get_customer_history",
    "find_prior_cases",
    "calculate_exposure",
]


def get_initial_tools(trigger_type: str) -> list[str]:
    """
    Return the initial set of tools to call based on the trigger type.

    Parameters
    ----------
    trigger_type : str
        The case trigger type from case_pack.csv

    Returns
    -------
    list[str]
        Ordered list of tool names to call
    """
    return TRIGGER_TOOL_MAP.get(trigger_type, DEFAULT_TOOL_SET).copy()


def get_additional_tools(
    evidence_gaps: list[str],
    already_called: set[str],
    temporal_signals: dict[str, Any] | None = None,
    connected_entity_count: int = 0,
) -> list[str]:
    """
    Determine additional tools to call based on evidence gaps.

    Parameters
    ----------
    evidence_gaps : list[str]
        Descriptions of missing evidence
    already_called : set[str]
        Tools already called in this investigation
    temporal_signals : dict | None
        Temporal pattern signals if already available
    connected_entity_count : int
        Number of connected entities found (triggers deeper investigation)

    Returns
    -------
    list[str]
        Additional tools to call
    """
    additional: list[str] = []

    # Check if device analysis is needed
    device_keywords = ["device", "DeviceInfo", "DeviceType", "shared device"]
    if any(kw in gap for kw in device_keywords for gap in evidence_gaps):
        if "find_shared_devices" not in already_called:
            additional.append("find_shared_devices")
        if "find_connected_entities" not in already_called:
            additional.append("find_connected_entities")

    # If temporal patterns show card testing signal, get connected entities
    if temporal_signals:
        signals = temporal_signals.get("signals", {})
        if signals.get("card_testing") and "find_connected_entities" not in already_called:
            additional.append("find_connected_entities")

    # If connected entities found, get shared devices for deeper ring analysis
    if connected_entity_count > 0 and "find_shared_devices" not in already_called:
        additional.append("find_shared_devices")

    # If prior cases not called yet and gaps mention history
    history_keywords = ["prior", "history", "historical", "past"]
    if any(kw in gap for kw in history_keywords for gap in evidence_gaps):
        if "find_prior_cases" not in already_called:
            additional.append("find_prior_cases")

    # Remove duplicates while preserving order
    seen: set[str] = set()
    result: list[str] = []
    for tool in additional:
        if tool not in seen:
            seen.add(tool)
            result.append(tool)

    return result


def should_call_tool(tool_name: str, already_called: set[str]) -> bool:
    """
    Return True if the tool should be called (i.e., hasn't been called yet).

    Tools should generally be called only once per investigation.
    """
    return tool_name not in already_called


def get_all_tool_names() -> list[str]:
    """Return the complete list of 8 MCP tool names from Part 1."""
    return [
        "get_case",
        "get_customer_history",
        "find_connected_entities",
        "find_prior_cases",
        "detect_temporal_patterns",
        "calculate_exposure",
        "find_shared_devices",
        "get_transaction_context",
    ]
