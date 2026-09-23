# Part 2 Implementation Plan — FraudGraph Investigation Agent

## 1. Discovered Part 1 Architecture

### Runtime Environment
- Python 3.11.8
- LangGraph 1.2.6 ✅ (already installed)
- LangChain 0.3.23 ✅
- langchain-anthropic 0.3.14 ✅
- langchain-openai 0.3.35 ✅
- Pydantic 2.x ✅
- FastAPI 0.128.0 ✅
- pytest 9.0.2 ✅
- requests 2.32.5 ✅
- anthropic 0.77.0 ✅

### MCP Server
- HTTP JSON-RPC at `http://localhost:8765` (default)
- `POST /tool` with body `{"tool": "<name>", "params": {...}}`
- Auto-fallback to MockClient (CSV) when TigerGraph unavailable
- All 8 tools fully functional via MockClient

### Data
- `case_pack.csv` — 20 open cases (HHG-001 to HHG-020)
- `closed_cases_history.csv` — 5,565 historical closed cases
- `transactions.csv` — 590,742 rows
- `identity.csv` — 144,432 rows

---

## 2. The 8 MCP Tools

| # | Tool Name | Required Params | Optional Params |
|---|---|---|---|
| 1 | `get_case` | `case_id` | — |
| 2 | `get_customer_history` | `customer_id` | `limit` (default 20) |
| 3 | `find_connected_entities` | `entity_id` | `entity_type` (default "customer") |
| 4 | `find_prior_cases` | — | `customer_id`, `card_id` |
| 5 | `detect_temporal_patterns` | `customer_id` | `window_hours` (default 24) |
| 6 | `calculate_exposure` | — | `customer_id`, `card_id` |
| 7 | `find_shared_devices` | `customer_id` | — |
| 8 | `get_transaction_context` | `txn_id` | — |

### Key Tool Output Facts
- `get_case` → `{found, case_id, case{...}, flagged_transaction{...}}`
- `get_customer_history` → `{customer_id, found, transaction_count, total_transaction_amt, fraud_case_count, total_fraud_exposure_usd, recent_transactions[], closed_cases[]}`
- `find_connected_entities` → `{entity_id, entity_type, connected_entity_count, connected_entities[{entity_type, entity_id, relationship, source_device, source_email, source_region}]}`
- `find_prior_cases` → `{customer_id, card_id, total_cases, fraud_cases, cleared_cases, total_exposure_usd, cases[]}`
- `detect_temporal_patterns` → `{customer_id, total_transactions, transactions_in_window, micro_transaction_count, signals{card_testing, burst_activity, channel_switching}, avg/max/min_transaction_amt}`
- `calculate_exposure` → `{customer_id, card_id, confirmed_fraud_cases, total_confirmed_exposure_usd, avg_fraud_exposure_usd, pending_investigation_txns[], pending_exposure_usd, fraud_cases_detail[]}`
- `find_shared_devices` → `{customer_id, devices_found, devices_shared_with_others, total_shared_customer_count, shared_with_customers[], device_details[]}`
- `get_transaction_context` → `{found, TransactionID, transaction{...}, customer_id, customer_prior_fraud_cases, customer_recent_transactions[]}`

### IMPORTANT: calculate_exposure takes customer_id/card_id (NOT case_id)
The MockClient implementation takes `customer_id`/`card_id`, not `case_id` like the GSQL version.

---

## 3. How Part 2 Consumes the 8 Tools

```
MCP Tool Call (HTTP POST /tool)
  ↓
agent/tools/mcp_client.py  (HTTP adapter — calls the MCP server)
  ↓
agent/tools/adapters.py    (normalizes raw MCP output → ToolResult models)
  ↓
agent/evidence/extractor.py (extracts Evidence objects from ToolResult)
  ↓
InvestigationState.evidence[]  (typed evidence list)
```

---

## 4. Proposed Agent Architecture

