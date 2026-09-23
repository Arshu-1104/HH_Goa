"""agent/api/schemas.py — FastAPI request/response schemas."""
from __future__ import annotations
from pydantic import BaseModel
from typing import Any


class InvestigateRequest(BaseModel):
    case_id: str


class HypothesisSummary(BaseModel):
    id: str
    name: str
    status: str
    confidence: float


class InvestigateResponse(BaseModel):
    case_id: str
    status: str
    recommended_action: str
    approval_required: bool
    approval_route: str
    uncertainty_level: str
    sufficiency_level: str
    key_findings: list[str]
    identified_patterns: list[str]
    hypotheses: list[HypothesisSummary]
    decision_reasoning: str
    evidence_count: int
    supporting_count: int
    contradictory_count: int
    completed_at: str
    error: str = ""


class BatchRequest(BaseModel):
    case_ids: list[str]


class BatchResponse(BaseModel):
    total: int
    completed: int
    failed: int
    results: list[InvestigateResponse]
