"""
agent/state/state.py — InvestigationState for LangGraph.

The state is the single source of truth throughout the investigation.
Every node reads from and writes to this state.
LangGraph requires state to be a TypedDict or dataclass for the StateGraph.
"""

from __future__ import annotations

from typing import Annotated, Any
from typing_extensions import TypedDict

from langgraph.graph.message import add_messages

from agent.state.models import (
    CandidateAction,
    CaseMemory,
    EvidenceRequest,
    Evidence,
    FinalSummary,
    Hypothesis,
    InvestigationPlan,
    InvestigationStatus,
    PolicyDecision,
    SufficiencyResult,
    ToolCall,
    TrailEvent,
    UncertaintyAssessment,
)


class InvestigationState(TypedDict, total=False):
    """
    Complete state for a fraud investigation.

    Fields are grouped by concern:
    - Identity: what case/customer/transaction we're investigating
    - Planning: what the investigation plan looks like
    - Execution: tool calls made and results
    - Evidence: normalized evidence items
    - Hypotheses: fraud pattern hypotheses
    - Assessment: uncertainty and sufficiency
    - Evidence requests: requests for additional evidence
    - Policy: policy evaluation results
    - Actions: candidate and recommended actions
    - Memory/output: case memory and final summary
    - Meta: errors, timestamps, debug info
    """

    # ── Identity ─────────────────────────────────────────────────────────
    case_id: str
    trigger: str               # e.g. "risk_score:0.61" or "customer_report"
    trigger_text: str          # Full trigger description from case_pack
    customer_id: str
    account_id: str            # Same as customer_id (alias for clarity)
    card_id: str
    transaction_id: str        # Flagged transaction ID
    opened_at: str             # When the case was opened

    # ── Investigation objective ───────────────────────────────────────────
    investigation_objective: str  # What we're trying to determine

    # ── Status ────────────────────────────────────────────────────────────
    investigation_status: InvestigationStatus

    # ── Planning ─────────────────────────────────────────────────────────
    investigation_plan: InvestigationPlan
    investigation_steps: list[str]  # Human-readable step log

    # ── Tool execution ────────────────────────────────────────────────────
    tool_calls: list[ToolCall]
    raw_tool_results: dict[str, Any]  # tool_name → raw result dict

    # ── Evidence ──────────────────────────────────────────────────────────
    evidence: list[Evidence]
    supporting_evidence: list[Evidence]      # Evidence that supports fraud
    contradictory_evidence: list[Evidence]   # Evidence against fraud
    missing_evidence: list[str]              # Descriptions of absent evidence

    # ── Hypotheses ────────────────────────────────────────────────────────
    hypotheses: list[Hypothesis]
    fraud_patterns: list[str]         # Patterns identified so far

    # ── Entity relationships ───────────────────────────────────────────────
    connected_entities: list[dict[str, Any]]  # From find_connected_entities
    prior_cases: list[dict[str, Any]]          # From find_prior_cases
    shared_devices: list[dict[str, Any]]       # From find_shared_devices

    # ── Risk ──────────────────────────────────────────────────────────────
    risk_assessment: str
    initial_risk_score: float  # From case_pack

    # ── Assessment ────────────────────────────────────────────────────────
    uncertainty: UncertaintyAssessment
    evidence_sufficiency: SufficiencyResult

    # ── Evidence requests ─────────────────────────────────────────────────
    requested_evidence: list[EvidenceRequest]
    received_evidence: list[Evidence]  # Evidence received in response to requests

    # ── Policy ────────────────────────────────────────────────────────────
    policy_evaluation: PolicyDecision

    # ── Actions ───────────────────────────────────────────────────────────
    candidate_actions: list[CandidateAction]
    recommended_action: CandidateAction

    # ── Approval ──────────────────────────────────────────────────────────
    approval_route: str       # none / fraud_analyst / senior_analyst
    approval_required: bool
    approval_status: str      # pending / approved / rejected / not_required

    # ── Decision ──────────────────────────────────────────────────────────
    decision_reasoning: str   # Full explanation of the final decision

    # ── Memory ────────────────────────────────────────────────────────────
    case_memory: CaseMemory

    # ── Final output ──────────────────────────────────────────────────────
    final_summary: FinalSummary

    # ── Audit trail ───────────────────────────────────────────────────────
    investigation_trail: list[TrailEvent]

    # ── Meta ──────────────────────────────────────────────────────────────
    errors: list[str]
    reassessment_count: int   # How many times we've reassessed
    debug_mode: bool
    started_at: str
    completed_at: str

    # ── LangGraph messages (for LLM communication within nodes) ───────────
    # Not used as the primary state — just for LLM tool-calling within nodes
    messages: Annotated[list, add_messages]


def create_initial_state(case_id: str, debug_mode: bool = False) -> InvestigationState:
    """
    Create a blank initial state for a new investigation.
    The load_case node will populate the identity fields.
    """
    from datetime import datetime, timezone
    now = datetime.now(timezone.utc).isoformat()

    return InvestigationState(
        case_id=case_id,
        trigger="",
        trigger_text="",
        customer_id="",
        account_id="",
        card_id="",
        transaction_id="",
        opened_at="",
        investigation_objective="",
        investigation_status=InvestigationStatus.PENDING,
        investigation_plan=InvestigationPlan(
            objective="",
            questions=[],
            planned_tools=[],
        ),
        investigation_steps=[],
        tool_calls=[],
        raw_tool_results={},
        evidence=[],
        supporting_evidence=[],
        contradictory_evidence=[],
        missing_evidence=[],
        hypotheses=[],
        fraud_patterns=[],
        connected_entities=[],
        prior_cases=[],
        shared_devices=[],
        risk_assessment="",
        initial_risk_score=0.0,
        requested_evidence=[],
        received_evidence=[],
        candidate_actions=[],
        approval_route="none",
        approval_required=False,
        approval_status="not_required",
        decision_reasoning="",
        investigation_trail=[],
        errors=[],
        reassessment_count=0,
        debug_mode=debug_mode,
        started_at=now,
        completed_at="",
        messages=[],
    )
