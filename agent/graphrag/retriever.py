"""
agent/graphrag/retriever.py — Fetch additional graph evidence via MCP tools.

Called when the sufficiency engine says evidence is INSUFFICIENT.
Selects which uncalled tools would best fill the gaps and calls them.
"""

from __future__ import annotations

import logging
import time
from datetime import datetime, timezone
from typing import Any

from agent.state.models import Evidence, ToolCall
from agent.tools.adapters import adapt
from agent.tools.registry import get_additional_tools

log = logging.getLogger(__name__)

_CALL_COUNTER = 0


def _next_call_id() -> str:
    global _CALL_COUNTER
    _CALL_COUNTER += 1
    return f"TC-{_CALL_COUNTER:03d}"


def reset_call_counter() -> None:
    global _CALL_COUNTER
    _CALL_COUNTER = 0


class GraphRAGRetriever:
    """
    Fetches additional graph evidence from MCP when gaps are identified.
    Never calls a tool more than once per investigation.
    """

    def __init__(self, mcp_client: Any) -> None:
        self._client = mcp_client

    def fetch_additional_evidence(
        self,
        missing_evidence: list[str],
        already_called: set[str],
        customer_id: str,
        card_id: str,
        transaction_id: str,
        temporal_signals: dict[str, Any] | None = None,
        connected_entity_count: int = 0,
    ) -> tuple[list[ToolCall], dict[str, Any]]:
        """
        Determine and call additional MCP tools to fill evidence gaps.

        Returns
        -------
        tuple[list[ToolCall], dict[str, Any]]
            (tool_calls_made, raw_results_dict)
        """
        additional = get_additional_tools(
            evidence_gaps=missing_evidence,
            already_called=already_called,
            temporal_signals=temporal_signals,
            connected_entity_count=connected_entity_count,
        )

        # Always try these standard tools if not yet called
        for tool in ["find_prior_cases", "detect_temporal_patterns",
                     "calculate_exposure", "get_transaction_context"]:
            if tool not in already_called and tool not in additional:
                additional.append(tool)

        tool_calls: list[ToolCall] = []
        raw_results: dict[str, Any] = {}

        for tool in additional:
            if tool in already_called:
                continue
            try:
                t0 = time.monotonic()
                raw = self._call_tool(tool, customer_id, card_id, transaction_id)
                latency = (time.monotonic() - t0) * 1000
                now = datetime.now(timezone.utc).isoformat()

                params = self._build_params(tool, customer_id, card_id, transaction_id)
                tc = ToolCall(
                    call_id=_next_call_id(),
                    tool_name=tool,
                    params=params,
                    result=raw,
                    success=True,
                    latency_ms=round(latency, 1),
                    timestamp=now,
                )
                tool_calls.append(tc)
                raw_results[tool] = raw
                already_called.add(tool)
                log.info(f"GraphRAG fetched: {tool} ({latency:.0f}ms)")

            except Exception as exc:
                log.warning(f"GraphRAG tool {tool} failed: {exc}")
                tc = ToolCall(
                    call_id=_next_call_id(),
                    tool_name=tool,
                    params=self._build_params(tool, customer_id, card_id, transaction_id),
                    success=False,
                    error=str(exc),
                    timestamp=datetime.now(timezone.utc).isoformat(),
                )
                tool_calls.append(tc)

        return tool_calls, raw_results

    def _build_params(
        self, tool: str, customer_id: str, card_id: str, transaction_id: str
    ) -> dict[str, Any]:
        if tool == "get_case":
            return {}
        if tool in ("get_customer_history", "detect_temporal_patterns",
                    "find_shared_devices", "find_connected_entities"):
            return {"customer_id": customer_id}
        if tool == "find_prior_cases":
            return {"customer_id": customer_id, "card_id": card_id}
        if tool == "calculate_exposure":
            return {"customer_id": customer_id}
        if tool == "get_transaction_context":
            return {"txn_id": transaction_id}
        return {"customer_id": customer_id}

    def _call_tool(
        self, tool: str, customer_id: str, card_id: str, transaction_id: str
    ) -> dict[str, Any]:
        if tool == "get_customer_history":
            return self._client.get_customer_history(customer_id=customer_id)
        if tool == "find_prior_cases":
            return self._client.find_prior_cases(
                customer_id=customer_id, card_id=card_id
            )
        if tool == "detect_temporal_patterns":
            return self._client.detect_temporal_patterns(customer_id=customer_id)
        if tool == "calculate_exposure":
            return self._client.calculate_exposure(customer_id=customer_id)
        if tool == "find_connected_entities":
            return self._client.find_connected_entities(entity_id=customer_id)
        if tool == "find_shared_devices":
            return self._client.find_shared_devices(customer_id=customer_id)
        if tool == "get_transaction_context":
            return self._client.get_transaction_context(txn_id=transaction_id)
        raise ValueError(f"Unknown tool: {tool!r}")
