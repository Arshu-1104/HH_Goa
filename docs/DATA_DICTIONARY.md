# Data Dictionary — FraudGraph Investigator

All facts derived from actual dataset inspection. No invented field meanings.

---

## transactions.csv — 590,742 rows, 397 columns

### Core Transaction Fields

| Column | Type | Meaning | Missingness | Graph Usage |
|---|---|---|---|---|
| `TransactionID` | INT | Unique transaction identifier | 0% | Transaction vertex primary key |
| `TransactionDT` | INT | Integer offset from reference date (seconds) | 0% | Transaction vertex attribute; used for temporal queries |
| `TransactionAmt` | FLOAT | Transaction amount in USD | 0% | Transaction vertex attribute; used in exposure calculation |
| `ProductCD` | STRING | Product category: W/H/C/R/S | 0% | Transaction vertex attribute |

**ProductCD values**: W (75.6%), H (10.3%), C (8.2%), R (3.5%), S (2.4%)

### Card Metadata Fields

| Column | Type | Meaning | Missingness | Graph Usage |
|---|---|---|---|---|
| `card1` | STRING | Hashed card number | ~0% | Card vertex attribute (card1) |
| `card2` | FLOAT | Numeric card metadata | ~1% | Not used in primary queries |
| `card3` | FLOAT | Numeric card metadata | ~1% | Not used in primary queries |
| `card4` | STRING | Card network: visa/mastercard/discover/amex | ~0% | Transaction and Card vertex attribute |
| `card5` | FLOAT | Numeric card metadata | ~1% | Not used in primary queries |
| `card6` | STRING | Card type: debit/credit | ~0% | Transaction and Card vertex attribute |

**⚠️ IMPORTANT — NO card_id in transactions.csv**

`transactions.csv` does NOT contain a `card_id` column.  The card fields (`card1`–`card6`) are attributes about the card used in the transaction but do NOT identify the specific card by its ID (e.g. `C12382-K1`).

This means:
- A `Card -[MADE]-> Transaction` relationship **cannot** be reliably constructed from the data.
- Assigning every transaction to the customer's "first" card would be factually wrong.
- The graph only populates `Customer -[PERFORMED]-> Transaction` and `Customer -[OWNS]-> Card`.
- The `MADE` edge type remains in the schema for future use if per-transaction card data becomes available.

**card4 values**: visa (most common), mastercard, discover, amex
**card6 values**: debit (75.6%), credit (24.4%)

### Address / Location Fields

| Column | Type | Meaning | Missingness | Graph Usage |
|---|---|---|---|---|
| `addr1` | FLOAT | Billing region code (numeric) | ~11% | Region vertex key; BILLED_TO_REGION edge |
| `addr2` | FLOAT | Secondary region code (country/state) | ~11% | Transaction vertex attribute |
| `dist1` | FLOAT | Distance between billing and transaction location | ~65% | Not used (high missingness) |
| `dist2` | FLOAT | Distance metric variant | ~95% | Not used (too sparse) |

### Email Domain Fields

| Column | Type | Meaning | Missingness | Graph Usage |
|---|---|---|---|---|
| `P_emaildomain` | STRING | Purchaser email domain (e.g. gmail.com) | ~24% | EmailDomain vertex; USES_EMAIL edge |
| `R_emaildomain` | STRING | Recipient email domain | ~60% | EmailDomain vertex (secondary) |

### Count Feature Fields (C1–C14)

| Column | Type | Meaning | Missingness | Graph Usage |
|---|---|---|---|---|
| `C1` | FLOAT | Number of addresses on card | ~0% | Transaction vertex attribute |
| `C2` | FLOAT | Number of cards on address | ~0% | Transaction vertex attribute |
| `C3` | FLOAT | Count feature (exact meaning undocumented) | ~0% | Not used |
| `C4` | FLOAT | Count feature | ~0% | Not used |
| `C5` | FLOAT | Count feature | ~0% | Not used |
| `C6` | FLOAT | Count feature | ~0% | Not used |
| `C7` | FLOAT | Count feature | ~0% | Not used |
| `C8` | FLOAT | Count feature | ~0% | Not used |
| `C9` | FLOAT | Number of days address on file | ~0% | Not used |
| `C10` | FLOAT | Count feature | ~0% | Not used |
| `C11` | FLOAT | Count feature | ~0% | Not used |
| `C12` | FLOAT | Count feature | ~0% | Not used |
| `C13` | FLOAT | Count feature | ~0% | Not used |
| `C14` | FLOAT | Count feature | ~0% | Not used |

### Timedelta Fields (D1–D15)

