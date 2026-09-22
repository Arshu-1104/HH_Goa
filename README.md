# FraudGraph Investigator

A graph-powered fraud investigation system built for Hacker House Goa. It ingests transaction and identity data into TigerGraph, exposes investigation tools via an MCP server, and enables an AI agent to autonomously investigate fraud cases.

## Mission

Given a set of open fraud investigation cases, automatically gather evidence from a graph database, detect patterns (card-not-present, account takeover, card testing, out-of-region use), assess uncertainty, and recommend actions — all in a transparent, auditable way.

---

## Architecture Overview

```
┌─────────────────────────────────────────────────────────┐
│                    AGENT LAYER (Part 2)                 │
│           LLM reasoning + investigation loop            │
└───────────────────────┬─────────────────────────────────┘
                        │ MCP tool calls
┌───────────────────────▼─────────────────────────────────┐
│                    MCP SERVER LAYER                     │
│          mcp/server/server.py  (port 8765)              │
│    get_case | get_customer_history | find_connected …   │
└───────────────────────┬─────────────────────────────────┘
                        │ pyTigerGraph / mock fallback
┌───────────────────────▼─────────────────────────────────┐
│                    GRAPH LAYER                          │
│     TigerGraph Savanna — FraudGraph schema              │
│   Vertices: Customer, Card, Transaction, Device …       │
│   GSQL queries: customer_history, transaction_context … │
└───────────────────────┬─────────────────────────────────┘
                        │ CSV loading jobs
┌───────────────────────▼─────────────────────────────────┐
│                    DATA LAYER                           │
│  transactions.csv | identity.csv | case_pack.csv        │
│  closed_cases_history.csv                               │
│  scripts/: validate → normalize → generate_load_files  │
└─────────────────────────────────────────────────────────┘
```

---

## Environment Requirements

- Python 3.12
- Node 24 (for any JS tooling)
- TigerGraph Savanna cloud instance (free tier works) **or** TigerGraph Community Edition
- `pyTigerGraph` Python package (install when network available: `pip install pyTigerGraph`)
- No pandas / numpy required — pure stdlib for data scripts

---

## Dataset Setup

Place all four CSV files in the workspace root (`C:\Users\Admin\Desktop\HH_Goa\`):

```
transactions.csv          590,742 rows, 397 columns
identity.csv              144,432 rows, 41 columns
case_pack.csv             20 rows — the open investigation cases
closed_cases_history.csv  5,565 rows — historical closed cases
```

Run validation first:

```powershell
python scripts/validate_dataset.py
```

Then normalize and generate graph-load files:

```powershell
python scripts/normalize_dataset.py
python scripts/generate_graph_load_files.py
```

---

## TigerGraph Setup (Savanna Cloud)

1. Sign up at [https://savanna.tgcloud.io](https://savanna.tgcloud.io)
2. Create a new graph named `FraudGraph`
3. Note your instance host (e.g. `https://xxx.i.tgcloud.io`), username, password
4. Generate a secret from the TigerGraph admin panel
5. Copy `.env.example` to `.env` and fill in your credentials:

```powershell
copy .env.example .env
# then edit .env with your values
```

---

## Environment Variables

See `.env.example` for the full list. Required variables:

| Variable | Description |
|---|---|
| `TIGERGRAPH_HOST` | Full URL of your TigerGraph instance |
| `TIGERGRAPH_USERNAME` | TigerGraph username (default: `tigergraph`) |
| `TIGERGRAPH_PASSWORD` | TigerGraph password |
| `TIGERGRAPH_GRAPH_NAME` | Graph name (default: `FraudGraph`) |
| `TIGERGRAPH_SECRET` | API secret from TigerGraph admin |
| `MCP_PORT` | MCP server port (default: `8765`) |
| `DATA_DIR` | Path to CSV files (default: `./`) |
| `LOG_LEVEL` | Logging level (default: `INFO`) |

---

## How to Run Each Script

```powershell
# Validate dataset integrity
python scripts/validate_dataset.py

# Normalize CSVs for graph loading
python scripts/normalize_dataset.py

# Generate TigerGraph-compatible load files
python scripts/generate_graph_load_files.py

# Start the MCP server
python mcp/server/server.py
# or with custom port:
$env:MCP_PORT=9000; python mcp/server/server.py
```

---

## How to Run Tests

```powershell
python -m pytest tests/ -v
```

Run a specific test module:

```powershell
python -m pytest tests/test_data.py -v
python -m pytest tests/test_mcp.py -v
python -m pytest tests/test_graph_queries.py -v
```

---

## GSQL Deployment Instructions

After setting up your TigerGraph instance and `.env`:

```powershell
# 1. Deploy the schema
# Log into TigerGraph Studio or use gsql CLI:
gsql tigergraph/schema/schema.gsql

# 2. Deploy loading jobs
gsql tigergraph/loading/loading.gsql

# 3. Run loading jobs (adjust file paths as needed)
gsql -g FraudGraph "RUN LOADING JOB load_transactions USING f1=\"/path/to/data/graph_load/transactions_vertex.csv\""

# 4. Install and deploy queries
gsql tigergraph/queries/customer_history.gsql
gsql tigergraph/queries/transaction_context.gsql
gsql tigergraph/queries/connected_entities.gsql
gsql tigergraph/queries/prior_cases.gsql
gsql tigergraph/queries/temporal_activity.gsql
gsql tigergraph/queries/exposure.gsql
gsql tigergraph/queries/shared_devices.gsql
gsql tigergraph/algorithms/pattern_detection.gsql
```

---

## MCP Server Setup

The MCP server runs on `http://localhost:8765` by default.

```powershell
# Start server (falls back to mock CSV client if TigerGraph unavailable)
python mcp/server/server.py
```

Test a tool call:

```powershell
# PowerShell
$body = '{"tool":"get_case","params":{"case_id":"HHG-001"}}'
Invoke-WebRequest -Uri http://localhost:8765/tool -Method POST -Body $body -ContentType 'application/json'
```

See `mcp/README.md` for full tool documentation.

---

## Troubleshooting

**TigerGraph not available** — The MCP server automatically falls back to a CSV-based mock client. All tools will return data sourced directly from the CSV files. Tests are designed to work without TigerGraph.

**Missing CSV files** — Run `python scripts/validate_dataset.py` to get a clear report of what's missing.

**pyTigerGraph not installed** — The mock client will be used automatically. When network is available: `pip install pyTigerGraph`

**Port already in use** — Set `$env:MCP_PORT=9000` before starting the server.

**Encoding errors in CSVs** — The scripts use `errors="replace"` for robustness. Check `validate_dataset.py` output for any encoding warnings.
