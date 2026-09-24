# FraudGraph Investigator

A graph-powered, AI-assisted fraud investigation system built for Hacker House Goa. It ingests transaction and identity data into TigerGraph, exposes investigation tools via an MCP server, runs an autonomous investigation agent over 20 open cases, and serves a complete investigator dashboard via FastAPI.

---

## System Architecture

```
Browser (http://localhost:8000/ui)
    |  fetch()
FastAPI Dashboard  (agent/api/main.py — port 8000)
    |  GET /api/v3/cases/meta  /report/{id}  /benchmark  /benchmark/validate
    |  POST /api/v3/run/{id}
    |
Investigation Agent  (agent/graph/workflow.py)
    |  LangGraph state machine
    |
Evidence + Sufficiency + Uncertainty
    |  agent/evidence/  agent/sufficiency/  agent/uncertainty/
    |
Policy Engine + Action Guard  (agent/policy/)
    |  7 deterministic rules, ActionGuard safety layer
    |
Case Memory / Audit  (agent/memory/  agent/audit/)
    |  investigation_reports/*.json
    |
MCP Server  (mcp/server/server.py — port 8765)
    |  get_case | get_customer_history | find_prior_cases
    |  detect_temporal_patterns | calculate_exposure | find_shared_devices
    |
MockClient / TigerGraph  (mcp/server/mock_client.py)
    |  CSV-backed mock with efficient selective column reader
    |
Data Layer
    transactions.csv (675 MB, excluded from Git — see Dataset section)
    data/normalized/transactions_slim.csv  (runtime fallback)
    identity.csv  |  case_pack.csv  |  closed_cases_history.csv
```

---

## Dataset

This project uses the dataset provided for Hacker House Goa.