| Column | Type | Meaning | Missingness | Graph Usage |
|---|---|---|---|---|
| `D1` | FLOAT | Days since last transaction | ~70% | Transaction vertex attribute (D1) |
| `D2` | FLOAT | Days since last transaction (variant) | ~76% | Not used |
| `D3` | FLOAT | Timedelta feature | ~89% | Not used |
| `D4` | FLOAT | Timedelta feature | ~79% | Not used |
| `D5` | FLOAT | Timedelta feature | ~92% | Not used |
| `D6` | FLOAT | Timedelta feature | ~97% | Not used (too sparse) |
| `D7` | FLOAT | Timedelta feature | ~97% | Not used (too sparse) |
| `D8` | FLOAT | Timedelta feature | ~93% | Not used |
| `D9` | FLOAT | Timedelta feature | ~93% | Not used |
| `D10` | FLOAT | Timedelta feature | ~88% | Not used |
| `D11` | FLOAT | Timedelta feature | ~75% | Not used |
| `D12` | FLOAT | Timedelta feature | ~97% | Not used (too sparse) |
| `D13` | FLOAT | Timedelta feature | ~97% | Not used (too sparse) |
| `D14` | FLOAT | Timedelta feature | ~97% | Not used (too sparse) |
| `D15` | FLOAT | Timedelta feature | ~84% | Not used |

### Match Flag Fields (M1–M9)

| Column | Type | Meaning | Missingness | Graph Usage |
|---|---|---|---|---|
| `M1` | STRING | Name match flag: T/F | ~63% | Transaction vertex attribute |
| `M2` | STRING | Address match flag: T/F | ~63% | Transaction vertex attribute |
| `M3` | STRING | Zip match flag: T/F | ~63% | Transaction vertex attribute |
| `M4` | STRING | Match flag (M0/M1/M2) | ~61% | Not used |
| `M5` | STRING | Match flag: T/F/M0/M1/M2 | ~66% | Not used |
| `M6` | STRING | Match flag: T/F | ~60% | Not used |
| `M7` | STRING | Match flag: T/F | ~78% | Not used |
| `M8` | STRING | Match flag: T/F | ~78% | Not used |
| `M9` | STRING | Match flag: T/F | ~78% | Not used |

### Engineered Feature Fields (V1–V339)

| Column | Type | Meaning | Missingness | Graph Usage |
|---|---|---|---|---|
| `V1`–`V339` | FLOAT | Vesta-engineered ranking/count features | Variable (many 50–99%) | Not used in primary queries. Loaded to Transaction vertex as optional enrichment if needed. |

### Customer / Channel Fields

| Column | Type | Meaning | Missingness | Graph Usage |
|---|---|---|---|---|
| `customer_id` | STRING | Customer identifier (e.g. C06075) | 0% | Customer vertex primary key |
| `ts` | STRING | Transaction timestamp (e.g. "2016-07-02 00:02:21") | 0% | Customer first_seen/last_seen |
| `channel` | STRING | Transaction channel: online/in_person | 0% | Transaction vertex attribute |
| `risk_score` | FLOAT | Pre-computed risk score 0.0–1.0 | ~0% | Transaction vertex attribute |

---

## identity.csv — 144,432 rows, 41 columns

| Column | Type | Meaning | Missingness | Graph Usage |
|---|---|---|---|---|
| `TransactionID` | INT | Join key to transactions.csv | 0% | Links Transaction → DeviceProfile |
| `id_01` | FLOAT | Identity feature | ~0% | Not used |
| `id_02` | FLOAT | Identity feature | ~0% | Not used |
| `id_03` | FLOAT | Identity feature | ~82% | Not used (too sparse) |
| `id_04` | FLOAT | Identity feature | ~82% | Not used (too sparse) |
| `id_05` | FLOAT | Identity feature | ~63% | Not used |
| `id_06` | FLOAT | Identity feature | ~63% | Not used |
| `id_07` | FLOAT | Identity feature | ~82% | Not used (too sparse) |
| `id_08` | FLOAT | Identity feature | ~82% | Not used (too sparse) |
| `id_09` | FLOAT | Identity feature | ~46% | Not used |
| `id_10` | FLOAT | Identity feature | ~46% | Not used |
| `id_11` | FLOAT | Identity feature | ~0% | Not used |
| `id_12` | STRING | NotFound/Found flag | ~0% | Not used directly |
| `id_13` | FLOAT | Identity feature | ~28% | Not used |
| `id_14` | FLOAT | Identity feature | ~52% | Not used |
| `id_15` | STRING | Found/New/Unknown — likely address/email match status | ~0% | DeviceProfile attribute context |
| `id_16` | STRING | NotFound/Found flag | ~0% | Not used directly |
| `id_17` | FLOAT | Identity feature | ~0% | Not used |
| `id_18` | FLOAT | Identity feature | ~96% | Not used (too sparse) |
| `id_19` | FLOAT | Identity feature | ~0% | Not used |
| `id_20` | FLOAT | Identity feature | ~0% | Not used |
| `id_21` | FLOAT | Identity feature | ~82% | Not used (too sparse) |
| `id_22` | FLOAT | Identity feature | ~82% | Not used (too sparse) |
| `id_23` | FLOAT | Identity feature | ~82% | Not used (too sparse) |
| `id_24` | FLOAT | Identity feature | ~82% | Not used (too sparse) |
| `id_25` | FLOAT | Identity feature | ~55% | Not used |
| `id_26` | FLOAT | Identity feature | ~55% | Not used |
| `id_27` | STRING | NotFound/Found flag | ~55% | Not used |
| `id_28` | STRING | Found/New — whether device was seen before | ~0% | DeviceProfile novelty signal |
| `id_29` | STRING | NotFound/Found flag | ~55% | Not used |
| `id_30` | STRING | OS string (e.g. "Android 7.0", "iOS 11.1.2") | ~0% | DeviceProfile.os attribute |
| `id_31` | STRING | Browser string (e.g. "chrome 62.0", "safari generic") | ~0% | DeviceProfile.browser attribute |
| `id_32` | FLOAT | Screen resolution or similar | ~60% | Not used |
| `id_33` | STRING | Screen resolution string | ~60% | Not used |
| `id_34` | STRING | Identity string feature | ~60% | Not used |
| `id_35` | STRING | T/F flag | ~0% | Not used |
| `id_36` | STRING | T/F flag | ~0% | Not used |
| `id_37` | STRING | T/F flag | ~0% | Not used |
| `id_38` | STRING | T/F flag | ~0% | Not used |
| `DeviceType` | STRING | mobile/desktop | ~0% | DeviceProfile.DeviceType attribute |
| `DeviceInfo` | STRING | Device+OS+browser string (e.g. "Samsung SM-G950U Build/R16NW") | ~0% | DeviceProfile primary key (normalized) |

