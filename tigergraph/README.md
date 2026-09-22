# TigerGraph Setup — FraudGraph

## Prerequisites

- TigerGraph Savanna account (free tier) at https://savanna.tgcloud.io
  OR TigerGraph Community Edition installed locally
- Python 3.12 with `pyTigerGraph` installed (when network available):
  `pip install pyTigerGraph`

---

## Environment Variables

Set these in your `.env` file (copy from `.env.example`):

```
TIGERGRAPH_HOST=https://your-instance.i.tgcloud.io
TIGERGRAPH_USERNAME=tigergraph
TIGERGRAPH_PASSWORD=your_password
TIGERGRAPH_GRAPH_NAME=FraudGraph
TIGERGRAPH_SECRET=your_secret
```

To get your secret:
1. Log into TigerGraph Savanna or GraphStudio
2. Navigate to Admin → User Management
3. Generate a secret for the `tigergraph` user

---

## Connecting to TigerGraph Savanna

1. Sign up at https://savanna.tgcloud.io
2. Create a new cloud instance (free tier: 4GB RAM, 50GB storage)
3. Note your instance URL (e.g. `https://abc123.i.tgcloud.io`)
4. Set the environment variables above

Test connection via pyTigerGraph:

```python
import pyTigerGraph as tg
conn = tg.TigerGraphConnection(
    host="https://abc123.i.tgcloud.io",
    username="tigergraph",
    password="your_password",
    graphname="FraudGraph"
)
conn.apiToken = conn.getToken(conn.createSecret())
print(conn.getVertexCount("*"))
```

---

## Step 1: Deploy the Schema

Using the GSQL CLI or GraphStudio:

```bash
# Via GSQL CLI
gsql tigergraph/schema/schema.gsql
```

Or paste the contents of `tigergraph/schema/schema.gsql` into the GSQL editor in GraphStudio.

This creates all vertex types (Customer, Card, Transaction, DeviceProfile, Region, EmailDomain, ClosedCase, InvestigationCase, FraudPattern) and edge types.

---

## Step 2: Generate Load Files

First run the data preparation scripts:

```powershell
python scripts/validate_dataset.py
python scripts/normalize_dataset.py
python scripts/generate_graph_load_files.py
```

This creates `data/graph_load/` with these CSV files:
- `customers_vertex.csv`
- `cards_vertex.csv`
- `transactions_vertex.csv`
- `device_profiles_vertex.csv`
- `regions_vertex.csv`
- `email_domains_vertex.csv`
- `closed_cases_vertex.csv`
- `investigation_cases_vertex.csv`
- `fraud_patterns_vertex.csv`
- `owns_edges.csv`
- `performed_edges.csv`
- `made_edges.csv`
- `uses_device_edges.csv`
- `billed_to_region_edges.csv`
- `uses_email_edges.csv`
- `closed_case_customer_edges.csv`
- `closed_case_card_edges.csv`
- `closed_case_txn_edges.csv`
- `has_pattern_edges.csv`
- `investigation_customer_edges.csv`
- `investigation_card_edges.csv`
- `investigation_txn_edges.csv`

---

## Step 3: Deploy Loading Jobs

```bash
gsql -g FraudGraph tigergraph/loading/loading.gsql
```

---

## Step 4: Run Loading Jobs

Replace `/path/to/` with your actual absolute path to `data/graph_load/`:

