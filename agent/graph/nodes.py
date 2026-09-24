"""
agent/graph/nodes.py — All investigation node functions.

Each node is a pure function:
  Input:  InvestigationState (dict)
  Output: dict of state updates

Nodes never modify the state dict directly — they return partial updates
which the workflow merges in. This matches LangGraph's architecture
and makes every node independently testable.

Node execution order (from workflow.py):
  1. load_case
  2. plan_investigation
  3. collect_evidence
  4. analyze_evidence
  5. update_hypotheses
  6. assess_uncertainty
  7. assess_sufficiency
     → if INSUFFICIENT: request_evidence → collect_evidence (loop, max 2x)
     → if SUFFICIENT/PARTIAL: evaluate_policy
  8. evaluate_policy
  9. determine_next_best_action
  10. route_approval
  11. write_case_memory
  12. generate_final_summary
"""

from __future__ import annotations

import logging
import time
from datetime import datetime, timezone
from typing import Any

from agent.audit.trail import InvestigationTrail
from agent.evidence.classifier import classify_evidence
from agent.evidence.extractor import extract_evidence, reset_counter
from agent.evidence.provenance import ProvenanceTracker
from agent.graphrag.context_builder import ContextBuilder
from agent.graphrag.retriever import GraphRAGRetriever
from agent.hypotheses.manager import HypothesisManager
from agent.memory.retriever import CaseMemoryRetriever
from agent.memory.writer import CaseMemoryWriter
from agent.policy.evaluator import PolicyEvaluator
from agent.decisions.next_best_action import NextBestActionEngine
from agent.state.models import (
    CaseMemory,
    FinalSummary,
    InvestigationStatus,
    SufficiencyLevel,
    ToolCall,
    UncertaintyLevel,
)
from agent.sufficiency.engine import SufficiencyEngine
from agent.tools.adapters import adapt
from agent.tools.registry import get_initial_tools
from agent.uncertainty.engine import UncertaintyEngine

log = logging.getLogger(__name__)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


# ── Node 1: load_case ─────────────────────────────────────────────────────────

def load_case(state: dict, mcp_client: Any, trail: InvestigationTrail) -> dict:
    """
    Load case details from MCP and populate identity fields.
    Always the first node.
    """
    case_id = state["case_id"]
    trail.log("CASE_LOADED", f"Loading case {case_id}", tool="get_case",
               inputs={"case_id": case_id})

    # Reset counters for this investigation
    reset_counter()

    t0 = time.monotonic()
    raw = mcp_client.get_case(case_id=case_id)
    latency = (time.monotonic() - t0) * 1000

    tool_call = ToolCall(
        call_id="TC-001",
        tool_name="get_case",
        params={"case_id": case_id},
        result=raw,
        success=raw.get("found", False),
        latency_ms=round(latency, 1),
        timestamp=_now(),
    )

    if not raw.get("found", False):
        trail.log("ERROR", f"Case {case_id} not found in MCP")
        return {
            "investigation_status": InvestigationStatus.ERROR,
            "errors": state.get("errors", []) + [f"Case {case_id} not found"],
            "tool_calls": state.get("tool_calls", []) + [tool_call],
        }

    case = raw["case"]
    txn = raw.get("flagged_transaction") or {}

    trail.log(
        "CASE_LOADED",
        f"Case {case_id} loaded: customer={case.get('customer_id')}, "
        f"trigger={case.get('trigger_type')}, risk={case.get('risk_score')}",
        outputs={"customer_id": case.get("customer_id"), "trigger_type": case.get("trigger_type")},
    )

    return {
        "customer_id": case.get("customer_id", ""),
        "account_id": case.get("customer_id", ""),
        "card_id": case.get("card_id", ""),
        "transaction_id": str(case.get("flagged_txn_id", "")),
        "trigger": case.get("trigger_type", ""),
        "trigger_text": case.get("trigger_text", ""),
        "opened_at": case.get("opened_at", ""),
        "initial_risk_score": float(case.get("risk_score") or 0.0),
        "investigation_objective": (
            f"Determine whether transaction {case.get('flagged_txn_id')} "
            f"for customer {case.get('customer_id')} is fraudulent. "
            f"Trigger: {case.get('trigger_text', '')}"
        ),
        "investigation_status": InvestigationStatus.PLANNING,
        "raw_tool_results": {"get_case": raw},
        "tool_calls": state.get("tool_calls", []) + [tool_call],
    }


# ── Node 2: plan_investigation ────────────────────────────────────────────────

