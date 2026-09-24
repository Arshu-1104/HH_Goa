# Architecture — FraudGraph Investigator

## System Layers Diagram

```
╔══════════════════════════════════════════════════════════════════════╗
║  LAYER 4: INVESTIGATION AGENT LAYER                                 ║
║                                                                      ║
║   ┌──────────────────────────────────────────────────────────────┐  ║
║   │  InvestigationWorkflow  (agent/graph/workflow.py)            │  ║
║   │  LangGraph-style state machine — pure Python                 │  ║
║   │                                                              │  ║
║   │  Flow:                                                       │  ║
║   │    load_case → plan → collect_evidence                       │  ║
║   │    → analyze → update_hypotheses → assess_uncertainty        │  ║
║   │    → assess_sufficiency                                      │  ║
║   │        → INSUFFICIENT (≤2 retries): request_evidence → loop  │  ║
║   │        → SUFFICIENT: evaluate_policy                        │  ║
║   │    → determine_next_best_action                              │  ║
║   │    → generate_final_summary → write_case_memory             │  ║
║   │                                                              │  ║
║   │  Evidence + Sufficiency + Uncertainty engines                │  ║
║   │  Policy evaluator (7 rules) + ActionGuard safety layer       │  ║
║   │  Approval router: FRAUD_ANALYST / SENIOR_ANALYST / NONE      │  ║
║   │                                                              │  ║
║   │  Inputs:  case_pack.csv (20 open cases)                      │  ║
║   │  Outputs: investigation_reports/{case_id}.json               │  ║
║   └──────────────────────────────────────────────────────────────┘  ║
║                                                                      ║
║   ┌──────────────────────────────────────────────────────────────┐  ║
║   │  FastAPI Dashboard  (agent/api/main.py — port 8000)          │  ║
║   │  GET /ui  |  /api/v3/cases/meta  |  /api/v3/report/{id}      │  ║
║   │  GET /api/v3/benchmark  |  /api/v3/benchmark/validate        │  ║
║   │  POST /api/v3/run/{id}  (re-run single investigation)        │  ║
║   └──────────────────────────────────────────────────────────────┘  ║
╠══════════════════════════════════════════════════════════════════════╣
║  LAYER 3: MCP SERVER LAYER                                          ║
║                                                                      ║
║   HTTP JSON-RPC server — mcp/server/server.py — port 8765           ║
║                                                                      ║
║   Tools exposed:                                                     ║
║   ┌────────────────────┐  ┌────────────────────────────────────┐    ║
║   │ get_case           │  │ find_prior_cases                   │    ║
║   │ get_customer_hist  │  │ detect_temporal_patterns           │    ║
║   │ get_txn_context    │  │ calculate_exposure                 │    ║
║   │ find_connected     │  │ search_graph                       │    ║
║   │ find_shared_dev    │  │ write_case                         │    ║
║   │ find_connected_crd │  └────────────────────────────────────┘    ║
║   └────────────────────┘                                            ║
║                                                                      ║
║   ┌──────────────────────┐    ┌──────────────────────────────────┐  ║
║   │ tigergraph_client.py │ OR │ mock_client.py (CSV fallback)    │  ║
║   └──────────────────────┘    └──────────────────────────────────┘  ║
╠══════════════════════════════════════════════════════════════════════╣
║  LAYER 2: GRAPH LAYER                                               ║
║                                                                      ║
║   TigerGraph Savanna — Graph: FraudGraph                            ║
║                                                                      ║
║   Vertices:                                                          ║
║   ┌──────────────┐ ┌──────┐ ┌─────────────┐ ┌──────────────────┐  ║
║   │ Customer     │ │ Card │ │ Transaction │ │ DeviceProfile    │  ║
║   └──────────────┘ └──────┘ └─────────────┘ └──────────────────┘  ║
║   ┌────────┐ ┌─────────────┐ ┌─────────────┐ ┌──────────────────┐ ║
║   │ Region │ │ EmailDomain │ │ ClosedCase  │ │ InvestigationCase│ ║
║   └────────┘ └─────────────┘ └─────────────┘ └──────────────────┘ ║
║   ┌───────────────┐                                                  ║
║   │ FraudPattern  │                                                  ║
║   └───────────────┘                                                  ║
║                                                                      ║
║   GSQL Queries:                                                      ║
║   get_customer_history | get_transaction_context                     ║
║   find_connected_entities | find_prior_cases                         ║
║   detect_temporal_patterns | calculate_exposure                      ║
║   find_shared_devices | detect_fraud_clusters                        ║
╠══════════════════════════════════════════════════════════════════════╣
║  LAYER 1: DATA LAYER                                                ║
║                                                                      ║
║   Raw CSVs:                                                          ║
║   transactions.csv (590k) | identity.csv (144k)                     ║
║   case_pack.csv (20) | closed_cases_history.csv (5.5k)              ║
║                                                                      ║
║   Pipeline:                                                          ║
║   validate_dataset.py → normalize_dataset.py                        ║
║   → generate_graph_load_files.py → TigerGraph loading jobs          ║
╚══════════════════════════════════════════════════════════════════════╝
```

---

## Data Flow

```
transactions.csv ──┐
identity.csv       ├──► validate_dataset.py ──► normalize_dataset.py
case_pack.csv      │         (checks)              (deduplicate,
closed_cases.csv ──┘                                normalize)
                                                         │
                                              generate_graph_load_files.py
                                                         │
                                              data/graph_load/*.csv
                                                         │
                                              TigerGraph loading.gsql
                                                         │
                                              FraudGraph (graph DB)
                                                         │
                                              GSQL queries installed
                                                         │
                                              MCP server (port 8765)
                                                         │
                                              Agent tool calls (Part 2)
```