```bash
# Load vertices
gsql -g FraudGraph "RUN LOADING JOB load_customers USING f1='/path/to/data/graph_load/customers_vertex.csv'"
gsql -g FraudGraph "RUN LOADING JOB load_cards USING f1='/path/to/data/graph_load/cards_vertex.csv'"
gsql -g FraudGraph "RUN LOADING JOB load_transactions USING f1='/path/to/data/graph_load/transactions_vertex.csv'"
gsql -g FraudGraph "RUN LOADING JOB load_device_profiles USING f1='/path/to/data/graph_load/device_profiles_vertex.csv'"
gsql -g FraudGraph "RUN LOADING JOB load_regions USING f1='/path/to/data/graph_load/regions_vertex.csv'"
gsql -g FraudGraph "RUN LOADING JOB load_email_domains USING f1='/path/to/data/graph_load/email_domains_vertex.csv'"
gsql -g FraudGraph "RUN LOADING JOB load_closed_cases USING f1='/path/to/data/graph_load/closed_cases_vertex.csv'"
gsql -g FraudGraph "RUN LOADING JOB load_investigation_cases USING f1='/path/to/data/graph_load/investigation_cases_vertex.csv'"
gsql -g FraudGraph "RUN LOADING JOB load_fraud_patterns USING f1='/path/to/data/graph_load/fraud_patterns_vertex.csv'"

# Load edges
gsql -g FraudGraph "RUN LOADING JOB load_owns_edges USING f1='/path/to/data/graph_load/owns_edges.csv'"
gsql -g FraudGraph "RUN LOADING JOB load_performed_edges USING f1='/path/to/data/graph_load/performed_edges.csv'"
gsql -g FraudGraph "RUN LOADING JOB load_made_edges USING f1='/path/to/data/graph_load/made_edges.csv'"
gsql -g FraudGraph "RUN LOADING JOB load_uses_device_edges USING f1='/path/to/data/graph_load/uses_device_edges.csv'"
gsql -g FraudGraph "RUN LOADING JOB load_billed_to_region_edges USING f1='/path/to/data/graph_load/billed_to_region_edges.csv'"
gsql -g FraudGraph "RUN LOADING JOB load_uses_email_edges USING f1='/path/to/data/graph_load/uses_email_edges.csv'"
gsql -g FraudGraph "RUN LOADING JOB load_closed_case_customer_edges USING f1='/path/to/data/graph_load/closed_case_customer_edges.csv'"
gsql -g FraudGraph "RUN LOADING JOB load_closed_case_card_edges USING f1='/path/to/data/graph_load/closed_case_card_edges.csv'"
gsql -g FraudGraph "RUN LOADING JOB load_closed_case_txn_edges USING f1='/path/to/data/graph_load/closed_case_txn_edges.csv'"
gsql -g FraudGraph "RUN LOADING JOB load_has_pattern_edges USING f1='/path/to/data/graph_load/has_pattern_edges.csv'"
gsql -g FraudGraph "RUN LOADING JOB load_investigation_customer_edges USING f1='/path/to/data/graph_load/investigation_customer_edges.csv'"
gsql -g FraudGraph "RUN LOADING JOB load_investigation_card_edges USING f1='/path/to/data/graph_load/investigation_card_edges.csv'"
gsql -g FraudGraph "RUN LOADING JOB load_investigation_txn_edges USING f1='/path/to/data/graph_load/investigation_txn_edges.csv'"
```

---

## Step 5: Install and Run Queries

```bash
# Install all queries
gsql -g FraudGraph tigergraph/queries/customer_history.gsql
gsql -g FraudGraph tigergraph/queries/transaction_context.gsql
gsql -g FraudGraph tigergraph/queries/connected_entities.gsql
gsql -g FraudGraph tigergraph/queries/prior_cases.gsql
gsql -g FraudGraph tigergraph/queries/temporal_activity.gsql
gsql -g FraudGraph tigergraph/queries/exposure.gsql
gsql -g FraudGraph tigergraph/queries/shared_devices.gsql
gsql -g FraudGraph tigergraph/algorithms/pattern_detection.gsql

# Install (compile) all queries
gsql -g FraudGraph "INSTALL QUERY ALL"

# Test run
gsql -g FraudGraph "RUN QUERY get_customer_history(\"C06075\")"
gsql -g FraudGraph "RUN QUERY calculate_exposure(\"HHG-001\")"
```

---

## Troubleshooting

**Schema already exists**: Drop the graph first: `gsql "DROP GRAPH FraudGraph"`

**Loading job file not found**: TigerGraph needs the file path to be accessible from the TigerGraph server. For Savanna, upload files via the Data Import UI in GraphStudio.

**Query install fails**: Check that the schema is fully deployed before installing queries. Run `gsql "ls"` to see current schema state.

**Connection timeout**: Savanna instances may sleep after inactivity. Wake them from the Savanna dashboard before running queries.

**Memory errors during loading**: Load vertices before edges. Load transactions in batches if needed.
