"""
agent/graph/workflow.py — Main investigation workflow orchestrator.

Implements the full investigation loop as a sequential state machine.
Routing logic mirrors LangGraph's conditional edges but uses pure Python
(LangGraph itself is broken in this environment due to dependency conflicts).

Flow:
  load_case
  → plan_investigation
  → collect_evidence
  → analyze_evidence
  → update_hypotheses
  → assess_uncertainty
  → assess_sufficiency
      → INSUFFICIENT (max 2 retries): request_evidence → re-analyze → re-assess
      → PARTIAL/SUFFICIENT: evaluate_policy
  → evaluate_policy
  → determine_next_best_action
  → generate_final_summary
  → write_case_memory
  → COMPLETE

Note on node order: generate_final_summary runs BEFORE write_case_memory so that
the persisted report contains the real FinalSummary (including actual TransactionAmt
from the dataset), not a placeholder.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

from agent.audit.trail import InvestigationTrail, reset_trail_counter
from agent.evidence.provenance import ProvenanceTracker
from agent.graph.nodes import (
    analyze_evidence,
    assess_sufficiency,
    assess_uncertainty,
    collect_evidence,
    determine_next_best_action,
    evaluate_policy,
    generate_final_summary,
    load_case,
    plan_investigation,
    request_evidence,
    update_hypotheses,
    write_case_memory,
)
from agent.state.models import InvestigationStatus, SufficiencyLevel
from agent.state.state import InvestigationState, create_initial_state
from agent.tools.mcp_client import MCPDirectClient, build_mcp_client

log = logging.getLogger(__name__)

MAX_REASSESSMENTS = 2


class InvestigationWorkflow:
    """
    Runs a complete fraud investigation for a single case.

    Usage:
        workflow = InvestigationWorkflow()
        result = workflow.run("HHG-001")
        print(result["final_summary"])
    """

    def __init__(
        self,
        mcp_client: Any | None = None,
        data_dir: Path | None = None,
        debug: bool = False,
    ) -> None:
        """
        Parameters
        ----------
        mcp_client : Any | None
            MCP client to use. If None, builds MCPDirectClient (no HTTP needed).
        data_dir : Path | None
            Data directory for MCPDirectClient.
        debug : bool
            Enable debug logging.
        """
        if mcp_client is not None:
            self._client = mcp_client
        else:
            self._client = build_mcp_client(use_direct=True, data_dir=data_dir)

        self._debug = debug
        if debug:
            logging.getLogger("agent").setLevel(logging.DEBUG)

    def run(self, case_id: str) -> InvestigationState:
        """
        Run the complete investigation for a case.

        Parameters
        ----------
        case_id : str
            The case ID, e.g. "HHG-001"

        Returns
        -------
        InvestigationState
            Final state including all evidence, decisions, and summary
        """
        log.info(f"{'='*60}")
        log.info(f"Starting investigation: {case_id}")
        log.info(f"{'='*60}")

        # Reset counters for clean run
        reset_trail_counter()
        trail = InvestigationTrail()
        provenance = ProvenanceTracker()

        # Create initial state
        state: dict = dict(create_initial_state(case_id, debug_mode=self._debug))

        # ── Step 1: Load case ──────────────────────────────────────────────
        state.update(load_case(state, self._client, trail))
        if state.get("investigation_status") == InvestigationStatus.ERROR:
            log.error(f"Failed to load case {case_id}")
            return InvestigationState(**state)

        # ── Step 2: Plan ───────────────────────────────────────────────────
        state.update(plan_investigation(state, trail))

        # ── Step 3: Collect initial evidence ──────────────────────────────
        state.update(collect_evidence(state, self._client, trail, provenance))

        # ── Steps 4–7: Analyze + assess (with reassessment loop) ──────────
        for attempt in range(MAX_REASSESSMENTS + 1):
            state.update(analyze_evidence(state, trail))
            state.update(update_hypotheses(state, trail))
            state.update(assess_uncertainty(state, trail))
            state.update(assess_sufficiency(state, trail))

            suf = state.get("evidence_sufficiency")
            if suf is None or suf.level == SufficiencyLevel.INSUFFICIENT:
                if attempt < MAX_REASSESSMENTS:
                    log.info(
                        f"Evidence insufficient (attempt {attempt + 1}/{MAX_REASSESSMENTS}) "
                        "— requesting more evidence"
                    )
                    state.update(
                        request_evidence(state, self._client, trail, provenance)
                    )
                    # Re-run collect for any newly identified tools
                    state.update(collect_evidence(state, self._client, trail, provenance))
                else:
                    log.info("Max reassessments reached — proceeding with available evidence")
                    break
            else:
                log.info(f"Evidence sufficiency: {suf.level.value} — proceeding to policy")
                break

        # ── Step 8: Policy evaluation ──────────────────────────────────────
        if "evidence_sufficiency" not in state or state.get("evidence_sufficiency") is None:
            log.error("No sufficiency result — aborting")
            state["investigation_status"] = InvestigationStatus.ERROR
            return InvestigationState(**state)

        state.update(evaluate_policy(state, trail))

        # ── Step 9: Next best action ───────────────────────────────────────
        state.update(determine_next_best_action(state, trail))

        # ── Step 10: Write memory ──────────────────────────────────────────
        # generate_final_summary runs FIRST so the persisted report contains
        # the real FinalSummary (including actual TransactionAmt from the
        # dataset) rather than a placeholder with transaction_amount=0.0.
        state.update(generate_final_summary(state, trail))

        # ── Step 11: Write memory ──────────────────────────────────────────
        state.update(write_case_memory(state, trail))

        log.info(f"Investigation complete: {case_id}")
        best = state.get("recommended_action")
        if best:
            log.info(f"  Action: {best.action}")
            log.info(f"  Approval: {best.approval_route}")
        log.info(f"{'='*60}")

        return InvestigationState(**state)
