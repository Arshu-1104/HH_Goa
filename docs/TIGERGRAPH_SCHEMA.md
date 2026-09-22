# TigerGraph Schema — FraudGraph

## Overview

The schema models the fraud investigation domain as a property graph. Every vertex type and edge type is justified by actual columns in the dataset files.

---

## Vertex Types

### 1. Customer
**ID**: `customer_id` (STRING)
**Source**: `customer_id` column in `transactions.csv`
**Justification**: Each transaction has a `customer_id` (e.g. `C06075`). Customers are the primary investigation subjects. All 20 open cases in `case_pack.csv` reference a `customer_id`.

**Attributes**:
| Attribute | Type | Source | Notes |
|---|---|---|---|
| `customer_id` | STRING | transactions.csv | Primary key |
| `first_seen` | STRING | transactions.csv ts | Earliest transaction timestamp |
| `last_seen` | STRING | transactions.csv ts | Most recent transaction timestamp |

---

### 2. Card
**ID**: `card_id` (STRING, e.g. `C12382-K1`)
**Source**: `card_id` column in `case_pack.csv` and `closed_cases_history.csv`
**Justification**: Case pack references specific card IDs per case. Format is `customer_id + "-K" + card_number` (e.g. `C12382-K1`). A customer may have multiple cards (K1, K2, ...).

**Attributes**:
| Attribute | Type | Source | Notes |
|---|---|---|---|
| `card_id` | STRING | case_pack.csv | Primary key |
| `card4` | STRING | transactions.csv | Network: visa/mastercard/discover/amex |
| `card6` | STRING | transactions.csv | Type: debit/credit |
| `card1` | STRING | transactions.csv | Hashed card number |

---

### 3. Transaction
**ID**: `TransactionID` (UINT)
**Source**: `TransactionID` column in `transactions.csv`
**Justification**: Core entity. Every fraud investigation involves specific transactions. `TransactionID` is referenced in `case_pack.flagged_txn_id` and `closed_cases_history.first_fraud_txn_id`.

**Attributes**:
| Attribute | Type | Source | Notes |
|---|---|---|---|
| `TransactionID` | UINT | transactions.csv | Primary key |
| `TransactionDT` | INT | transactions.csv | Integer offset from reference date |
| `TransactionAmt` | DOUBLE | transactions.csv | Transaction amount in USD |
| `ProductCD` | STRING | transactions.csv | W/H/C/R/S product category |
| `card4` | STRING | transactions.csv | Network on this transaction |
| `card6` | STRING | transactions.csv | Card type on this transaction |
| `channel` | STRING | transactions.csv | online/in_person |
| `risk_score` | DOUBLE | transactions.csv | Pre-computed risk score 0–1 |
| `ts` | STRING | transactions.csv | Timestamp string |
| `P_emaildomain` | STRING | transactions.csv | Purchaser email domain |
| `R_emaildomain` | STRING | transactions.csv | Recipient email domain |
| `addr1` | STRING | transactions.csv | Billing region code |
| `addr2` | STRING | transactions.csv | Secondary region code |
| `C1` | DOUBLE | transactions.csv | Count: how many addresses on card |
| `C2` | DOUBLE | transactions.csv | Count: how many cards on address |
| `D1` | DOUBLE | transactions.csv | Days since last transaction |
| `M1` | STRING | transactions.csv | Match flag: name |
| `M2` | STRING | transactions.csv | Match flag: address |
| `M3` | STRING | transactions.csv | Match flag: zip |

---

### 4. DeviceProfile
**ID**: `device_id` (STRING, normalized DeviceInfo)
**Source**: `DeviceInfo` column in `identity.csv`
**Justification**: `identity.csv` contains `DeviceInfo` strings (e.g. `"Samsung SM-G950U Build/R16NW"`). Normalizing and deduplicating these creates device profiles. Shared devices across different customers is a strong fraud signal.

**Attributes**:
| Attribute | Type | Source | Notes |
|---|---|---|---|
| `device_id` | STRING | identity.csv DeviceInfo (normalized) | Primary key |
| `DeviceType` | STRING | identity.csv | mobile/desktop |
| `DeviceInfo` | STRING | identity.csv | Raw DeviceInfo string |
| `os` | STRING | identity.csv id_30 | OS string (e.g. "Android 7.0") |
| `browser` | STRING | identity.csv id_31 | Browser string (e.g. "chrome 62.0") |

---

### 5. Region
**ID**: `region_code` (STRING)
**Source**: `addr1` column in `transactions.csv`
**Justification**: `addr1` contains billing region codes. Out-of-region use is a documented fraud pattern (`out_of_region_use` in closed_cases_history). Modeling regions as vertices enables fast traversal of "transactions in this region" queries.

**Attributes**:
| Attribute | Type | Source | Notes |
|---|---|---|---|
| `region_code` | STRING | transactions.csv addr1 | Primary key |

---

### 6. EmailDomain
**ID**: `domain` (STRING)
**Source**: `P_emaildomain` and `R_emaildomain` in `transactions.csv`
**Justification**: Email domain is a known fraud signal. Multiple customers using the same disposable email domain, or sudden domain changes, indicate account takeover or synthetic identity fraud.

**Attributes**:
| Attribute | Type | Source | Notes |
|---|---|---|---|
| `domain` | STRING | transactions.csv | Primary key |

---

### 7. ClosedCase
**ID**: `case_id` (STRING)
**Source**: `case_id` column in `closed_cases_history.csv`
**Justification**: 5,565 historical closed cases provide the training signal for pattern matching. Similar closed cases inform the agent's recommendations.

