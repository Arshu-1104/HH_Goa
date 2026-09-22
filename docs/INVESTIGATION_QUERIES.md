# Investigation Queries — FraudGraph GSQL

All queries are installed on the FraudGraph TigerGraph graph. Each query is callable via pyTigerGraph or the MCP server.

---

## 1. get_customer_history

**File**: `tigergraph/queries/customer_history.gsql`
**Purpose**: Returns a full investigation summary for a customer, including all transactions, cards, devices, prior closed cases, and recent activity. This is the first query the agent runs when investigating any case.

**Inputs**:
| Parameter | Type | Description |
|---|---|---|
| `customer_id` | STRING | Customer identifier (e.g. `C06075`) |

**Outputs**: Aggregated summary:
- Total transaction count and date range
- Transaction channel breakdown (online/in_person)
- Transaction amount stats (min, max, sum, avg)
- Distinct regions visited
- Email domains used
- Cards linked to this customer
- Devices used
- Prior closed cases (outcome, pattern, exposure)
- Recent transactions (last 30 days by TransactionDT relative to latest)

**How the agent uses it**: First call after case trigger. Establishes baseline customer behavior. Anomalies relative to this baseline inform the investigation hypothesis.

**Example output JSON shape**:
```json
{
  "customer_id": "C06075",
  "transaction_count": 47,
  "date_range": {"first_dt": 86400, "last_dt": 15552000},
  "channels": {"online": 12, "in_person": 35},
  "amount_stats": {"min": 12.50, "max": 892.00, "sum": 8432.75, "avg": 179.42},
  "regions": ["315", "402", "229"],
  "email_domains": ["gmail.com", "yahoo.com"],
  "cards": [
    {"card_id": "C06075-K1", "card4": "visa", "card6": "debit"}
  ],
  "devices": [
    {"device_id": "samsung_android_7_chrome", "DeviceType": "mobile"}
  ],
  "prior_cases": [
    {
      "case_id": "CHC-1234",
      "outcome": "confirmed_fraud",
      "pattern": "card_not_present_fraud",
      "closed_at": "2019-03-15",
      "exposure_usd": 450.00,
      "actions_taken": "CREATE_CASE|BLOCK_CARD"
    }
  ],
  "recent_transactions": [
    {
      "TransactionID": 2987432,
      "TransactionAmt": 250.00,
      "ProductCD": "W",
      "channel": "online",
      "risk_score": 0.82
    }
  ]
}
```

---

## 2. get_transaction_context

**File**: `tigergraph/queries/transaction_context.gsql`
**Purpose**: Returns full context for a specific transaction, including the customer, card, device, region, and surrounding transactions by the same customer within ±7 days. Also returns any closed cases that involved this transaction.

**Inputs**:
| Parameter | Type | Description |
|---|---|---|
| `txn_id` | UINT | TransactionID |

**Outputs**:
- Transaction attributes
- Customer info
- Card info
- Device/identity info (if available in identity.csv)
- Region
- Surrounding transactions (±7 days by TransactionDT)
- Closed cases involving this transaction

**How the agent uses it**: Run on the flagged transaction from the case. Reveals whether the device is new, the region is unusual, the email domain changed, or multiple transactions occurred in a short window.

**Example output JSON shape**:
```json
{
  "transaction": {
    "TransactionID": 2987432,
    "TransactionAmt": 250.00,
    "TransactionDT": 15552000,
    "ProductCD": "W",
    "card4": "visa",
    "card6": "debit",
    "channel": "online",
    "risk_score": 0.82,
    "P_emaildomain": "gmail.com",
    "addr1": "315",
    "ts": "2019-02-20 14:32:11"
  },
  "customer": {"customer_id": "C06075"},
  "card": {"card_id": "C06075-K1", "card4": "visa", "card6": "debit"},
  "device": {
    "device_id": "iphone_ios_12_safari",
    "DeviceType": "mobile",
    "os": "iOS 12.0",
    "browser": "safari generic",
    "is_new_device": true
  },
  "region": "315",
  "surrounding_transactions": [
    {
      "TransactionID": 2987411,
      "TransactionAmt": 1.00,
      "TransactionDT": 15551900,
      "channel": "online",
      "risk_score": 0.75
    }
  ],
  "involved_in_cases": []
}
```

---

## 3. find_connected_entities

**File**: `tigergraph/queries/connected_entities.gsql`
**Purpose**: Multi-hop traversal from a flagged transaction to find all connected entities — cards sharing a device, customers sharing a device, related prior cases. Used to detect fraud rings.

**Inputs**:
| Parameter | Type | Description |
|---|---|---|
| `txn_id` | UINT | TransactionID |
| `max_hops` | INT | Maximum traversal depth (1–3 recommended) |

**Outputs**:
- Connected cards (via shared device, shared region, or shared email domain)
- Connected customers (via shared cards or devices)
- Shared devices across transactions
- Related prior cases

**How the agent uses it**: Detect fraud rings. If 5 different customers all used the same device, that's a strong account takeover signal.

**Example output JSON shape**:
```json
{
  "source_txn_id": 2987432,
  "connected_cards": [
    {"card_id": "C07821-K1", "connection_type": "shared_device", "hops": 2}
  ],
  "connected_customers": [
    {"customer_id": "C07821", "connection_type": "shared_device", "hops": 2}
  ],
  "shared_devices": [
    {
      "device_id": "iphone_ios_12_safari",
      "transaction_count": 3,
      "customer_count": 2
    }
  ],
  "related_cases": []
}
```

---

## 4. find_prior_cases

**File**: `tigergraph/queries/prior_cases.gsql`
**Purpose**: Retrieve historical closed cases relevant to the current investigation. Matches by customer, card, and/or fraud pattern. Returns case details, outcome, actions taken, and analyst notes.

