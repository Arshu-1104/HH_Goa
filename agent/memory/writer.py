"""
agent/memory/writer.py — Writes completed investigation to case memory.

Persists CaseMemory as a JSON file under investigation_reports/.
Each case gets its own file: investigation_reports/{case_id}.json
This is the long-term memory store for the agent.
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from agent.state.models import CaseMemory, FinalSummary

log = logging.getLogger(__name__)

_MEMORY_DIR = Path(__file__).parent.parent.parent / "investigation_reports"


class CaseMemoryWriter:
    """Writes investigation results to persistent JSON files."""

    def __init__(self, memory_dir: Path | None = None) -> None:
        self._dir = memory_dir or _MEMORY_DIR
        self._dir.mkdir(parents=True, exist_ok=True)

    def write(self, case_id: str, summary: FinalSummary, memory: CaseMemory) -> Path:
        """
        Persist investigation memory to disk.

        Parameters
        ----------
        case_id : str
        summary : FinalSummary
        memory : CaseMemory

        Returns
        -------
        Path — path to the written file
        """
        payload = {
            "case_id": case_id,
            "written_at": datetime.now(timezone.utc).isoformat(),
            "memory": memory.model_dump(),
            "summary": summary.model_dump(),
        }
        path = self._dir / f"{case_id}.json"
        with open(path, "w", encoding="utf-8") as f:
            json.dump(payload, f, indent=2, default=str)

        log.info(f"Case memory written: {path}")
        return path

    def load(self, case_id: str) -> dict[str, Any] | None:
        """Load a previously written case memory, or None if not found."""
        path = self._dir / f"{case_id}.json"
        if not path.exists():
            return None
        with open(path, encoding="utf-8") as f:
            return json.load(f)