```
agent/
├── __init__.py
├── run.py                     # CLI entrypoint: python -m agent.run --case-id HHG-001
├── state/
│   ├── __init__.py
│   ├── models.py              # All Pydantic models for state
│   └── state.py               # InvestigationState definition
├── graph/
│   ├── __init__.py
│   ├── workflow.py            # LangGraph StateGraph definition
│   ├── nodes.py               # All 16 graph node functions
│   └── routing.py             # Conditional edge functions
├── tools/
│   ├── __init__.py
│   ├── mcp_client.py          # HTTP client for MCP server
│   ├── adapters.py            # Raw MCP output → ToolResult models
│   └── registry.py            # Tool selection logic
├── evidence/
│   ├── __init__.py
│   ├── models.py              # Evidence, EvidenceCategory models
│   ├── extractor.py           # ToolResult → Evidence objects
│   ├── provenance.py          # Evidence provenance tracking
│   └── classifier.py         # Supporting vs contradictory classifier
├── hypotheses/
│   ├── __init__.py
│   ├── models.py              # Hypothesis, HypothesisStatus models
│   └── manager.py             # Hypothesis creation and update
├── sufficiency/
│   ├── __init__.py
│   ├── engine.py              # Evidence sufficiency evaluation
│   ├── models.py              # SufficiencyResult model
│   └── config.py              # Sufficiency configuration
├── uncertainty/
│   ├── __init__.py
│   ├── engine.py              # Uncertainty derivation engine
│   └── models.py              # UncertaintyAssessment model
├── graphrag/
│   ├── __init__.py
│   ├── retriever.py           # Fetches relevant graph evidence via MCP
│   ├── context_builder.py     # Assembles context pack for LLM
│   └── prompts.py             # LLM prompt templates (grounded)
├── policy/
│   ├── __init__.py
│   ├── models.py              # PolicyRule, CandidateAction models
│   ├── rules.py               # Deterministic policy rules
│   ├── evaluator.py           # Policy evaluation engine
│   ├── approvals.py           # Approval routing
│   └── action_guard.py        # Final safety gate
├── memory/
│   ├── __init__.py
│   ├── writer.py              # Writes case memory (in-memory + JSON file)
│   └── retriever.py           # Retrieves prior memory
├── decisions/
│   ├── __init__.py
│   └── next_best_action.py    # NBA decision module
├── audit/
│   ├── __init__.py
│   ├── models.py              # TrailEvent model
│   └── trail.py               # Investigation trail writer
└── api/
    ├── __init__.py
    ├── routes.py              # FastAPI routes
    └── schemas.py             # Request/response models
```

---

## 5. LangGraph Nodes

| Node | Purpose |
|---|---|
| `load_case` | Load case from MCP `get_case` + create initial state |
| `plan_investigation` | LLM creates structured investigation plan |
| `collect_initial_evidence` | Call planned MCP tools, extract evidence |
| `analyze_evidence` | LLM analyzes evidence, classifies supporting/contradictory |
| `update_hypotheses` | Update hypothesis statuses based on evidence |
| `assess_uncertainty` | Derive uncertainty from evidence state |
| `assess_evidence_sufficiency` | Run sufficiency engine |
| `request_evidence` | Create structured evidence request |
| `receive_evidence` | Inject new evidence into state |
| `reassess` | Re-run analysis after new evidence |
| `evaluate_policy` | Run deterministic policy evaluator |
| `generate_candidate_actions` | LLM proposes candidate actions |
| `determine_next_best_action` | NBA decision module selects best action |
| `determine_approval` | Route to approval if required |
| `write_case_memory` | Persist case to memory store |
| `generate_final_summary` | Generate structured final summary |

---

## 6. Conditional Routing

```
assess_evidence_sufficiency
  → INSUFFICIENT → request_evidence
  → SUFFICIENT   → evaluate_policy

reassess
  → loops back to analyze_evidence

determine_approval
  → APPROVAL_REQUIRED → write_case_memory (with approval_pending flag)
  → AUTO_EXECUTE      → write_case_memory
```

---

## 7. Files to Create

