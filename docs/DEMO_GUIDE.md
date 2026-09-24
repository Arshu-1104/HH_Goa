# Demo Guide — FraudGraph Investigator
## Hacker House Goa · Phase 5

---

## 1. Startup

```powershell
# From the project root: C:\Users\Chari\Downloads\HH_Goa
uvicorn agent.api.main:app --host 0.0.0.0 --port 8000
```

Wait for the log line:
```
INFO:     Application startup complete.
```

Open in browser:
```
http://localhost:8000/ui
```

The dashboard loads immediately. All 20 cases appear in the sidebar within 2–3 seconds.

---

## 2. Recommended Demo Flow (10 minutes)

### Step 1 — Home Screen (30 sec)
- Point out the 20 investigation cases in the left sidebar, each with a colour-coded action badge.
- Explain the system: graph database → MCP tools → Part 2 agent → investigation report → UI.

### Step 2 — Select a strong BLOCK_CARD case: HHG-007 (2 min)
- Click **HHG-007** in the sidebar.
- **What to show:**
  - Case Information: Customer C09933, Card C09933-K2, Transaction 3514948, Risk Score 0.87, Trigger: Risk Score alert.
  - Recommended Action panel: **BLOCK CARD** (red accent, prominent).
  - Approval: senior_analyst required.
  - Policy: RULE-001 — "Block card on confirmed fraud pattern + sufficient evidence".
  - Sufficiency: **SUFFICIENT** (green) — all evidence categories covered.
  - Uncertainty: **MEDIUM** (orange) — device identity absent.
  - Key Findings: 18 prior confirmed fraud cases, $12,195 total exposure.
  - Evidence: 3 supporting items / 0 contradictory.
  - Case Memory: shows persisted outcome, approved_by: senior_analyst.
  - Investigation Workflow: 11 data-driven steps.

### Step 3 — Show a contrasting ESCALATE case: HHG-010 (1.5 min)
- Click **HHG-010** in the sidebar.
- **What to show:**
  - Trigger: Risk Score 0.90 — highest in the benchmark.
  - Recommended Action: **ESCALATE** (purple accent).
  - Approval: senior_analyst.
  - Policy: RULE-006 — "Escalate on high uncertainty + high exposure" ($1,000.03 pending).
  - Uncertainty: **HIGH** (red) — only 1 supporting item vs 2 contradictory.
  - Evidence: device is desktop/Windows (contradictory), no prior fraud history (contradictory), but $1,000 exposure (supporting).
  - Point out: the system correctly escalates rather than blocking when contradictory evidence is present and uncertainty is high.

### Step 4 — Show a VERIFY case: HHG-016 (1 min)
- Click **HHG-016** in the sidebar.
- **What to show:**
  - Trigger: Customer report — "I never made this $59.67 purchase."
  - Recommended Action: **VERIFY WITH CUSTOMER** (orange accent).
  - Approval: **none — auto-executable** (green chip, no human needed).
  - Policy: RULE-003 — "Verify with customer on customer-reported case."
  - High uncertainty, no prior fraud history — system correctly chooses verification over blocking.

### Step 5 — Show the ActionGuard safety case: HHG-017 (1 min)
- Click **HHG-017** in the sidebar.
- **What to show:**
  - Policy Basis: **ACTION_GUARD_SAFETY** (not a standard rule ID).
  - Explain: policy engine initially selected CLOSE_NO_FRAUD, but the ActionGuard safety layer blocked it because supporting evidence was present. Downgraded to VERIFY_WITH_CUSTOMER.
  - This demonstrates the safety layer working correctly — the system cannot falsely clear a case that has supporting fraud evidence.

### Step 6 — Benchmark Dashboard (2 min)
- Click **Benchmark Dashboard** in the top-left nav.
- **What to show:**
  - Summary stats: 20/20 reports loaded, 16 require approval, 4 auto-executable.
  - Action distribution: BLOCK_CARD 15 (75%), VERIFY 4 (20%), ESCALATE 1 (5%).
  - Sufficiency: all 20 cases SUFFICIENT.
  - Uncertainty: 15 MEDIUM, 5 HIGH, 0 LOW.
  - Approval route: 9 senior_analyst, 7 fraud_analyst, 4 none.
  - Validation panel: ✅ 12/12 checks passed, 0 errors, 0 warnings.
  - Known limitations table: honest about what Part 2 does not persist to disk.
  - Click any row in the case table → jumps directly to that case's investigation view.

### Step 7 — Drill-down from benchmark (30 sec)
- From the benchmark table, click **HHG-014**.
- Show: analyst_request trigger (unique — only 1 in the benchmark), 3 supporting / 2 contradictory (connected entities evidence), BLOCK_CARD.
- Return to benchmark with the browser back button or sidebar nav.

---

## 3. Recommended Cases by Demo Scenario

| Scenario | Case | Why |
|----------|------|-----|
| Strongest fraud signal | HHG-007 | 18 prior fraud cases, $12,195 exposure, BLOCK_CARD |
| High exposure + high uncertainty | HHG-010 | Only ESCALATE in benchmark, RULE-006 |
| Customer report + clean history | HHG-016 | VERIFY, auto-executable, no prior fraud |
| ActionGuard safety layer | HHG-017 | ACTION_GUARD_SAFETY policy basis |
| Analyst-request trigger | HHG-014 | Only analyst_request in benchmark, shared devices evidence |
| Highest prior fraud count | HHG-018 | 19 prior confirmed fraud cases, $19,262 exposure |

---

## 4. What Each Screen Demonstrates

### Home / Welcome Screen
- System overview and architecture.
- Quick-select dropdown for any of the 20 cases.
- Direct link to the benchmark dashboard.
- Shows how many cases have stored reports.

