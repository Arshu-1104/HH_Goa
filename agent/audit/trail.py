"""
agent/audit/trail.py — Investigation audit trail writer.

Records every meaningful step of the investigation as a TrailEvent.
The trail is the complete, auditable record of what the agent did and why.
Every tool call, decision, and state transition is logged here.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any

from agent.state.models import TrailEvent

log = logging.getLogger(__name__)

_EVENT_COUNTER = 0


def _next_event_id() -> str:
    global _EVENT_COUNTER
    _EVENT_COUNTER += 1
    return f"EVT-{_EVENT_COUNTER:03d}"


def reset_trail_counter() -> None:
    global _EVENT_COUNTER
    _EVENT_COUNTER = 0


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


class InvestigationTrail:
    """Records and manages the investigation audit trail."""

    def __init__(self) -> None:
        self._events: list[TrailEvent] = []

    def log(
        self,
        step_type: str,
        description: str,
        tool: str = "",
        inputs: dict[str, Any] | None = None,
        outputs: dict[str, Any] | None = None,
        reason: str = "",
    ) -> TrailEvent:
        """
        Record a trail event.

        Parameters
        ----------
        step_type : str
            One of: CASE_LOADED, PLAN_CREATED, TOOL_CALLED, EVIDENCE_EXTRACTED,
            HYPOTHESIS_UPDATED, SUFFICIENCY_ASSESSED, UNCERTAINTY_ASSESSED,
            EVIDENCE_REQUESTED, POLICY_EVALUATED, ACTION_SELECTED, APPROVAL_ROUTED,
            MEMORY_WRITTEN, SUMMARY_GENERATED, ERROR
        description : str
            Human-readable description of what happened
        tool : str
            MCP tool name (if applicable)
        inputs : dict
            Inputs to this step
        outputs : dict
            Key outputs from this step
        reason : str
            Why this step was taken
        """
        event = TrailEvent(
            event_id=_next_event_id(),
            timestamp=_now(),
            step_type=step_type,
            description=description,
            tool=tool,
            inputs=inputs or {},
            outputs=outputs or {},
            reason=reason,
        )
        self._events.append(event)
        log.debug(f"Trail [{event.event_id}] {step_type}: {description[:80]}")
        return event

    def get_events(self) -> list[TrailEvent]:
        return list(self._events)

    def get_summary_lines(self) -> list[str]:
        """Return a human-readable summary of trail events."""
        return [
            f"[{e.event_id}] {e.timestamp[:19]} | {e.step_type}: {e.description}"
            for e in self._events
        ]

    def get_tool_calls(self) -> list[TrailEvent]:
        return [e for e in self._events if e.step_type == "TOOL_CALLED"]

    def get_errors(self) -> list[TrailEvent]:
        return [e for e in self._events if e.step_type == "ERROR"]