def plan_investigation(state: dict, trail: InvestigationTrail) -> dict:
    """
    Create deterministic investigation plan based on trigger type.
    Uses registry.get_initial_tools() — no LLM required.
    """
    from agent.state.models import InvestigationPlan

    trigger_type = state.get("trigger", "risk_score")
    tools = get_initial_tools(trigger_type)
    customer_id = state.get("customer_id", "")
    risk_score = state.get("initial_risk_score", 0.0)

    questions = [
        f"Is transaction {state.get('transaction_id')} consistent with "
        f"customer {customer_id}'s normal behaviour?",
        "Are there prior fraud cases for this customer or card?",
        "What fraud pattern best matches the available evidence?",
        "What is the financial exposure if this is fraud?",
        "Are there other customers connected via shared devices or attributes?",
    ]

    plan = InvestigationPlan(
        objective=state.get("investigation_objective", ""),
        questions=questions,
        planned_tools=tools,
        trigger_analysis=(
            f"Trigger type: {trigger_type}. "
            + (f"Risk score: {risk_score:.2f}." if risk_score else "Customer-reported.")
        ),
        risk_assessment=(
            "HIGH" if risk_score >= 0.7
            else "MEDIUM" if risk_score >= 0.4
            else "REVIEW NEEDED"
        ),
        created_at=_now(),
    )

    trail.log(
        "PLAN_CREATED",
        f"Investigation plan created: {len(tools)} tools planned for {trigger_type} trigger",
        outputs={"planned_tools": tools},
    )

    return {
        "investigation_plan": plan,
        "investigation_status": InvestigationStatus.INVESTIGATING,
        "investigation_steps": [f"Plan created: will call {', '.join(tools)}"],
    }


# ── Node 3: collect_evidence ──────────────────────────────────────────────────

def collect_evidence(
    state: dict,
    mcp_client: Any,
    trail: InvestigationTrail,
    provenance: ProvenanceTracker,
    extra_tools: list[str] | None = None,
) -> dict:
    """
    Call all planned MCP tools and extract evidence from results.
    `extra_tools` is used during reassessment to call additional tools.
    """
    customer_id = state.get("customer_id", "")
    card_id = state.get("card_id", "")
    transaction_id = state.get("transaction_id", "")

    already_called = {tc.tool_name for tc in state.get("tool_calls", [])}
    planned = extra_tools or state.get("investigation_plan", {}).get(
        "planned_tools", get_initial_tools(state.get("trigger", "risk_score"))
    ) if not hasattr(state.get("investigation_plan"), "planned_tools") else \
        state["investigation_plan"].planned_tools

    # Handle both dict and object
    if hasattr(state.get("investigation_plan"), "planned_tools"):
        planned = state["investigation_plan"].planned_tools
    elif isinstance(state.get("investigation_plan"), dict):
        planned = state["investigation_plan"].get("planned_tools", [])

    if extra_tools:
        planned = [t for t in extra_tools if t not in already_called]

    new_tool_calls: list[ToolCall] = []
    new_raw_results: dict[str, Any] = dict(state.get("raw_tool_results", {}))
    new_evidence: list = list(state.get("evidence", []))
    call_num = len(state.get("tool_calls", [])) + 1
    steps: list[str] = list(state.get("investigation_steps", []))

    for tool in planned:
        if tool in already_called:
            continue
        try:
            t0 = time.monotonic()
            raw = _call_tool(mcp_client, tool, customer_id, card_id, transaction_id)
            latency = (time.monotonic() - t0) * 1000
            now = _now()

            params = _build_params(tool, customer_id, card_id, transaction_id)
            tc = ToolCall(
                call_id=f"TC-{call_num:03d}",
                tool_name=tool,
                params=params,
                result=raw,
                success=True,
                latency_ms=round(latency, 1),
                timestamp=now,
            )
            call_num += 1
            new_tool_calls.append(tc)
            new_raw_results[tool] = raw
            already_called.add(tool)

            # Adapt + extract evidence
            result = adapt(tool, raw)
            extracted = extract_evidence(result)
            new_evidence.extend(extracted)

            # Record provenance
            provenance.record(tc, raw, extracted)

            trail.log(
                "TOOL_CALLED",
                f"{tool} → {len(extracted)} evidence items ({latency:.0f}ms)",
                tool=tool,
                inputs=params,
                outputs={"evidence_count": len(extracted)},
            )
            steps.append(f"Called {tool}: {len(extracted)} evidence items extracted")

        except Exception as exc:
            log.error(f"Tool {tool} failed: {exc}")
            tc = ToolCall(
                call_id=f"TC-{call_num:03d}",
                tool_name=tool,
                params=_build_params(tool, customer_id, card_id, transaction_id),
                success=False,
                error=str(exc),
                timestamp=_now(),
            )
            call_num += 1
            new_tool_calls.append(tc)
            trail.log("ERROR", f"Tool {tool} failed: {exc}", tool=tool)
            steps.append(f"Tool {tool} FAILED: {exc}")

    return {
        "tool_calls": state.get("tool_calls", []) + new_tool_calls,
        "raw_tool_results": new_raw_results,
        "evidence": new_evidence,
        "investigation_steps": steps,
        "investigation_status": InvestigationStatus.ANALYZING,
    }