---

## TigerGraph Role

TigerGraph is the core analytical engine. Its role:

1. **Schema**: Defines the fraud domain as a typed property graph (customers, cards, transactions, devices, regions, email domains, cases, patterns).

2. **Storage**: Holds ~590k transactions with all metadata. Edges encode relationships that would be expensive to compute via SQL joins.

3. **GSQL queries**: Compiled, installed queries run in milliseconds even on large neighborhoods. Key capabilities:
   - Multi-hop traversal: find all customers sharing a device with a flagged transaction
   - Temporal aggregation: count transaction bursts within time windows
   - Pattern matching: identify card-testing sequences (small repeated amounts)
   - Exposure calculation: sum amounts across case-linked transactions

4. **Why graph vs SQL**: Fraud investigation is inherently graph-shaped. "Who else used this device?" requires a 2-hop traversal. "What fraud patterns has this customer been linked to historically?" requires 3-hop. TigerGraph handles these natively.

---

## MCP Role

The Model Context Protocol (MCP) server is the interface layer between the LLM agent and the graph database.

- Exposes fraud investigation capabilities as named tools
- Handles TigerGraph connection, authentication, query execution
- Falls back gracefully to CSV-based mock when TigerGraph unavailable
- Standardizes all responses: `{success, tool, data, warnings, source}`
- Handles timeouts and errors without crashing the agent
- Logs all tool calls for audit trail

The agent never calls TigerGraph directly — it always goes through MCP tools.

---

## Investigation Agent Layer

The investigation agent is a deterministic state machine implemented in `agent/graph/workflow.py`. It requires no LLM API key — all decisions are made by rule-based engines grounded in actual MCP tool results.

Key components:
- **Evidence extractor**: pulls structured evidence items from every MCP tool response
- **Sufficiency engine**: evaluates whether all required evidence categories are covered; retry exhaustion never upgrades INSUFFICIENT to SUFFICIENT
- **Uncertainty engine**: rates investigation confidence as LOW / MEDIUM / HIGH
- **Policy evaluator**: applies 7 deterministic rules (RULE-001 through RULE-007) to select a candidate action
- **ActionGuard**: safety layer that blocks disruptive actions (BLOCK_CARD, FILE_REPORT) when evidence is insufficient, regardless of policy output
- **Approval router**: routes BLOCK_CARD to FRAUD_ANALYST or SENIOR_ANALYST based on exposure amount

The workflow runs all 20 cases via `python -m agent.run --all`. Results are persisted to `investigation_reports/{case_id}.json`.

---

## Investigation Flow

```
┌─────────────────────────────────────────────────────────────┐
│  TRIGGER                                                    │
│  Input: case_id, trigger_type, flagged_txn_id, risk_score   │
│  → Determine investigation priority and initial hypothesis  │
└──────────────────────────┬──────────────────────────────────┘
                           │
┌──────────────────────────▼──────────────────────────────────┐
│  INVESTIGATE                                                │
│  Tool: get_case(case_id)                                    │
│  Tool: get_customer_history(customer_id)                    │
│  → Load case details and customer baseline behavior         │
└──────────────────────────┬──────────────────────────────────┘
                           │
┌──────────────────────────▼──────────────────────────────────┐
│  GATHER EVIDENCE                                            │
│  Tool: get_transaction_context(flagged_txn_id)              │
│  Tool: find_connected_entities(flagged_txn_id)              │
│  Tool: find_shared_devices(flagged_txn_id)                  │
│  → Collect transaction details, device info, connections    │
└──────────────────────────┬──────────────────────────────────┘
                           │
┌──────────────────────────▼──────────────────────────────────┐
│  ASSESS UNCERTAINTY                                         │
│  → Evaluate evidence quality                                │
│  → Check for missing identity data, high missingness fields │
│  → Rate confidence: HIGH / MEDIUM / LOW                     │
└──────────────────────────┬──────────────────────────────────┘
                           │
              ┌────────────┴────────────┐
              │ LOW confidence?         │ HIGH/MEDIUM confidence?
              ▼                         ▼
┌─────────────────────────┐  ┌─────────────────────────────────┐
│ REQUEST MORE EVIDENCE   │  │ REASSESS                        │
│ Tool: find_prior_cases  │  │ → Pattern matching vs history   │
│ Tool: detect_temporal   │  │ Tool: find_prior_cases          │
│ Tool: search_graph      │  │ → Update hypothesis             │
└─────────────┬───────────┘  └──────────────┬──────────────────┘
              │                             │
              └─────────────┬───────────────┘
                            │
┌───────────────────────────▼─────────────────────────────────┐
│  RECOMMEND                                                  │
│  → One of: BLOCK_CARD | VERIFY_WITH_CUSTOMER |              │
│            FILE_REPORT | CLOSE_NO_FRAUD | ESCALATE          │
│  Tool: calculate_exposure(case_id)                          │
│  → Include exposure amount in recommendation                │
└──────────────────────────┬──────────────────────────────────┘
                           │
┌──────────────────────────▼──────────────────────────────────┐
│  EXPLAIN                                                    │
│  → Natural language summary of findings                     │
│  → Evidence chain: which facts led to recommendation        │
│  → Uncertainty disclosure                                   │
│  → Similar historical cases cited                           │
└──────────────────────────┬──────────────────────────────────┘
                           │
┌──────────────────────────▼──────────────────────────────────┐
│  UPDATE CASE MEMORY                                         │
│  Tool: write_case(case_id, update)                          │
│  → Persist findings, recommendation, evidence chain         │
│  → Link to similar closed cases                             │
└─────────────────────────────────────────────────────────────┘
```
