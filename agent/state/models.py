"""
agent/state/models.py — All Pydantic models used in InvestigationState.

Every field has a documented purpose.
No field exists purely for decoration.
"""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field


# ── Enums ─────────────────────────────────────────────────────────────────────

class InvestigationStatus(str, Enum):
    """Lifecycle status of an investigation."""
    PENDING = "pending"
    PLANNING = "planning"
    INVESTIGATING = "investigating"
    ANALYZING = "analyzing"
    INSUFFICIENT_EVIDENCE = "insufficient_evidence"
    REQUESTING_EVIDENCE = "requesting_evidence"
    REASSESSING = "reassessing"
    POLICY_EVALUATION = "policy_evaluation"
    AWAITING_APPROVAL = "awaiting_approval"
    COMPLETE = "complete"
    ERROR = "error"


class HypothesisStatus(str, Enum):
    """Status of a fraud hypothesis during investigation."""
    ACTIVE = "active"              # Under consideration
    STRENGTHENED = "strengthened"  # Evidence supports this hypothesis
    WEAKENED = "weakened"          # Evidence contradicts this hypothesis
    REJECTED = "rejected"          # Sufficient evidence against
    CONFIRMED = "confirmed"        # Sufficient evidence for (rare — high bar)


class UncertaintyLevel(str, Enum):
    """Qualitative uncertainty level."""
    LOW = "low"        # Evidence is complete, consistent, and sufficient
    MEDIUM = "medium"  # Some missing evidence or minor conflicts
    HIGH = "high"      # Significant gaps, conflicts, or missing data


class SufficiencyLevel(str, Enum):
    """Evidence sufficiency level."""
    INSUFFICIENT = "insufficient"  # Not enough to act
    PARTIAL = "partial"            # Enough to recommend non-disruptive actions
    SUFFICIENT = "sufficient"      # Enough to recommend any permitted action


class EvidenceSourceType(str, Enum):
    """Where the evidence came from."""
    MCP_GET_CASE = "get_case"
    MCP_CUSTOMER_HISTORY = "get_customer_history"
    MCP_TRANSACTION_CONTEXT = "get_transaction_context"
    MCP_CONNECTED_ENTITIES = "find_connected_entities"
    MCP_PRIOR_CASES = "find_prior_cases"
    MCP_TEMPORAL_PATTERNS = "detect_temporal_patterns"
    MCP_EXPOSURE = "calculate_exposure"
    MCP_SHARED_DEVICES = "find_shared_devices"
    INJECTED = "injected"         # Manually injected evidence (for testing/simulation)
    DERIVED = "derived"           # Derived from other evidence (must cite sources)


class ActionType(str, Enum):
    """Possible investigation actions. Derived from closed_cases_history actions_taken values."""
    REQUEST_MORE_EVIDENCE = "REQUEST_MORE_EVIDENCE"
    MONITOR = "MONITOR"
    VERIFY_WITH_CUSTOMER = "VERIFY_WITH_CUSTOMER"
    CREATE_CASE = "CREATE_CASE"
    BLOCK_CARD = "BLOCK_CARD"
    BLOCK_ACCOUNT = "BLOCK_ACCOUNT"
    FILE_REPORT = "FILE_REPORT"
    CLOSE_NO_FRAUD = "CLOSE_NO_FRAUD"
    ESCALATE = "ESCALATE"


class ApprovalRoute(str, Enum):
    """Who must approve the recommended action."""
    NONE = "none"              # Auto-executable
    FRAUD_ANALYST = "fraud_analyst"    # Standard review
    SENIOR_ANALYST = "senior_analyst"  # High-impact actions
    AUTO_BLOCKED = "auto_blocked"      # Policy prevents this action entirely


class EvidenceRequestType(str, Enum):
    """Types of additional evidence that can be requested."""
    VERIFY_WITH_CUSTOMER = "VERIFY_WITH_CUSTOMER"
    ANALYST_REVIEW = "ANALYST_REVIEW"
    ADDITIONAL_GRAPH_QUERY = "ADDITIONAL_GRAPH_QUERY"


class EvidenceRequestStatus(str, Enum):
    """Status of an evidence request."""
    PENDING = "pending"
    RECEIVED = "received"
    EXPIRED = "expired"


class FraudPattern(str, Enum):
    """
    Fraud patterns from fraud_patterns.csv and closed_cases_history.csv.
    These are the ONLY official patterns — do not invent new ones.
    """
    ACCOUNT_TAKEOVER = "account_takeover"
    CARD_NOT_PRESENT_FRAUD = "card_not_present_fraud"
    CARD_NOT_PRESENT_NEW_DEVICE = "card_not_present_new_device"
    CARD_TESTING = "card_testing"
    OUT_OF_REGION_USE = "out_of_region_use"
    UNDOCUMENTED = "undocumented"
    NONE = "none"  # Cleared case — no fraud pattern