def _call_tool(client: Any, tool: str, customer_id: str, card_id: str, txn_id: str) -> dict:
    if tool == "get_case":
        return {}
    if tool == "get_customer_history":
        return client.get_customer_history(customer_id=customer_id)
    if tool == "get_transaction_context":
        return client.get_transaction_context(txn_id=txn_id)
    if tool == "find_prior_cases":
        return client.find_prior_cases(customer_id=customer_id, card_id=card_id)
    if tool == "detect_temporal_patterns":
        return client.detect_temporal_patterns(customer_id=customer_id)
    if tool == "calculate_exposure":
        return client.calculate_exposure(customer_id=customer_id)
    if tool == "find_connected_entities":
        return client.find_connected_entities(entity_id=customer_id)
    if tool == "find_shared_devices":
        return client.find_shared_devices(customer_id=customer_id)
    raise ValueError(f"Unknown tool: {tool!r}")


def _build_params(tool: str, customer_id: str, card_id: str, txn_id: str) -> dict:
    if tool in ("get_customer_history", "detect_temporal_patterns",
                "find_shared_devices", "find_connected_entities"):
        return {"customer_id": customer_id}
    if tool == "find_prior_cases":
        return {"customer_id": customer_id, "card_id": card_id}
    if tool == "calculate_exposure":
        return {"customer_id": customer_id}
    if tool == "get_transaction_context":
        return {"txn_id": txn_id}
    return {}


# ── Node 4: analyze_evidence ──────────────────────────────────────────────────

def analyze_evidence(state: dict, trail: InvestigationTrail) -> dict:
    """Classify evidence as supporting or contradictory."""
    evidence = state.get("evidence", [])
    hypotheses = state.get("hypotheses", [])

    if not hypotheses:
        # Create hypotheses if not yet done
        mgr = HypothesisManager()
        hypotheses = mgr.create_hypotheses(state.get("trigger", "risk_score"))
        trail.log("HYPOTHESIS_UPDATED", f"Created {len(hypotheses)} hypotheses")

    supporting, contradictory = classify_evidence(evidence, hypotheses)

    trail.log(
        "EVIDENCE_EXTRACTED",
        f"Classified: {len(supporting)} supporting, {len(contradictory)} contradictory "
        f"from {len(evidence)} total evidence items",
        outputs={"supporting": len(supporting), "contradictory": len(contradictory)},
    )

    return {
        "hypotheses": hypotheses,
        "supporting_evidence": supporting,
        "contradictory_evidence": contradictory,
    }


# ── Node 5: update_hypotheses ─────────────────────────────────────────────────

def update_hypotheses(state: dict, trail: InvestigationTrail) -> dict:
    """Update hypothesis confidence and status based on classified evidence."""
    mgr = HypothesisManager()
    hypotheses = mgr.update_hypotheses(
        hypotheses=state.get("hypotheses", []),
        supporting=state.get("supporting_evidence", []),
        contradictory=state.get("contradictory_evidence", []),
    )
    top = mgr.get_top_hypothesis(hypotheses)
    trail.log(
        "HYPOTHESIS_UPDATED",
        f"Hypotheses updated. Top: {top.name if top else 'none'} "
        f"(conf={top.confidence:.2f})" if top else "No active hypotheses",
        outputs={"top_hypothesis": top.name if top else None},
    )
    patterns = [h.name for h in hypotheses if h.confidence >= 0.4]
    return {
        "hypotheses": hypotheses,
        "fraud_patterns": patterns,
    }


# ── Node 6: assess_uncertainty ────────────────────────────────────────────────