---

## case_pack.csv — 20 rows

| Column | Type | Meaning | Missingness | Graph Usage |
|---|---|---|---|---|
| `case_id` | STRING | Case identifier (HHG-001 to HHG-020) | 0% | InvestigationCase vertex primary key |
| `opened_at` | STRING | Timestamp when case was opened | 0% | InvestigationCase.opened_at |
| `trigger_type` | STRING | What triggered the case: risk_score/customer_report/analyst_request | 0% | InvestigationCase.trigger_type |
| `trigger_text` | STRING | Human-readable trigger description | 0% | InvestigationCase.trigger_text |
| `flagged_txn_id` | STRING | TransactionID of the triggering transaction | 0% | FLAGGED_TRANSACTION edge target |
| `card_id` | STRING | Card under investigation (e.g. C12382-K1) | 0% | Card vertex key; INVOLVES_CARD edge |
| `customer_id` | STRING | Customer under investigation | 0% | Customer vertex key; ABOUT_CUSTOMER edge |
| `risk_score` | FLOAT | Risk score at case opening | 0% | InvestigationCase.risk_score |

**Trigger type distribution**: risk_score (11), customer_report (8), analyst_request (1)

---

## closed_cases_history.csv — 5,565 rows

| Column | Type | Meaning | Missingness | Graph Usage |
|---|---|---|---|---|
| `case_id` | STRING | Historical case identifier | 0% | ClosedCase vertex primary key |
| `customer_id` | STRING | Customer subject of the case | 0% | INVOLVES_CUSTOMER edge target |
| `card_id` | STRING | Card involved in the case | 0% | INVOLVES_CARD edge target |
| `opened_at` | STRING | Case open timestamp | 0% | ClosedCase.opened_at |
| `closed_at` | STRING | Case close timestamp | 0% | ClosedCase.closed_at |
| `outcome` | STRING | confirmed_fraud/cleared | 0% | ClosedCase.outcome |
| `pattern` | STRING | Fraud pattern classification | 0% | HAS_PATTERN edge; FraudPattern vertex |
| `first_fraud_txn_id` | STRING | TransactionID of first confirmed fraud transaction | ~16% | FLAGGED_TRANSACTION edge target |
| `txn_ids` | STRING | Pipe-separated list of all transaction IDs in case | 0% | FLAGGED_TRANSACTION edges |
| `n_txns` | INT | Number of transactions in the case | 0% | ClosedCase.n_txns |
| `exposure_usd` | FLOAT | Total USD exposure | 0% | ClosedCase.exposure_usd |
| `connected_card_ids` | STRING | Related card IDs (pipe-separated) | ~99% | Not reliably usable (too sparse) |
| `actions_taken` | STRING | Actions taken (pipe-separated): CREATE_CASE\|BLOCK_CARD\|FILE_REPORT\|VERIFY_WITH_CUSTOMER\|CLOSE_NO_FRAUD | 0% | ClosedCase.actions_taken |
| `report_filed` | STRING | Whether a report was filed | 0% | Not used directly |
| `analyst_notes` | STRING | Free text analyst notes | ~0% | ClosedCase.analyst_notes |

**Outcome distribution**: confirmed_fraud (4,665 / 83.8%), cleared (900 / 16.2%)

**Pattern distribution**:
| Pattern | Count | % |
|---|---|---|
| card_not_present_fraud | 1,404 | 25.2% |
| account_takeover | 1,205 | 21.7% |
| card_not_present_new_device | 1,076 | 19.3% |
| out_of_region_use | 955 | 17.2% |
| none (cleared) | 900 | 16.2% |
| card_testing | 16 | 0.3% |
| undocumented | 9 | 0.2% |

**Actions distribution**:
| Actions | Count |
|---|---|
| CREATE_CASE\|BLOCK_CARD | 4,268 |
| VERIFY_WITH_CUSTOMER\|CLOSE_NO_FRAUD | 900 |
| CREATE_CASE\|BLOCK_CARD\|FILE_REPORT | 397 |