# ── Evidence models ───────────────────────────────────────────────────────────

class Evidence(BaseModel):
    """
    A single piece of evidence with full provenance.

    Every evidence item must be traceable to its source tool call.
    The agent may NEVER fabricate evidence — every claim must have
    a source_type and source_id pointing to an actual tool result.
    """
    evidence_id: str = Field(description="Unique ID, e.g. EV-001")
    source_type: EvidenceSourceType = Field(description="Which MCP tool produced this")
    source_id: str = Field(description="Transaction ID, customer ID, or case ID this came from")
    claim: str = Field(description="Human-readable factual claim from the evidence")
    value: Any = Field(default=None, description="Machine-readable value (amount, count, flag, etc.)")
    timestamp: str = Field(default="", description="When the evidence was retrieved")
    relevance: str = Field(default="", description="Why this is relevant to the investigation")
    supports: list[str] = Field(
        default_factory=list,
        description="List of hypothesis_ids this evidence supports"
    )
    contradicts: list[str] = Field(
        default_factory=list,
        description="List of hypothesis_ids this evidence contradicts"
    )
    confidence: float = Field(
        default=1.0,
        ge=0.0, le=1.0,
        description="Confidence in this evidence (1.0 = directly observed fact, <1.0 = inferred)"
    )
    retrieval_method: str = Field(
        default="",
        description="Exact tool name used, e.g. 'get_transaction_context'"
    )

    model_config = {"frozen": False}


class Hypothesis(BaseModel):
    """
    A fraud hypothesis being tested during investigation.

    Only patterns from fraud_patterns.csv are used as official hypotheses.
    Additional investigative hypotheses (e.g. 'legitimate_activity') are permitted.
    """
    hypothesis_id: str = Field(description="Unique ID, e.g. HYP-001")
    name: str = Field(description="Short name, e.g. 'card_testing'")
    description: str = Field(description="What this hypothesis means in context")
    status: HypothesisStatus = Field(default=HypothesisStatus.ACTIVE)
    supporting_evidence_ids: list[str] = Field(
        default_factory=list,
        description="Evidence IDs that support this hypothesis"
    )
    contradictory_evidence_ids: list[str] = Field(
        default_factory=list,
        description="Evidence IDs that contradict this hypothesis"
    )
    confidence: float = Field(
        default=0.5,
        ge=0.0, le=1.0,
        description="Probability this hypothesis is correct given current evidence"
    )
    reasoning: str = Field(
        default="",
        description="Why this hypothesis has its current status and confidence"
    )
    last_updated: str = Field(default="", description="ISO timestamp of last update")

    model_config = {"frozen": False}


class EvidenceRequest(BaseModel):
    """
    A structured request for additional evidence.

    Created when evidence is insufficient to make a decision.
    Must be resolved before high-impact actions can be recommended.
    """
    request_id: str = Field(description="Unique ID, e.g. REQ-001")
    request_type: EvidenceRequestType
    reason: str = Field(description="Why this evidence is needed")
    required_for_decision: bool = Field(
        default=True,
        description="Whether this blocks the final decision"
    )
    status: EvidenceRequestStatus = Field(default=EvidenceRequestStatus.PENDING)
    created_at: str = Field(default="")
    resolved_at: str = Field(default="")
    response: dict[str, Any] = Field(
        default_factory=dict,
        description="The evidence received in response to this request"
    )

    model_config = {"frozen": False}


class SufficiencyResult(BaseModel):
    """Output from the Evidence Sufficiency Engine."""
    sufficient: bool
    level: SufficiencyLevel
    supporting_count: int
    contradictory_count: int
    missing_evidence: list[str] = Field(
        default_factory=list,
        description="Descriptions of what evidence is missing"
    )
    satisfied_categories: list[str] = Field(default_factory=list)
    unsatisfied_categories: list[str] = Field(default_factory=list)
    reason: str = Field(description="Human-readable explanation of the sufficiency assessment")

    model_config = {"frozen": False}


class UncertaintyAssessment(BaseModel):
    """Output from the Uncertainty Engine."""
    level: UncertaintyLevel
    known: list[str] = Field(default_factory=list, description="What is known with confidence")
    unknown: list[str] = Field(default_factory=list, description="What is not known")
    conflicts: list[str] = Field(default_factory=list, description="Conflicting evidence")
    missing: list[str] = Field(default_factory=list, description="What evidence is absent")
    reduction_steps: list[str] = Field(
        default_factory=list,
        description="What would reduce uncertainty"
    )
    reason: str = Field(description="Summary explanation of uncertainty level")

    model_config = {"frozen": False}