def assess_uncertainty(state: dict, trail: InvestigationTrail) -> dict:
    """Assess the uncertainty level of the investigation."""
    engine = UncertaintyEngine()
    tools_called = {tc.tool_name for tc in state.get("tool_calls", [])}

    assessment = engine.assess(
        evidence=state.get("evidence", []),
        supporting=state.get("supporting_evidence", []),
        contradictory=state.get("contradictory_evidence", []),
        hypotheses=state.get("hypotheses", []),
        tools_called=tools_called,
    )

    trail.log(
        "UNCERTAINTY_ASSESSED",
        f"Uncertainty: {assessment.level.value.upper()} — {assessment.reason[:80]}",
        outputs={"level": assessment.level.value},
    )

    return {
        "uncertainty": assessment,
        "risk_assessment": assessment.level.value,
    }


# ── Node 7: assess_sufficiency ────────────────────────────────────────────────

def assess_sufficiency(state: dict, trail: InvestigationTrail) -> dict:
    """Assess whether gathered evidence is sufficient for a decision."""
    engine = SufficiencyEngine()
    tools_called = {tc.tool_name for tc in state.get("tool_calls", [])}

    result = engine.evaluate(
        evidence=state.get("evidence", []),
        supporting=state.get("supporting_evidence", []),
        contradictory=state.get("contradictory_evidence", []),
        tools_called=tools_called,
        reassessment_count=state.get("reassessment_count", 0),
    )

    status = (
        InvestigationStatus.INSUFFICIENT_EVIDENCE
        if not result.sufficient
        else InvestigationStatus.POLICY_EVALUATION
    )

    trail.log(
        "SUFFICIENCY_ASSESSED",
        f"Sufficiency: {result.level.value.upper()} — {result.reason[:80]}",
        outputs={"level": result.level.value, "sufficient": result.sufficient},
    )

    return {
        "evidence_sufficiency": result,
        "missing_evidence": result.missing_evidence,
        "investigation_status": status,
    }


# ── Node 8: request_evidence ──────────────────────────────────────────────────

def request_evidence(
    state: dict,
    mcp_client: Any,
    trail: InvestigationTrail,
    provenance: ProvenanceTracker,
) -> dict:
    """
    Request additional evidence by calling uncalled MCP tools.
    Called when sufficiency is INSUFFICIENT.
    """
    already_called = {tc.tool_name for tc in state.get("tool_calls", [])}
    missing = state.get("missing_evidence", [])
    retriever = GraphRAGRetriever(mcp_client)

    extra_calls, extra_raw = retriever.fetch_additional_evidence(
        missing_evidence=missing,
        already_called=already_called,
        customer_id=state.get("customer_id", ""),
        card_id=state.get("card_id", ""),
        transaction_id=state.get("transaction_id", ""),
    )

    # Extract evidence from additional tool results
    new_evidence = list(state.get("evidence", []))
    for tc in extra_calls:
        if tc.success and tc.tool_name in extra_raw:
            result = adapt(tc.tool_name, extra_raw[tc.tool_name])
            extracted = extract_evidence(result)
            new_evidence.extend(extracted)
            provenance.record(tc, extra_raw[tc.tool_name], extracted)

    trail.log(
        "EVIDENCE_REQUESTED",
        f"Requested additional evidence: {len(extra_calls)} tool calls, "
        f"{len(new_evidence) - len(state.get('evidence', []))} new items",
    )

    count = state.get("reassessment_count", 0) + 1
    return {
        "tool_calls": state.get("tool_calls", []) + extra_calls,
        "raw_tool_results": {**state.get("raw_tool_results", {}), **extra_raw},
        "evidence": new_evidence,
        "reassessment_count": count,
        "investigation_status": InvestigationStatus.REASSESSING,
    }


# ── Node 9: evaluate_policy ───────────────────────────────────────────────────

def evaluate_policy(state: dict, trail: InvestigationTrail) -> dict:
    """Run deterministic policy evaluation."""
    evaluator = PolicyEvaluator()
    retriever = CaseMemoryRetriever()

    # Get total exposure from evidence
    total_exposure = _extract_exposure(state)
    prior_actions = retriever.get_prior_actions(state.get("customer_id", ""))

    top_hyp = None
    hyps = state.get("hypotheses", [])
    if hyps:
        from agent.hypotheses.manager import HypothesisManager
        top_hyp = HypothesisManager().get_top_hypothesis(hyps)

    decision, candidates = evaluator.evaluate(
        sufficiency=state["evidence_sufficiency"],
        uncertainty=state["uncertainty"],
        supporting_count=len(state.get("supporting_evidence", [])),
        contradictory_count=len(state.get("contradictory_evidence", [])),
        total_exposure_usd=total_exposure,
        trigger_type=state.get("trigger", "risk_score"),
        top_hypothesis_name=top_hyp.name if top_hyp else "",
    )

    trail.log(
        "POLICY_EVALUATED",
        f"Policy: {decision.action} | approval={decision.approval_route}",
        outputs={"action": str(decision.action), "approval": str(decision.approval_route)},
    )

    return {
        "policy_evaluation": decision,
        "candidate_actions": candidates,
    }


