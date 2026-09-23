"""
agent/api/routes.py — FastAPI routes for the investigation agent.

Exposes:
  POST /investigate/{case_id}  — Run investigation for one case
  POST /investigate/batch      — Run investigations for multiple cases
  GET  /health                 — Health check
  GET  /cases                  — List all 20 open cases
"""

from __future__ import annotations

import logging
from typing import Any

from fastapi import FastAPI, HTTPException

from agent.api.schemas import (
    BatchRequest,
    BatchResponse,
    HypothesisSummary,
    InvestigateRequest,
    InvestigateResponse,
)
from agent.graph.workflow import InvestigationWorkflow
from agent.state.models import InvestigationStatus

log = logging.getLogger(__name__)

app = FastAPI(
    title="FraudGraph Investigation Agent",
    description="AI-powered fraud investigation using graph evidence",
    version="2.0.0",
)

# Single shared workflow instance (client is initialised once)
_workflow: InvestigationWorkflow | None = None


def _get_workflow() -> InvestigationWorkflow:
    global _workflow
    if _workflow is None:
        _workflow = InvestigationWorkflow()
    return _workflow


def _state_to_response(state: dict, case_id: str) -> InvestigateResponse:
    """Convert InvestigationState to API response."""
    summary = state.get("final_summary")
    best = state.get("recommended_action")
    suf = state.get("evidence_sufficiency")
    unc = state.get("uncertainty")

    error = ""
    if state.get("investigation_status") == InvestigationStatus.ERROR:
        error = "; ".join(state.get("errors", ["Unknown error"]))

    return InvestigateResponse(
        case_id=case_id,
        status=str(state.get("investigation_status", "unknown")),
        recommended_action=str(
            best.action.value if best and hasattr(best.action, "value") else "UNKNOWN"
        ),
        approval_required=bool(state.get("approval_required", False)),
        approval_route=str(state.get("approval_route", "none")),
        uncertainty_level=unc.level.value if unc else "unknown",
        sufficiency_level=suf.level.value if suf else "unknown",
        key_findings=(summary.key_findings if summary else []),
        identified_patterns=(summary.identified_patterns if summary else []),
        hypotheses=[
            HypothesisSummary(
                id=h.hypothesis_id,
                name=h.name,
                status=h.status.value if hasattr(h.status, "value") else str(h.status),
                confidence=h.confidence,
            )
            for h in state.get("hypotheses", [])
        ],
        decision_reasoning=str(state.get("decision_reasoning", "")),
        evidence_count=len(state.get("evidence", [])),
        supporting_count=len(state.get("supporting_evidence", [])),
        contradictory_count=len(state.get("contradictory_evidence", [])),
        completed_at=str(state.get("completed_at", "")),
        error=error,
    )


@app.get("/health")
def health() -> dict:
    return {"status": "ok", "agent": "FraudGraph Investigation Agent v2"}


@app.get("/cases")
def list_cases() -> dict:
    """List all 20 open investigation cases."""
    import csv
    from pathlib import Path
    path = Path(__file__).parent.parent.parent / "case_pack.csv"
    cases = []
    if path.exists():
        with open(path, encoding="utf-8") as f:
            for row in csv.DictReader(f):
                cases.append({
                    "case_id": row.get("case_id"),
                    "trigger_type": row.get("trigger_type"),
                    "customer_id": row.get("customer_id"),
                    "risk_score": row.get("risk_score"),
                    "opened_at": row.get("opened_at"),
                })
    return {"total": len(cases), "cases": cases}


@app.post("/investigate/{case_id}", response_model=InvestigateResponse)
def investigate(case_id: str) -> InvestigateResponse:
    """Run a full investigation for the given case ID."""
    try:
        workflow = _get_workflow()
        state = dict(workflow.run(case_id))
        return _state_to_response(state, case_id)
    except Exception as exc:
        log.error(f"Investigation failed for {case_id}: {exc}")
        raise HTTPException(status_code=500, detail=str(exc))


@app.post("/investigate/batch", response_model=BatchResponse)
def investigate_batch(request: BatchRequest) -> BatchResponse:
    """Run investigations for multiple cases."""
    workflow = _get_workflow()
    results: list[InvestigateResponse] = []
    failed = 0

    for case_id in request.case_ids:
        try:
            state = dict(workflow.run(case_id))
            results.append(_state_to_response(state, case_id))
            if state.get("investigation_status") == InvestigationStatus.ERROR:
                failed += 1
        except Exception as exc:
            log.error(f"Batch investigation failed for {case_id}: {exc}")
            results.append(InvestigateResponse(
                case_id=case_id,
                status="error",
                recommended_action="UNKNOWN",
                approval_required=False,
                approval_route="none",
                uncertainty_level="unknown",
                sufficiency_level="unknown",
                key_findings=[],
                identified_patterns=[],
                hypotheses=[],
                decision_reasoning="",
                evidence_count=0,
                supporting_count=0,
                contradictory_count=0,
                completed_at="",
                error=str(exc),
            ))
            failed += 1

    return BatchResponse(
        total=len(request.case_ids),
        completed=len(results) - failed,
        failed=failed,
        results=results,
    )