**Attributes**:
| Attribute | Type | Source | Notes |
|---|---|---|---|
| `case_id` | STRING | closed_cases_history.csv | Primary key |
| `outcome` | STRING | closed_cases_history.csv | confirmed_fraud/cleared |
| `pattern` | STRING | closed_cases_history.csv | Fraud pattern name |
| `opened_at` | STRING | closed_cases_history.csv | Case open timestamp |
| `closed_at` | STRING | closed_cases_history.csv | Case close timestamp |
| `exposure_usd` | DOUBLE | closed_cases_history.csv | Total exposure in USD |
| `n_txns` | INT | closed_cases_history.csv | Number of transactions in case |
| `actions_taken` | STRING | closed_cases_history.csv | Actions taken (pipe-separated) |
| `analyst_notes` | STRING | closed_cases_history.csv | Free text analyst notes |

---

### 8. InvestigationCase
**ID**: `case_id` (STRING)
**Source**: `case_id` column in `case_pack.csv`
**Justification**: The 20 open cases are the primary work items. Storing them as vertices enables linking to transactions, customers, cards, and similar closed cases.

**Attributes**:
| Attribute | Type | Source | Notes |
|---|---|---|---|
| `case_id` | STRING | case_pack.csv | Primary key |
| `opened_at` | STRING | case_pack.csv | Case open timestamp |
| `trigger_type` | STRING | case_pack.csv | risk_score/customer_report/analyst_request |
| `trigger_text` | STRING | case_pack.csv | Human-readable trigger description |
| `risk_score` | DOUBLE | case_pack.csv | Risk score at time of case opening |

---

### 9. FraudPattern
**ID**: `pattern_name` (STRING)
**Source**: `pattern` column in `closed_cases_history.csv`
**Justification**: 7 distinct fraud patterns in historical data. Modeling patterns as vertices enables "how many cases with this pattern were confirmed fraud?" queries in a single hop.

**Attributes**:
| Attribute | Type | Source | Notes |
|---|---|---|---|
| `pattern_name` | STRING | closed_cases_history.csv | Primary key |
| `description` | STRING | (derived) | Human-readable description |

---

## Edge Types

### Customer -[OWNS]-> Card
**Justification**: Card ID format is `customer_id + "-K" + number`. The customer prefix identifies card ownership. A customer can own multiple cards.

### Card -[MADE]-> Transaction
**Justification**: Each transaction has a `customer_id`; combining with the card's `customer_id` prefix links card to transaction. Card-level transaction history is key for card-not-present fraud.

**⚠️ DATA LIMITATION — THIS EDGE IS CURRENTLY EMPTY**

`transactions.csv` does NOT contain a `card_id` column — only a `customer_id` column.  
A customer can own multiple cards (K1, K2, …).  There is NO data-supported way to determine which specific card was used for a given transaction.

**Decision**: The `MADE` edge type exists in the schema for future use when actual per-transaction card data is available.  Currently, `made_edges.csv` is header-only (zero rows).  Do NOT infer the card by assigning every transaction to the customer's first card — this would be factually wrong and damage fraud-ring analysis.

**Graph representation**:
- `Customer -[PERFORMED]-> Transaction` ✓ (fully populated — data-supported)
- `Customer -[OWNS]-> Card` ✓ (fully populated — data-supported)
- `Card -[MADE]-> Transaction` ✗ Empty — **no data to support this mapping**

### Customer -[PERFORMED]-> Transaction
**Justification**: Direct customer-to-transaction edge enables fast "all transactions by this customer" queries without traversing cards. The `customer_id` field on each transaction makes this explicit.

### Transaction -[USES_DEVICE]-> DeviceProfile
**Justification**: `identity.csv` joins on `TransactionID`. Every transaction with an identity record has a `DeviceInfo`. Device sharing across transactions is a strong card-not-present fraud signal.

### Transaction -[BILLED_TO_REGION]-> Region
**Justification**: `addr1` on each transaction is a billing region code. Out-of-region use pattern requires traversing region→transactions.

### Transaction -[USES_EMAIL]-> EmailDomain
**Justification**: `P_emaildomain` links the transaction to an email domain vertex. Shared disposable domains across customers indicate synthetic identities.

### ClosedCase -[INVOLVES_CUSTOMER]-> Customer
**Justification**: `customer_id` on `closed_cases_history` directly links the case to the customer.

### ClosedCase -[INVOLVES_CARD]-> Card
**Justification**: `card_id` on `closed_cases_history` links the historical case to the specific card used.

### ClosedCase -[FLAGGED_TRANSACTION]-> Transaction
**Justification**: `first_fraud_txn_id` and `txn_ids` on `closed_cases_history` identify the specific fraudulent transactions. Multiple transactions can be flagged per case.

### ClosedCase -[HAS_PATTERN]-> FraudPattern
**Justification**: `pattern` column on `closed_cases_history` identifies the fraud pattern. This edge enables "all cases with this pattern" traversals.

### InvestigationCase -[ABOUT_CUSTOMER]-> Customer
**Justification**: `customer_id` on `case_pack` identifies the subject of investigation.

### InvestigationCase -[INVOLVES_CARD]-> Card
**Justification**: `card_id` on `case_pack` identifies the specific card under investigation.

### InvestigationCase -[FLAGGED_TRANSACTION]-> Transaction
**Justification**: `flagged_txn_id` on `case_pack` identifies the triggering transaction.

### InvestigationCase -[SIMILAR_TO]-> ClosedCase
**Justification**: Similarity matching between open and closed cases enables the agent to cite precedents. The `similarity_score` attribute (DOUBLE) quantifies pattern/customer/card overlap.

**Attributes on SIMILAR_TO**:
| Attribute | Type | Notes |
|---|---|---|
| `similarity_score` | DOUBLE | Computed similarity 0.0–1.0 |
