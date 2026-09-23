"""
agent/evidence/provenance.py — Evidence provenance tracker.

Tracks the chain from tool call → raw result → evidence item.
Every evidence item must be traceable to its source tool call.
"""

from __future__ import annotations

import logging
from typing import Any

from agent.state.models import Evidence, ToolCall

log = logging.getLogger(__name__)


class ProvenanceTracker:
    """
    Tracks which tool call produced which evidence items.

    Usage:
        tracker = ProvenanceTracker()
        tracker.record_tool_call(tool_call, raw_result, evidence_items)
        chain = tracker.get_chain("EV-003")
    """

    def __init__(self) -> None:
        # evidence_id → ToolCall
        self._ev_to_call: dict[str, ToolCall] = {}
        # evidence_id → raw tool result dict
        self._ev_to_raw: dict[str, dict[str, Any]] = {}
        # tool call_id → list of evidence_ids produced
        self._call_to_evidence: dict[str, list[str]] = {}

    def record(
        self,
        tool_call: ToolCall,
        raw_result: dict[str, Any],
        evidence_items: list[Evidence],
    ) -> None:
        """
        Record the relationship between a tool call and its evidence output.

        Parameters
        ----------
        tool_call : ToolCall
            The tool call that was made
        raw_result : dict
            The raw output from the MCP server
        evidence_items : list[Evidence]
            Evidence extracted from this tool call
        """
        call_id = tool_call.call_id
        ev_ids: list[str] = []

        for ev in evidence_items:
            self._ev_to_call[ev.evidence_id] = tool_call
            self._ev_to_raw[ev.evidence_id] = raw_result
            ev_ids.append(ev.evidence_id)

        self._call_to_evidence[call_id] = ev_ids
        log.debug(
            f"Provenance: {tool_call.tool_name} call {call_id} → "
            f"{len(ev_ids)} evidence items"
        )

    def get_tool_call(self, evidence_id: str) -> ToolCall | None:
        """Return the ToolCall that produced this evidence item."""
        return self._ev_to_call.get(evidence_id)

    def get_raw_result(self, evidence_id: str) -> dict[str, Any] | None:
        """Return the raw MCP result that produced this evidence item."""
        return self._ev_to_raw.get(evidence_id)

    def get_evidence_ids_for_call(self, call_id: str) -> list[str]:
        """Return all evidence IDs produced by a specific tool call."""
        return self._call_to_evidence.get(call_id, [])

    def get_chain(self, evidence_id: str) -> dict[str, Any]:
        """
        Return the full provenance chain for an evidence item.

        Returns
        -------
        dict with keys:
            evidence_id, tool_name, call_id, params, timestamp, raw_snippet
        """
        call = self._ev_to_call.get(evidence_id)
        raw = self._ev_to_raw.get(evidence_id)

        if call is None:
            return {"evidence_id": evidence_id, "error": "No provenance recorded"}

        # Only return a snippet of the raw result (first 500 chars) for readability
        raw_str = str(raw)
        raw_snippet = raw_str[:500] + ("…" if len(raw_str) > 500 else "")

        return {
            "evidence_id": evidence_id,
            "tool_name": call.tool_name,
            "call_id": call.call_id,
            "params": call.params,
            "timestamp": call.timestamp,
            "raw_snippet": raw_snippet,
        }

    def summary(self) -> dict[str, Any]:
        """Return a summary of all provenance records."""
        return {
            "total_evidence_items": len(self._ev_to_call),
            "total_tool_calls": len(self._call_to_evidence),
            "tools_called": list({c.tool_name for c in self._ev_to_call.values()}),
        }
