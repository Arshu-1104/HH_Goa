"""
agent/tools/adapters.py — Normalize raw MCP output into typed ToolResult models.

This layer sits between the MCP client and the evidence extractor.
It normalizes raw dict outputs from MCP tools into consistent structures,
isolating Part 2 from any Part 1 output format changes.

IMPORTANT: This adapter does NOT modify Part 1 code.
It only normalizes what Part 1 returns.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any

log = logging.getLogger(__name__)


@dataclass
class ToolResult:
    """
    Normalized result from a single MCP tool call.
    Contains both the raw output (for provenance) and structured fields.
    """
    tool_name: str
    success: bool
    raw: dict[str, Any]           # Original output — preserved for provenance
    error: str = ""

    # ── Normalized fields populated by each adapter ───────────────────────
    # These are always present (may be None/empty if tool returned nothing useful)
    case_data: dict[str, Any] = field(default_factory=dict)
    transaction_data: dict[str, Any] = field(default_factory=dict)
    customer_data: dict[str, Any] = field(default_factory=dict)
    connected_entities: list[dict[str, Any]] = field(default_factory=list)
    prior_cases: list[dict[str, Any]] = field(default_factory=list)
    temporal_signals: dict[str, Any] = field(default_factory=dict)
    exposure_data: dict[str, Any] = field(default_factory=dict)
    shared_devices: list[dict[str, Any]] = field(default_factory=list)


def adapt_get_case(raw: dict[str, Any]) -> ToolResult:
    """Normalize get_case output."""
    if not raw.get("found", False):
        return ToolResult(
            tool_name="get_case",
            success=False,
            raw=raw,
            error=raw.get("error", "Case not found"),
        )

    return ToolResult(
        tool_name="get_case",
        success=True,
        raw=raw,
        case_data=raw.get("case", {}),
        transaction_data=raw.get("flagged_transaction") or {},
    )


def adapt_get_customer_history(raw: dict[str, Any]) -> ToolResult:
    """Normalize get_customer_history output."""
    if not raw.get("found", False):
        return ToolResult(
            tool_name="get_customer_history",
            success=False,
            raw=raw,
            error=f"Customer not found: {raw.get('customer_id', '?')}",
        )

    return ToolResult(
        tool_name="get_customer_history",
        success=True,
        raw=raw,
        customer_data={
            "customer_id": raw.get("customer_id"),
            "transaction_count": raw.get("transaction_count", 0),
            "total_transaction_amt": raw.get("total_transaction_amt", 0.0),
            "fraud_case_count": raw.get("fraud_case_count", 0),
            "total_fraud_exposure_usd": raw.get("total_fraud_exposure_usd", 0.0),
            "recent_transactions": raw.get("recent_transactions", []),
            "closed_cases": raw.get("closed_cases", []),
        },
        prior_cases=raw.get("closed_cases", []),
    )


def adapt_find_connected_entities(raw: dict[str, Any]) -> ToolResult:
    """Normalize find_connected_entities output."""
    entities = raw.get("connected_entities", [])
    return ToolResult(
        tool_name="find_connected_entities",
        success=True,
        raw=raw,
        connected_entities=entities,
        customer_data={
            "entity_id": raw.get("entity_id"),
            "entity_type": raw.get("entity_type"),
            "connected_entity_count": raw.get("connected_entity_count", 0),
            "seed_devices": raw.get("seed_devices", []),
            "seed_email_domains": raw.get("seed_email_domains", []),
            "seed_regions": raw.get("seed_regions", []),
        },
    )


def adapt_find_prior_cases(raw: dict[str, Any]) -> ToolResult:
    """Normalize find_prior_cases output."""
    return ToolResult(
        tool_name="find_prior_cases",
        success=True,
        raw=raw,
        prior_cases=raw.get("cases", []),
        customer_data={
            "total_cases": raw.get("total_cases", 0),
            "fraud_cases": raw.get("fraud_cases", 0),
            "cleared_cases": raw.get("cleared_cases", 0),
            "total_exposure_usd": raw.get("total_exposure_usd", 0.0),
        },
    )


def adapt_detect_temporal_patterns(raw: dict[str, Any]) -> ToolResult:
    """Normalize detect_temporal_patterns output."""
    return ToolResult(
        tool_name="detect_temporal_patterns",
        success=True,
        raw=raw,
        temporal_signals={
            "customer_id": raw.get("customer_id"),
            "total_transactions": raw.get("total_transactions", 0),
            "window_hours": raw.get("window_hours", 24),
            "transactions_in_window": raw.get("transactions_in_window", 0),
            "micro_transaction_count": raw.get("micro_transaction_count", 0),
            "online_transaction_count": raw.get("online_transaction_count", 0),
            "in_person_transaction_count": raw.get("in_person_transaction_count", 0),
            "signals": raw.get("signals", {}),
            "avg_transaction_amt": raw.get("avg_transaction_amt", 0.0),
            "max_transaction_amt": raw.get("max_transaction_amt", 0.0),
            "min_transaction_amt": raw.get("min_transaction_amt", 0.0),
            "window_transaction_ids": raw.get("window_transaction_ids", []),
        },
    )


def adapt_calculate_exposure(raw: dict[str, Any]) -> ToolResult:
    """Normalize calculate_exposure output."""
    return ToolResult(
        tool_name="calculate_exposure",
        success=True,
        raw=raw,
        exposure_data={
            "customer_id": raw.get("customer_id"),
            "card_id": raw.get("card_id"),
            "confirmed_fraud_cases": raw.get("confirmed_fraud_cases", 0),
            "total_confirmed_exposure_usd": raw.get("total_confirmed_exposure_usd", 0.0),
            "avg_fraud_exposure_usd": raw.get("avg_fraud_exposure_usd", 0.0),
            "pending_investigation_txns": raw.get("pending_investigation_txns", []),
            "pending_exposure_usd": raw.get("pending_exposure_usd", 0.0),
            "fraud_cases_detail": raw.get("fraud_cases_detail", []),
        },
    )


def adapt_find_shared_devices(raw: dict[str, Any]) -> ToolResult:
    """Normalize find_shared_devices output."""
    return ToolResult(
        tool_name="find_shared_devices",
        success=True,
        raw=raw,
        shared_devices=raw.get("device_details", []),
        customer_data={
            "customer_id": raw.get("customer_id"),
            "devices_found": raw.get("devices_found", 0),
            "devices_shared_with_others": raw.get("devices_shared_with_others", 0),
            "total_shared_customer_count": raw.get("total_shared_customer_count", 0),
            "shared_with_customers": raw.get("shared_with_customers", []),
        },
    )


def adapt_get_transaction_context(raw: dict[str, Any]) -> ToolResult:
    """Normalize get_transaction_context output."""
    if not raw.get("found", False):
        return ToolResult(
            tool_name="get_transaction_context",
            success=False,
            raw=raw,
            error=raw.get("error", "Transaction not found"),
        )

    return ToolResult(
        tool_name="get_transaction_context",
        success=True,
        raw=raw,
        transaction_data=raw.get("transaction") or {},
        customer_data={
            "customer_id": raw.get("customer_id"),
            "customer_prior_fraud_cases": raw.get("customer_prior_fraud_cases", 0),
            "customer_recent_transactions": raw.get("customer_recent_transactions", []),
        },
    )


# ── Dispatch table ────────────────────────────────────────────────────────────

_ADAPTERS = {
    "get_case": adapt_get_case,
    "get_customer_history": adapt_get_customer_history,
    "find_connected_entities": adapt_find_connected_entities,
    "find_prior_cases": adapt_find_prior_cases,
    "detect_temporal_patterns": adapt_detect_temporal_patterns,
    "calculate_exposure": adapt_calculate_exposure,
    "find_shared_devices": adapt_find_shared_devices,
    "get_transaction_context": adapt_get_transaction_context,
}


def adapt(tool_name: str, raw: dict[str, Any]) -> ToolResult:
    """
    Adapt raw MCP output for a named tool.

    Parameters
    ----------
    tool_name : str
        The MCP tool name
    raw : dict
        Raw output dict from the MCP server

    Returns
    -------
    ToolResult
        Normalized result
    """
    adapter = _ADAPTERS.get(tool_name)
    if adapter is None:
        log.warning(f"No adapter for tool: {tool_name!r} — returning raw")
        return ToolResult(
            tool_name=tool_name,
            success=True,
            raw=raw,
        )

    try:
        return adapter(raw)
    except Exception as exc:
        log.error(f"Adapter for {tool_name!r} raised: {exc}")
        return ToolResult(
            tool_name=tool_name,
            success=False,
            raw=raw,
            error=f"Adapter error: {exc}",
        )