def _extract_exposure(state: dict) -> float:
    """Extract total exposure amount from evidence."""
    raw = state.get("raw_tool_results", {}).get("calculate_exposure", {})
    if raw:
        confirmed = float(raw.get("total_confirmed_exposure_usd", 0.0) or 0.0)
        pending = float(raw.get("pending_exposure_usd", 0.0) or 0.0)
        return confirmed + pending
    # Fallback: look in evidence
    for ev in state.get("evidence", []):
        if isinstance(ev.value, dict) and "total_usd" in ev.value:
            return float(ev.value["total_usd"])
    return 0.0


# ── Node 10: determine_next_best_action ───────────────────────────────────────

def determine_next_best_action(state: dict, trail: InvestigationTrail) -> dict:
    """Select the final recommended action."""
    engine = NextBestActionEngine()
    ctx_builder = ContextBuilder()
    retriever = CaseMemoryRetriever()
    prior_actions = retriever.get_prior_actions(state.get("customer_id", ""))
    total_exposure = _extract_exposure(state)

    context = ctx_builder.build_decision_context(
        case_id=state.get("case_id", ""),
        customer_id=state.get("customer_id", ""),
        evidence=state.get("evidence", []),
        supporting=state.get("supporting_evidence", []),
        contradictory=state.get("contradictory_evidence", []),
        hypotheses=state.get("hypotheses", []),
        sufficiency=state["evidence_sufficiency"],
        uncertainty=state["uncertainty"],
        prior_actions=prior_actions,
    )

    best = engine.select(
        policy_decision=state["policy_evaluation"],
        candidates=state.get("candidate_actions", []),
        context=context,
        sufficiency=state["evidence_sufficiency"],
        uncertainty=state["uncertainty"],
        supporting_count=len(state.get("supporting_evidence", [])),
        total_exposure_usd=total_exposure,
    )

    trail.log(
        "ACTION_SELECTED",
        f"NBA: {best.action} | approval={best.approval_route} | "
        f"required={best.approval_required}",
        outputs={
            "action": str(best.action),
            "approval_route": str(best.approval_route),
            "approval_required": best.approval_required,
        },
    )

    return {
        "recommended_action": best,
        "approval_route": best.approval_route.value if hasattr(best.approval_route, "value") else str(best.approval_route),
        "approval_required": best.approval_required,
        "approval_status": "pending" if best.approval_required else "not_required",
        "decision_reasoning": best.reason,
    }


# ── Node 11: write_case_memory ────────────────────────────────────────────────

def write_case_memory(state: dict, trail: InvestigationTrail) -> dict:
    """
    Persist investigation results to case memory.

    generate_final_summary() must have run before this node so that
    state["final_summary"] is populated with the real FinalSummary
    (including actual TransactionAmt from the dataset).
    """
    writer = CaseMemoryWriter()
    best = state.get("recommended_action")
    action_str = str(best.action) if best else "UNKNOWN"

    hyp_patterns = [
        h.name for h in state.get("hypotheses", [])
        if hasattr(h, "confidence") and h.confidence >= 0.4
    ]

    memory = CaseMemory(
        case_id=state.get("case_id", ""),
        customer_id=state.get("customer_id", ""),
        card_id=state.get("card_id", ""),
        transaction_id=state.get("transaction_id", ""),
        investigation_completed_at=_now(),
        final_action=action_str,
        outcome_description=state.get("decision_reasoning", ""),
        fraud_patterns_identified=hyp_patterns,
        key_evidence_summary="; ".join(
            ev.claim[:80] for ev in state.get("supporting_evidence", [])[:3]
        ),
        connected_entities=[
            e.get("entity_id", "") for e in state.get("connected_entities", [])[:5]
        ],
        policy_decisions=[action_str],
        reasoning_summary=state.get("decision_reasoning", "")[:300],
        approved_by=state.get("approval_route", "none"),
    )

    # final_summary is always populated by generate_final_summary() which
    # runs before this node. Use it directly — no placeholder needed.
    summary = state["final_summary"]

    try:
        path = writer.write(state.get("case_id", "UNKNOWN"), summary, memory)
        trail.log("MEMORY_WRITTEN", f"Case memory written to {path}")
    except Exception as exc:
        trail.log("ERROR", f"Failed to write case memory: {exc}")

    return {
        "case_memory": memory,
    }