class PolicyDecision(BaseModel):
    """Result from the deterministic policy engine."""
    action: ActionType
    allowed: bool
    reason: str
    approval_required: bool = False
    approval_route: ApprovalRoute = ApprovalRoute.NONE
    policy_rules_applied: list[str] = Field(default_factory=list)

    model_config = {"frozen": False}


class CandidateAction(BaseModel):
    """
    A possible action the agent could recommend.
    Generated by the LLM, validated by the policy engine.
    """
    action: ActionType
    reason: str = Field(description="Why this action is appropriate")
    required_evidence: list[str] = Field(
        default_factory=list,
        description="Evidence IDs supporting this action"
    )
    policy_basis: str = Field(description="Which policy rule justifies this action")
    approval_required: bool = False
    approval_route: ApprovalRoute = ApprovalRoute.NONE
    execution_mode: str = Field(
        default="manual",
        description="auto (agent can execute) or manual (requires human)"
    )
    risk_level: str = Field(
        default="medium",
        description="low / medium / high impact"
    )

    model_config = {"frozen": False}


class ToolCall(BaseModel):
    """Record of a single MCP tool call."""
    call_id: str
    tool_name: str
    params: dict[str, Any]
    result: dict[str, Any] = Field(default_factory=dict)
    success: bool = True
    error: str = Field(default="")
    latency_ms: float = 0.0
    timestamp: str = Field(default="")

    model_config = {"frozen": False}


class TrailEvent(BaseModel):
    """A single event in the investigation audit trail."""
    event_id: str
    timestamp: str
    step_type: str  # CASE_CREATED, PLAN_CREATED, TOOL_CALLED, etc.
    description: str
    tool: str = Field(default="")
    inputs: dict[str, Any] = Field(default_factory=dict)
    outputs: dict[str, Any] = Field(default_factory=dict)
    reason: str = Field(default="")

    model_config = {"frozen": False}


class InvestigationPlan(BaseModel):
    """
    Structured investigation plan created at the start of each investigation.
    Determines which tools to call and why.
    """
    objective: str
    questions: list[str] = Field(description="Key questions to answer")
    planned_tools: list[str] = Field(description="Ordered list of tool names to call")
    trigger_analysis: str = Field(default="", description="Why this case was triggered")
    risk_assessment: str = Field(default="", description="Initial risk assessment from trigger")
    created_at: str = Field(default="")

    model_config = {"frozen": False}


class CaseMemory(BaseModel):
    """
    Persisted memory for a completed investigation.
    Used by future investigations when searching for similar prior cases.
    """
    case_id: str
    customer_id: str
    card_id: str
    transaction_id: str
    investigation_completed_at: str
    final_action: str
    outcome_description: str
    fraud_patterns_identified: list[str] = Field(default_factory=list)
    key_evidence_summary: str = Field(default="")
    connected_entities: list[str] = Field(default_factory=list)
    policy_decisions: list[str] = Field(default_factory=list)
    reasoning_summary: str = Field(default="")
    approved_by: str = Field(default="")

    model_config = {"frozen": False}


class FinalSummary(BaseModel):
    """
    The complete structured output of an investigation.
    Every factual claim must trace to an evidence ID.
    """
    case_id: str
    trigger: str
    investigation_objective: str
    customer_id: str
    transaction_id: str
    transaction_amount: float
    key_entities: list[str] = Field(default_factory=list)
    key_findings: list[str] = Field(description="Top findings, each citing evidence IDs")
    supporting_evidence_summary: str
    contradictory_evidence_summary: str
    identified_patterns: list[str] = Field(default_factory=list)
    hypotheses_summary: list[dict[str, Any]] = Field(default_factory=list)
    uncertainty_level: str
    uncertainty_reason: str
    evidence_sufficiency_level: str
    sufficiency_reason: str
    missing_evidence: list[str] = Field(default_factory=list)
    evidence_requests: list[str] = Field(default_factory=list)
    candidate_actions: list[str] = Field(default_factory=list)
    recommended_action: str
    policy_basis: str
    approval_route: str
    decision_reasoning: str
    investigation_trail_summary: list[str] = Field(default_factory=list)
    case_outcome: str
    memory_updated: bool = False
    completed_at: str = Field(default="")

    model_config = {"frozen": False}