**Inputs**:
| Parameter | Type | Description |
|---|---|---|
| `customer_id` | STRING | Customer to search for (can be empty) |
| `card_id` | STRING | Card to search for (can be empty) |
| `pattern` | STRING | Fraud pattern to search for (can be empty) |

**Outputs**:
- List of matching closed cases with full details

**How the agent uses it**: Find precedents. If this customer previously had a confirmed card_not_present_fraud case that was resolved by BLOCK_CARD, the agent should weight that action more heavily.

**Example output JSON shape**:
```json
{
  "customer_id": "C06075",
  "card_id": "C06075-K1",
  "pattern": "card_not_present_fraud",
  "matching_cases": [
    {
      "case_id": "CHC-1234",
      "match_reason": "customer_id",
      "outcome": "confirmed_fraud",
      "pattern": "card_not_present_fraud",
      "opened_at": "2019-01-10",
      "closed_at": "2019-03-15",
      "exposure_usd": 450.00,
      "n_txns": 3,
      "actions_taken": "CREATE_CASE|BLOCK_CARD",
      "analyst_notes": "Customer reported unauthorized online purchases."
    }
  ]
}
```

---

## 5. detect_temporal_patterns

**File**: `tigergraph/queries/temporal_activity.gsql`
**Purpose**: Analyze transaction sequences for time-based fraud signals: rapid-fire transactions (burst), repeated small amounts (card testing), rapid region changes, out-of-hours activity.

**Inputs**:
| Parameter | Type | Description |
|---|---|---|
| `customer_id` | STRING | Customer to analyze |
| `window_hours` | INT | Time window in hours for burst detection (e.g. 24) |

**Outputs**:
- Burst sequences (transactions within short window)
- Repeated amounts (potential card testing)
- Region changes within window
- Out-of-hours transaction counts

**How the agent uses it**: Card testing involves many small transactions in rapid succession. Burst activity combined with new device = account takeover signal.

**Example output JSON shape**:
```json
{
  "customer_id": "C06075",
  "window_hours": 24,
  "burst_sequences": [
    {
      "start_dt": 15551800,
      "end_dt": 15552100,
      "transaction_count": 5,
      "total_amount": 15.00,
      "transactions": [2987401, 2987411, 2987420, 2987430, 2987432]
    }
  ],
  "repeated_amounts": [
    {"amount": 1.00, "count": 4, "flag": "possible_card_testing"}
  ],
  "region_changes": [
    {"from_region": "315", "to_region": "402", "dt_delta": 300, "flag": "rapid_region_change"}
  ],
  "out_of_hours_count": 3
}
```

---

## 6. calculate_exposure

**File**: `tigergraph/queries/exposure.gsql`
**Purpose**: Calculate the total USD exposure for a given investigation case by summing transaction amounts for all flagged transactions. Fully deterministic — no LLM involved.

**Inputs**:
| Parameter | Type | Description |
|---|---|---|
| `case_id` | STRING | Case identifier (from case_pack or closed_cases_history) |

**Outputs**:
- Total exposure amount (Decimal precision)
- Count of flagged transactions
- Individual transaction amounts

**How the agent uses it**: Include in recommendations. "Blocking this card would protect $892 in exposure from 3 flagged transactions."

**Example output JSON shape**:
```json
{
  "case_id": "HHG-001",
  "total_exposure_usd": 892.50,
  "flagged_transaction_count": 3,
  "transactions": [
    {"TransactionID": 2987432, "amount": 250.00},
    {"TransactionID": 2987450, "amount": 450.00},
    {"TransactionID": 2987480, "amount": 192.50}
  ]
}
```

---

## 7. find_shared_devices

**File**: `tigergraph/queries/shared_devices.gsql`
**Purpose**: Find all transactions that share the same DeviceProfile as the given transaction. Returns associated customer IDs and card IDs. A device shared by multiple customers is a strong fraud ring indicator.

**Inputs**:
| Parameter | Type | Description |
|---|---|---|
| `txn_id` | UINT | TransactionID to start from |

**Outputs**:
- DeviceProfile for the transaction
- All other transactions using the same device
- Customer IDs and card IDs for those transactions

**How the agent uses it**: If a device was used by 10 different customers, it's likely a compromised/shared device used by fraudsters.

**Example output JSON shape**:
```json
{
  "source_txn_id": 2987432,
  "device": {
    "device_id": "iphone_ios_12_safari",
    "DeviceType": "mobile",
    "os": "iOS 12.0",
    "browser": "safari generic"
  },
  "sharing_transactions": [
    {
      "TransactionID": 2901234,
      "customer_id": "C07821",
      "card_id": "C07821-K1",
      "TransactionAmt": 150.00,
      "channel": "online"
    }
  ],
  "total_customers_on_device": 2,
  "total_transactions_on_device": 4
}
```

---

## 8. detect_fraud_clusters (Algorithm)

**File**: `tigergraph/algorithms/pattern_detection.gsql`
**Purpose**: Graph-level algorithm that finds clusters of transactions connected through shared devices or regions. Uses connected component analysis to identify fraud rings.

**Inputs**: None (runs on full graph)

**Outputs**:
- Cluster assignments for transactions
- Cluster size distribution
- Clusters with multiple customers (potential fraud rings)

**How the agent uses it**: Background knowledge. "This transaction belongs to cluster #47 which contains 15 transactions across 8 customers — previously linked to card_not_present_fraud."

**Example output JSON shape**:
```json
{
  "total_clusters": 1240,
  "suspicious_clusters": [
    {
      "cluster_id": 47,
      "transaction_count": 15,
      "customer_count": 8,
      "device_count": 2,
      "dominant_pattern": "card_not_present_fraud",
      "transactions": [2987432, 2901234, ...]
    }
  ]
}
```
