"""
agent/memory/retriever.py — Retrieves prior investigation memories.

Searches the investigation_reports/ directory for similar prior cases
to inform the current investigation.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

log = logging.getLogger(__name__)

_MEMORY_DIR = Path(__file__).parent.parent.parent / "investigation_reports"


class CaseMemoryRetriever:
    """Retrieves stored investigation memories."""

    def __init__(self, memory_dir: Path | None = None) -> None:
        self._dir = memory_dir or _MEMORY_DIR

    def get_all(self) -> list[dict[str, Any]]:
        """
        Return all stored case memories.

        Only returns valid case-memory documents — dicts that contain
        both a "memory" object and a "case_id" string.  Any other JSON
        artifacts in the directory (e.g. batch_summary.json, which is a
        list) are silently skipped.
        """
        results: list[dict[str, Any]] = []
        if not self._dir.exists():
            return results
        for path in sorted(self._dir.glob("*.json")):
            try:
                with open(path, encoding="utf-8") as f:
                    data = json.load(f)
            except Exception as exc:
                log.warning(f"Could not load memory {path}: {exc}")
                continue

            # Filter: must be a dict with both "memory" and "case_id"
            if not isinstance(data, dict):
                log.debug(f"Skipping {path.name}: not a JSON object (got {type(data).__name__})")
                continue
            if "memory" not in data or not isinstance(data["memory"], dict):
                log.debug(f"Skipping {path.name}: missing or invalid 'memory' key")
                continue
            if not data.get("case_id"):
                log.debug(f"Skipping {path.name}: missing 'case_id'")
                continue

            results.append(data)
        return results

    def get_similar(
        self,
        customer_id: str | None = None,
        fraud_patterns: list[str] | None = None,
    ) -> list[dict[str, Any]]:
        """
        Find memories for the same customer or matching fraud patterns.
        Returns at most 5 most relevant memories.
        """
        all_memories = self.get_all()
        scored: list[tuple[int, dict[str, Any]]] = []

        for mem in all_memories:
            memory_data = mem.get("memory", {})
            score = 0
            if customer_id and memory_data.get("customer_id") == customer_id:
                score += 10
            if fraud_patterns:
                stored_patterns = memory_data.get("fraud_patterns_identified", [])
                matches = set(fraud_patterns) & set(stored_patterns)
                score += len(matches) * 3
            if score > 0:
                scored.append((score, mem))

        scored.sort(key=lambda x: x[0], reverse=True)
        return [m for _, m in scored[:5]]

    def get_prior_actions(self, customer_id: str) -> list[str]:
        """Return list of final actions from prior investigations for this customer."""
        similar = self.get_similar(customer_id=customer_id)
        return [
            m["memory"].get("final_action", "")
            for m in similar
            if m.get("memory", {}).get("final_action")
        ]