### Core agent (new)
- `agent/__init__.py`
- `agent/run.py`
- `agent/state/models.py` + `state.py`
- `agent/graph/workflow.py` + `nodes.py` + `routing.py`
- `agent/tools/mcp_client.py` + `adapters.py` + `registry.py`
- `agent/evidence/models.py` + `extractor.py` + `provenance.py` + `classifier.py`
- `agent/hypotheses/models.py` + `manager.py`
- `agent/sufficiency/engine.py` + `models.py` + `config.py`
- `agent/uncertainty/engine.py` + `models.py`
- `agent/graphrag/retriever.py` + `context_builder.py` + `prompts.py`
- `agent/policy/models.py` + `rules.py` + `evaluator.py` + `approvals.py` + `action_guard.py`
- `agent/memory/writer.py` + `retriever.py`
- `agent/decisions/next_best_action.py`
- `agent/audit/models.py` + `trail.py`
- `agent/api/routes.py` + `schemas.py`

### Tests (new)
- `tests/agent/test_state.py`
- `tests/agent/test_planning.py`
- `tests/agent/test_tool_selection.py`
- `tests/evidence/test_models.py`
- `tests/evidence/test_extractor.py`
- `tests/evidence/test_provenance.py`
- `tests/evidence/test_classifier.py`
- `tests/policy/test_rules.py`
- `tests/policy/test_evaluator.py`
- `tests/policy/test_action_guard.py`
- `tests/memory/test_writer.py`
- `tests/integration/test_e2e.py`
- `tests/integration/test_before_after.py`
- `tests/integration/test_anti_hallucination.py`

### Documentation (new)
- `docs/PART2_IMPLEMENTATION_PLAN.md` (this file)
- `docs/PART2_ARCHITECTURE.md`
- `docs/PART2_GUIDE.md`

---

## 8. Dependencies (all already installed)
- `langgraph==1.2.6`
- `langchain-anthropic==0.3.14` (or langchain-openai as fallback)
- `pydantic==2.x`
- `fastapi==0.128.0`
- `uvicorn`
- `requests==2.32.5`
- `pytest==9.0.2`

---

## 9. Environment Variables to Add to .env.example
```
# LLM Provider
LLM_PROVIDER=anthropic        # or openai
LLM_MODEL=claude-3-5-haiku-20241022  # fast model for hackathon
LLM_TEMPERATURE=0.0
LLM_TIMEOUT=60

# MCP Connection
MCP_HOST=localhost
MCP_PORT=8765

# Agent Configuration
MAX_TOOL_CALLS=20
MAX_INVESTIGATION_STEPS=30
EVIDENCE_REQUEST_TIMEOUT=30

# Policy
DISRUPTIVE_ACTION_THRESHOLD=0.7
REQUIRE_APPROVAL_FOR_BLOCK=true

# Feature flags
DEBUG_MODE=false
AGENT_MODE=auto   # auto | supervised

# API
API_PORT=8000
```

---

## 10. Assumptions
1. The MCP server is running at `MCP_HOST:MCP_PORT` (or we use MockClient directly for tests)
2. An LLM API key is in environment (`ANTHROPIC_API_KEY` or `OPENAI_API_KEY`)
3. LangGraph's `StateGraph` is used for explicit state-machine orchestration
4. The agent is NOT a chatbot — it has a deterministic trigger→investigation→decision flow
5. Policy rules are derived from actual `actions_taken` values in `closed_cases_history.csv`:
   - `CREATE_CASE|BLOCK_CARD` (most common — 4,268 cases)
   - `VERIFY_WITH_CUSTOMER|CLOSE_NO_FRAUD` (900 cases)
   - `CREATE_CASE|BLOCK_CARD|FILE_REPORT` (397 cases)
6. Fraud patterns are exactly the 7 defined in `fraud_patterns.csv`
7. Case memory is stored as JSON files in `memory/` directory (no additional DB)
8. For tests that don't need a live LLM, LLM calls are mocked

---

## 11. Risks
1. **LLM API key not present**: All LLM-dependent nodes must degrade gracefully. Tests mock LLM.
2. **MCP server not running**: Agent tests use MockClient directly, bypassing HTTP.
3. **Large connected entity sets**: `find_connected_entities` can return up to 50 entities. Context pack must summarize, not dump all.
4. **Hallucination**: GraphRAG prompts are strictly grounded. Tests verify amounts/entities cannot be fabricated.
5. **Memory persistence**: JSON file memory is sufficient for hackathon. Not production-grade.