| File | Rows | Columns | Notes |
|------|------|---------|-------|
| `transactions.csv` | 590,742 | 397 | Raw dataset — **excluded from Git** (675 MB exceeds GitHub's 100 MB limit) |
| `identity.csv` | 144,432 | 41 | Device and identity signals |
| `case_pack.csv` | 20 | — | Open investigation cases |
| `closed_cases_history.csv` | 5,565 | — | Historical closed cases |

### Dataset Packaging

The raw `transactions.csv` (~675 MB) is intentionally excluded from this repository because GitHub enforces a hard 100 MB per-file limit. It is available from the Hacker House Goa organizers.

The repository contains `data/normalized/transactions_slim.csv`, which was generated from the raw file and contains the 19 investigation-relevant columns (`TransactionID`, `TransactionAmt`, `customer_id`, `risk_score`, `channel`, etc.). The agent runtime uses this file automatically when `transactions.csv` is not present:

```
Source priority:
  1. transactions.csv      (project root, if present — full raw dataset)
  2. data/normalized/transactions_slim.csv  (GitHub clone fallback)
```

The source used is logged on startup:
```
Using transaction source: transactions.csv
-- or --
Using transaction source: data/normalized/transactions_slim.csv
```

For full raw-data validation and normalization, place `transactions.csv` in the project root before running the data scripts.

---

## Environment Requirements

- Python 3.12
- TigerGraph Savanna cloud instance (free tier) **or** Community Edition — optional; the system falls back to the CSV mock client automatically
- No pandas / numpy required

---

## Quick Start

```powershell
# 1. Clone the repository
git clone <repo-url>
cd HH_Goa

# 2. Install dependencies
pip install -r requirements.txt

# 3. (Optional) Set up .env for TigerGraph
copy .env.example .env
# Edit .env with your TigerGraph credentials

# 4. Run all 20 investigations
python -m agent.run --all

# 5. Start the dashboard
uvicorn agent.api.main:app --host 0.0.0.0 --port 8000

# 6. Open the dashboard
# http://localhost:8000/ui
```

---

## Running Investigations

```powershell
# Investigate a single case
python -m agent.run --case-id HHG-001

# Investigate all 20 cases (regenerates investigation_reports/*.json)
python -m agent.run --all

# Debug mode
python -m agent.run --case-id HHG-001 --debug
```

Reports are saved to `investigation_reports/HHG-NNN.json`. The batch run summary is saved to `artifacts/batch_summary.json` (separate from case memories, so it does not interfere with memory retrieval).

---

## Dashboard (Part 3)

```powershell
uvicorn agent.api.main:app --host 0.0.0.0 --port 8000
```

Open **http://localhost:8000/ui**

The dashboard provides:
- 20-case overview with action, uncertainty, and sufficiency for each case
- Case investigation view: evidence, findings, hypotheses, patterns, policy/approval, case memory
- Benchmark statistics page with 7 distributions and cross-analysis
- Schema/consistency validation (12 checks)

### API Endpoints

| Method | Path | Description |
|--------|------|-------------|
| GET | `/ui` | Dashboard HTML |
| GET | `/api/v3/cases/meta` | All 20 cases with report status |
| GET | `/api/v3/report/{case_id}` | Full normalised investigation report |
| GET | `/api/v3/benchmark` | All 20 reports + aggregate statistics |
| GET | `/api/v3/benchmark/validate` | Schema / consistency validation |
| GET | `/api/v3/policy/rules` | Policy rule catalogue (read-only) |
| POST | `/api/v3/run/{case_id}` | Re-run a single investigation |
| GET | `/health` | Health check |
| GET | `/cases` | Part 2 case list |

---

## Benchmark Results (20 Cases)

| Metric | Value |
|--------|-------|
| BLOCK_CARD | 15 |
| VERIFY_WITH_CUSTOMER | 4 |
| ESCALATE | 1 |
| Evidence sufficiency: SUFFICIENT | 20 / 20 |
| Uncertainty: MEDIUM | 15 |
| Uncertainty: HIGH | 5 |
| Require approval | 16 / 20 |
| Auto-executable | 4 / 20 |

All invariants hold: BLOCK_CARD is never recommended without SUFFICIENT evidence.

See `docs/BENCHMARK_RESULTS.md` for the full per-case breakdown.

---

## Safety Guardrails

- **ActionGuard**: blocks BLOCK_CARD and FILE_REPORT unless evidence is SUFFICIENT
- **Sufficiency engine**: retry exhaustion does not upgrade INSUFFICIENT → SUFFICIENT
- **Policy evaluator**: 7 deterministic rules derived from closed case history
- **Approval routing**: BLOCK_CARD always requires human analyst sign-off; high-exposure cases require SENIOR_ANALYST
- **No LLM fabrication**: all evidence is grounded in MCP tool results

---

## Running Tests

```powershell
# Core agent / evidence / policy tests (65 tests)
python -m pytest tests/agent tests/evidence tests/policy -q

# Part 3 API and benchmark tests (120 tests)
python -m pytest tests/test_part3.py -q

# Integration / workflow tests (23 tests)
python -m pytest tests/integration/test_e2e.py -q

# Part 1 data / MCP tests (118 tests, requires transactions.csv or slim fallback)
python -m pytest tests/test_data.py tests/test_device_and_entities.py tests/test_graph_queries.py tests/test_runtime_smoke.py -q

# E2E invariant check (all 20 cases, 0 violations expected)
python scripts/e2e_validate.py

# Full suite (test_mcp.py may hang on Windows due to TCP socket cleanup — run separately)
python -m pytest tests/ --ignore=tests/test_mcp.py -q
```

---

## Data Pipeline Scripts

```powershell
# Validate the raw dataset
python scripts/validate_dataset.py

# Normalize CSVs for graph loading
python scripts/normalize_dataset.py

# Generate TigerGraph-compatible load files
python scripts/generate_graph_load_files.py
```

These scripts require the raw `transactions.csv` and `identity.csv` in the project root.

---

## MCP Server

The MCP server runs on port 8765. It falls back to `MockClient` (CSV-based) automatically if TigerGraph is unavailable.

```powershell
python mcp/server/server.py
```

### Available Tools

| Tool | Description |
|------|-------------|
| `get_case` | Full case details and flagged transaction |
| `get_customer_history` | Customer transaction summary |
| `find_prior_cases` | Prior fraud cases for the customer |
| `detect_temporal_patterns` | Card testing, burst activity, channel switching signals |
| `calculate_exposure` | Confirmed + pending financial exposure |
| `find_shared_devices` | Other customers sharing the same device |
| `find_connected_entities` | Connected cards, addresses, emails |

---

## TigerGraph Setup (Optional)

```powershell
# 1. Deploy schema
gsql tigergraph/schema/schema.gsql

# 2. Deploy loading jobs
gsql tigergraph/loading/loading.gsql

# 3. Install and deploy queries
gsql tigergraph/queries/customer_history.gsql
gsql tigergraph/queries/transaction_context.gsql
# ... (see docs/TIGERGRAPH_SCHEMA.md for full list)
```

Copy `.env.example` to `.env` and fill in your TigerGraph credentials before connecting.

---

## Documentation

| File | Description |
|------|-------------|
| `docs/ARCHITECTURE.md` | Full system architecture |
| `docs/BENCHMARK_RESULTS.md` | 20-case benchmark validation results |
| `docs/DATA_DICTIONARY.md` | Data field reference |
| `docs/DEMO_GUIDE.md` | Demo flow and recommended walkthrough |
| `docs/INVESTIGATION_QUERIES.md` | GSQL query reference |
| `docs/TIGERGRAPH_SCHEMA.md` | Graph schema reference |

---

## Known Limitations

| Issue | Detail |
|-------|--------|
| `transaction_amount` is 0.0 in reports | The mock CSV client does not populate `TransactionAmt` in the format `generate_final_summary` expects |
| `investigation_trail_summary` is empty | Trail events are in-memory only; not persisted to the report JSON |
| `hypotheses_summary` is empty | No hypothesis reached the 0.4 confidence threshold in this dataset |
| `identified_patterns` is empty | Derived from hypothesis confidence — same root cause as above |
| `test_mcp.py` may hang on Windows | Pre-existing TCP socket cleanup issue; run the rest of the suite with `--ignore=tests/test_mcp.py` |
| `transactions.csv` excluded from Git | 675 MB exceeds GitHub's 100 MB limit; use `data/normalized/transactions_slim.csv` fallback |

---

## Environment Variables

| Variable | Description | Default |
|----------|-------------|---------|
| `TIGERGRAPH_HOST` | TigerGraph instance URL | — |
| `TIGERGRAPH_USERNAME` | TigerGraph username | `tigergraph` |
| `TIGERGRAPH_PASSWORD` | TigerGraph password | — |
| `TIGERGRAPH_GRAPH_NAME` | Graph name | `FraudGraph` |
| `TIGERGRAPH_SECRET` | API secret | — |
| `MCP_PORT` | MCP server port | `8765` |
| `DATA_DIR` | Path to CSV files | `./` |
| `LOG_LEVEL` | Logging level | `INFO` |