### Case Investigation View
| Section | What it proves |
|---------|---------------|
| Case Information | Correct case identity loading from stored report + case_pack.csv |
| Recommended Action panel | NBA engine output, policy basis, approval requirement |
| Evidence Sufficiency / Uncertainty meters | Sufficiency and uncertainty engine outputs with full explanations |
| Evidence Counts (Sup / Contra / Total) | Quantified evidence balance |
| Key Findings | Agent's top findings from the investigation |
| Supporting Evidence column | Green — evidence that supports fraud hypothesis |
| Contradictory Evidence column | Red — evidence that argues against fraud |
| Hypotheses section | Honest: all cases show "not reached" notice (confidence < 0.4 in all 20) |
| Case Memory | Persisted investigation result from Part 2 CaseMemoryWriter |
| Investigation Workflow | Data-driven steps derived from actual report fields — no fabricated timeline |

### Benchmark Dashboard
| Section | What it proves |
|---------|---------------|
| Summary stats | 20/20 cases loaded, approval breakdown |
| 6 distribution charts | Action, sufficiency, uncertainty, approval route, trigger type, policy rule |
| Validation panel (✅ 12/12) | All schema/consistency checks pass, 0 errors |
| Known Limitations table | Honest documentation of what Part 2 does not persist to disk |
| Case table with drill-down | Per-case outcomes with direct navigation |

---

## 5. All API Endpoints

| Endpoint | Method | Purpose |
|----------|--------|---------|
| `/ui` | GET | Serves the dashboard HTML |
| `/static/app.js` | GET | Main JavaScript application |
| `/static/styles.css` | GET | Dashboard stylesheet |
| `/api/v3/cases/meta` | GET | All 20 cases with report status |
| `/api/v3/report/{case_id}` | GET | Load one investigation report from disk |
| `/api/v3/benchmark` | GET | All 20 reports + aggregate statistics |
| `/api/v3/benchmark/validate` | GET | Deep schema/consistency validation |
| `/api/v3/policy/rules` | GET | All 7 policy rules (read-only) |
| `/api/v3/run/{case_id}` | POST | Re-run investigation via Part 2 workflow |
| `/health` | GET | Part 2 health check (unchanged) |
| `/cases` | GET | Part 2 case list (unchanged) |
| `/investigate/{case_id}` | POST | Part 2 investigation (unchanged) |
| `/investigate/batch` | POST | Part 2 batch investigation (unchanged) |

---

## 6. Known Limitations

### Investigation Trail Not Persisted
The Part 2 workflow runs a full 11-step investigation trail in memory, but `CaseMemoryWriter` does not serialise `TrailEvent` objects to the JSON report file. The Investigation Workflow section of the UI shows data-driven steps derived from actual report fields — it does **not** fabricate per-step timestamps or tool call details.

### Hypothesis Confidence Below Threshold
All 20 benchmark cases show `hypotheses_summary: []`. Part 2 records hypotheses only when confidence ≥ 0.4. No case in this dataset reached that threshold. The UI displays this honestly with an explanatory notice rather than fabricating hypotheses.

### Transaction Amount is 0.0
The mock CSV client does not populate `TransactionAmt` in the format `FinalSummary` expects. The amount is visible in the `trigger_text` (e.g. "$77.07") but `summary.transaction_amount` is 0.0 in all 20 reports. The UI uses the trigger text for display.

### MCP Test Timeout
`tests/test_mcp.py` starts a real HTTP server process. On Windows, the last test in the class (`test_missing_device_does_not_create_relationship`) hangs waiting for a socket to close after the server process terminates. This is a pre-existing Windows TCP TIME_WAIT issue — it does not affect the MCP server's functionality. All other MCP tests pass. The test suite is run with MCP tests excluded from timed runs.

### No Live TigerGraph
The system runs entirely on the CSV mock client. All 20 investigations complete correctly via MockClient. TigerGraph Savanna credentials and a live instance would be needed to switch to the real graph backend — configure via `.env`.

### No Ground-Truth Labels
The benchmark dataset does not include a `is_fraud` or ground-truth field. The system correctly avoids fabricating accuracy/precision/recall metrics. All reported statistics are derived from what the agent actually decided — not compared to any hidden truth.

---

## 7. Running Tests

```powershell
# Part 3 + Part 4 tests (fast — ~2.5 seconds)
python -m pytest tests/test_part3.py -v

# Part 2 tests (fast — ~0.5 seconds)
python -m pytest tests/agent/ tests/evidence/ tests/policy/ -v

# End-to-end workflow tests (~17 seconds)
python -m pytest tests/integration/test_e2e.py -v

# Part 1 tests (~15 seconds, excludes hanging MCP server test)
python -m pytest tests/test_data.py tests/test_device_and_entities.py tests/test_graph_queries.py tests/test_runtime_smoke.py -v

# All non-MCP tests together
python -m pytest tests/ --ignore=tests/test_mcp.py -q
```

---

## 8. Git Status (as of Phase 5)

No commits made. All Part 3–5 changes are uncommitted and ready for review:

**New untracked files:**
- `agent/api/main.py`
- `agent/api/part3_routes.py`
- `docs/BENCHMARK_RESULTS.md`
- `docs/DEMO_GUIDE.md`
- `tests/test_part3.py`
- `ui/` (directory: `index.html`, `static/app.js`, `static/styles.css`)

**Modified (by existing E2E tests — not Part 3):**
- `investigation_reports/HHG-001.json`
- `investigation_reports/HHG-003.json`
- `investigation_reports/HHG-007.json`
- `investigation_reports/HHG-010.json`
- `investigation_reports/HHG-014.json`