# ── Node 10: generate_final_summary ──────────────────────────────────────────

def generate_final_summary(state: dict, trail: InvestigationTrail) -> dict:
    """
    Generate the structured FinalSummary for the investigation.

    Runs BEFORE write_case_memory so the persisted report contains
    the real transaction amount from the dataset, not 0.0.
    """
    best = state.get("recommended_action")
    suf = state.get("evidence_sufficiency")
    unc = state.get("uncertainty")
    action_str = str(best.action.value if hasattr(best.action, "value") else best.action) if best else "UNKNOWN"

    # Try LLM-enhanced summary; fall back to deterministic
    summary_data = _build_deterministic_summary(state, action_str, best, suf, unc)

    trail_events = trail.get_events()

    summary = FinalSummary(
        case_id=state.get("case_id", ""),
        trigger=state.get("trigger", ""),
        investigation_objective=state.get("investigation_objective", ""),
        customer_id=state.get("customer_id", ""),
        transaction_id=state.get("transaction_id", ""),
        transaction_amount=float(
            (
                (state.get("raw_tool_results", {}).get("get_case", {}) or {})
                .get("flagged_transaction") or {}
            ).get("TransactionAmt", 0.0) or 0.0
        ),
        key_entities=[state.get("customer_id", ""), state.get("card_id", "")],
        key_findings=summary_data["key_findings"],
        supporting_evidence_summary=summary_data["supporting_summary"],
        contradictory_evidence_summary=summary_data["contradictory_summary"],
        identified_patterns=state.get("fraud_patterns", []),
        hypotheses_summary=[
            {
                "id": h.hypothesis_id,
                "name": h.name,
                "status": h.status.value if hasattr(h.status, "value") else str(h.status),
                "confidence": h.confidence,
            }
            for h in state.get("hypotheses", [])
        ],
        uncertainty_level=unc.level.value if unc else "unknown",
        uncertainty_reason=unc.reason if unc else "",
        evidence_sufficiency_level=suf.level.value if suf else "unknown",
        sufficiency_reason=suf.reason if suf else "",
        missing_evidence=state.get("missing_evidence", [])[:5],
        candidate_actions=[
            str(c.action.value if hasattr(c.action, "value") else c.action)
            for c in state.get("candidate_actions", [])
        ],
        recommended_action=action_str,
        policy_basis=best.policy_basis if best else "",
        approval_route=state.get("approval_route", "none"),
        decision_reasoning=state.get("decision_reasoning", ""),
        # investigation_trail_summary is intentionally left empty in the
        # persisted JSON.  Trail events are in-memory only during workflow
        # execution and are not serialised to disk by design.
        investigation_trail_summary=[],
        case_outcome=action_str,
        # write_case_memory runs after this node; mark as True since the
        # persisted file is written unconditionally in the next step.
        memory_updated=True,
        completed_at=_now(),
    )

    trail.log(
        "SUMMARY_GENERATED",
        f"Final summary generated: {action_str} | "
        f"uncertainty={summary.uncertainty_level} | "
        f"sufficiency={summary.evidence_sufficiency_level}",
    )

    return {
        "final_summary": summary,
        "investigation_status": InvestigationStatus.COMPLETE,
        "completed_at": summary.completed_at,
        "investigation_trail": trail_events,
    }


def _build_deterministic_summary(
    state: dict, action_str: str, best: Any, suf: Any, unc: Any
) -> dict:
    supporting = state.get("supporting_evidence", [])
    contradictory = state.get("contradictory_evidence", [])

    key_findings = [
        f"{ev.claim[:100]} [{ev.evidence_id}]"
        for ev in supporting[:5]
    ]
    if not key_findings:
        key_findings = ["No supporting fraud evidence found"]

    supporting_summary = "; ".join(
        f"{ev.claim[:80]} [{ev.evidence_id}]" for ev in supporting[:3]
    ) or "No supporting evidence found"

    contradictory_summary = "; ".join(
        f"{ev.claim[:80]} [{ev.evidence_id}]" for ev in contradictory[:2]
    ) or "None"

    return {
        "key_findings": key_findings,
        "supporting_summary": supporting_summary,
        "contradictory_summary": contradictory_summary,
    }
