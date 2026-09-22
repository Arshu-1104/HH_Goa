"""
mock_client.py — CSV-based mock client for FraudGraph MCP server.

Provides the same interface as TigerGraphClient but reads directly from
the CSV files.  No TigerGraph or network connection required.

MEMORY STRATEGY
---------------
transactions.csv has 590,742 rows × 397 columns (~800 MB uncompressed).

Instead of csv.DictReader (which builds a 397-key dict per row), we use
iter_selected_csv_columns() which:
  1. Reads the CSV header once to find column positions.
  2. Uses csv.reader (returns a plain list per row).
  3. Slices only the required positions.
  4. Yields a small dict with only the needed columns.

This avoids creating the 397-key intermediate dict entirely.

Three indexes are built in one pass over transactions.csv:
  _txn_index        : TransactionID → slim row dict
  _customer_txn_idx : customer_id  → [TransactionID, ...]

identity.csv (144k rows × 41 cols) is loaded with selective column
reading — only 5 columns kept.  Additionally a device→customers inverted
index is built so find_shared_devices() never rescans all 144k rows.

Closed-case history and case-pack are small and loaded entirely.

No full 397-column dataset is ever held in RAM simultaneously.
"""

import csv
import re
import os
import logging
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Iterator

from mcp.server.device_utils import normalize_device_info
from mcp.server.csv_utils import iter_selected_csv_columns

log = logging.getLogger(__name__)

DATA_DIR = Path(os.environ.get("DATA_DIR", Path(__file__).parent.parent.parent))

# ── Minimal column set loaded from transactions.csv ───────────────────────────
# Only these columns are kept in the in-memory index.
# Do NOT add V-feature columns here.
SLIM_COLS: tuple[str, ...] = (
    "TransactionID",
    "TransactionDT",
    "TransactionAmt",
    "ProductCD",
    "card4",
    "card6",
    "channel",
    "risk_score",
    "ts",
    "P_emaildomain",
    "R_emaildomain",
    "addr1",
    "C1",
    "C2",
    "D1",
    "M1",
    "M2",
    "M3",
    "customer_id",
)

# ── Minimal identity columns ──────────────────────────────────────────────────
IDENTITY_COLS: tuple[str, ...] = (
    "TransactionID",
    "DeviceType",
    "DeviceInfo",
    "id_30",   # OS string
    "id_31",   # Browser string
)

# ── Timestamp helpers ─────────────────────────────────────────────────────────
_TS_FMT = "%Y-%m-%d %H:%M:%S"


def _parse_ts(ts_str: str) -> datetime | None:
    """Parse an ISO-format ts string to datetime.  Returns None on failure."""
    try:
        return datetime.strptime(ts_str.strip(), _TS_FMT)
    except (ValueError, AttributeError):
        return None


# ── CSV helpers ───────────────────────────────────────────────────────────────

def _iter_csv(path: Path, limit: int | None = None) -> Iterator[dict[str, str]]:
    """Full-row DictReader — use only for small files (case_pack, closed_cases)."""
    if not path.exists():
        log.warning(f"CSV not found: {path}")
        return
    with open(path, encoding="utf-8", errors="replace") as f:
        reader = csv.DictReader(f)
        for i, row in enumerate(reader):
            if limit is not None and i >= limit:
                return
            yield row


def _load_csv(path: Path, limit: int | None = None) -> list[dict[str, str]]:
    return list(_iter_csv(path, limit=limit))


def _safe_float(value: str, default: float = 0.0) -> float:
    try:
        return float(value) if value else default
    except (ValueError, TypeError):
        return default


# ── MockClient ────────────────────────────────────────────────────────────────

class MockClient:
    """
    CSV-backed mock for all MCP tool data sources.

    Indexes are built lazily on first use and then cached.
    Only SLIM_COLS columns are ever loaded from transactions.csv.
    Uses iter_selected_csv_columns() — no 397-key dict per row is created.
    """

    def __init__(self, data_dir: Path | None = None) -> None:
        self._data_dir = data_dir or DATA_DIR

        # TransactionID (str) → slim row dict
        self._txn_index: dict[str, dict[str, str]] | None = None

        # customer_id (str) → list[TransactionID str]  (inverted index)
        self._customer_txn_idx: dict[str, list[str]] | None = None

        # TransactionID → minimal identity dict (only IDENTITY_COLS)
        self._identity_index: dict[str, dict[str, str]] | None = None

        # device_id (canonical) → set[customer_id]  (inverted device index)
        # Only real devices (normalize_device_info != None) are included.
        self._device_customer_idx: dict[str, set[str]] | None = None

        # case_id → case_pack row
        self._cases_index: dict[str, dict[str, str]] | None = None

        # case_pack rows list
        self._case_pack: list[dict[str, str]] | None = None

        # customer_id → list[closed_case row]
        self._history_index: dict[str, list[dict[str, str]]] | None = None

        log.info(f"MockClient initialised — data_dir={self._data_dir}")

    # ── Lazy index builders ────────────────────────────────────────────────

    def _build_txn_indexes(self) -> None:
        """
        Single-pass load of transactions.csv using the efficient column reader.

        Builds _txn_index and _customer_txn_idx simultaneously.
        Only SLIM_COLS columns are stored.  The 397-key intermediate dict
        is never created.
        """
        if self._txn_index is not None:
            return

        log.info("MockClient: building transaction indexes (slim columns, fast reader) …")
        path = self._data_dir / "transactions.csv"
        txn_index: dict[str, dict[str, str]] = {}
        cust_idx: dict[str, list[str]] = {}

        for row in iter_selected_csv_columns(path, SLIM_COLS):
            tid = row.get("TransactionID", "").strip()
            if not tid:
                continue
            txn_index[tid] = row
            cid = row.get("customer_id", "").strip()
            if cid:
                cust_idx.setdefault(cid, []).append(tid)

        self._txn_index = txn_index
        self._customer_txn_idx = cust_idx
        log.info(
            f"MockClient: {len(txn_index):,} transactions indexed "
            f"({len(cust_idx):,} customers)"
        )

    def _build_identity_indexes(self) -> None:
        """
        Load identity.csv (selected columns only) and build:
          _identity_index        : TransactionID → identity row
          _device_customer_idx   : canonical device_id → set[customer_id]

        The device→customer index avoids rescanning 144k rows on every
        find_shared_devices() call.
        """
        if self._identity_index is not None:
            return

        log.info("MockClient: loading identity.csv (selected columns) …")
        path = self._data_dir / "identity.csv"
        txn_index = self._get_txn_index()  # needed to resolve customer_id

        identity_idx: dict[str, dict[str, str]] = {}
        device_cust: dict[str, set[str]] = {}

        for row in iter_selected_csv_columns(path, IDENTITY_COLS):
            tid = row.get("TransactionID", "").strip()
            if not tid:
                continue
            identity_idx[tid] = row

            # Build device→customers index
            raw_dev = row.get("DeviceInfo", "")
            canon = normalize_device_info(raw_dev)
            if canon is None:
                # Missing device — do NOT add to shared-device index
                continue
            # Resolve customer from txn_index
            txn_row = txn_index.get(tid, {})
            cid = txn_row.get("customer_id", "").strip()
            if cid:
                device_cust.setdefault(canon, set()).add(cid)

        self._identity_index = identity_idx
        self._device_customer_idx = device_cust
        log.info(
            f"MockClient: {len(identity_idx):,} identity records indexed, "
            f"{len(device_cust):,} canonical devices"
        )

    def _get_txn_index(self) -> dict[str, dict[str, str]]:
        self._build_txn_indexes()
        return self._txn_index  # type: ignore[return-value]

    def _get_customer_txn_idx(self) -> dict[str, list[str]]:
        self._build_txn_indexes()
        return self._customer_txn_idx  # type: ignore[return-value]

    def _get_identity_index(self) -> dict[str, dict[str, str]]:
        self._build_identity_indexes()
        return self._identity_index  # type: ignore[return-value]

    def _get_device_customer_idx(self) -> dict[str, set[str]]:
        self._build_identity_indexes()
        return self._device_customer_idx  # type: ignore[return-value]

    def _get_case_pack(self) -> list[dict[str, str]]:
        if self._case_pack is None:
            path = self._data_dir / "case_pack.csv"
            self._case_pack = _load_csv(path)
        return self._case_pack

    def _get_cases_index(self) -> dict[str, dict[str, str]]:
        if self._cases_index is None:
            self._cases_index = {
                row["case_id"]: row
                for row in self._get_case_pack()
                if row.get("case_id")
            }
        return self._cases_index

    def _get_history_index(self) -> dict[str, list[dict[str, str]]]:
        if self._history_index is None:
            log.info("MockClient: loading closed_cases_history.csv …")
            path = self._data_dir / "closed_cases_history.csv"
            idx: dict[str, list[dict[str, str]]] = {}
            for row in _iter_csv(path):
                cid = row.get("customer_id", "").strip()
                if cid:
                    idx.setdefault(cid, []).append(row)
            self._history_index = idx
            log.info(f"MockClient: {len(idx):,} customers with history")
        return self._history_index

    def _get_customer_txns(self, customer_id: str) -> list[dict[str, str]]:
        """Return slim transaction rows for a customer using the inverted index."""
        txn_index = self._get_txn_index()
        cust_idx = self._get_customer_txn_idx()
        tid_list = cust_idx.get(customer_id, [])
        return [txn_index[tid] for tid in tid_list if tid in txn_index]

    def _get_customer_devices(self, customer_id: str) -> set[str]:
        """Return canonical device IDs observed for a customer.
        Only includes real devices — None results from normalize_device_info are excluded."""
        identity_index = self._get_identity_index()
        cust_idx = self._get_customer_txn_idx()
        devices: set[str] = set()
        for tid in cust_idx.get(customer_id, []):
            raw_dev = identity_index.get(tid, {}).get("DeviceInfo", "")
            canon = normalize_device_info(raw_dev)
            if canon:
                devices.add(canon)
        return devices

    # ── Public tool methods ────────────────────────────────────────────────

    def get_case(self, case_id: str) -> dict[str, Any]:
        """Return full details for an open investigation case."""
        cases = self._get_cases_index()
        case = cases.get(case_id)
        if not case:
            return {"found": False, "case_id": case_id, "error": "Case not found"}

        txn_id = case.get("flagged_txn_id", "").strip()
        txn = self._get_txn_index().get(txn_id, {})
        identity = self._get_identity_index().get(txn_id, {})

        return {
            "found": True,
            "case_id": case_id,
            "case": {
                "case_id": case.get("case_id"),
                "opened_at": case.get("opened_at"),
                "trigger_type": case.get("trigger_type"),
                "trigger_text": case.get("trigger_text"),
                "flagged_txn_id": txn_id,
                "card_id": case.get("card_id"),
                "customer_id": case.get("customer_id"),
                "risk_score": _safe_float(case.get("risk_score", "")),
            },
            "flagged_transaction": _format_txn(txn, identity) if txn else None,
        }

    def get_customer_history(self, customer_id: str, limit: int = 20) -> dict[str, Any]:
        """Return recent transactions and closed case history for a customer."""
        customer_txns = self._get_customer_txns(customer_id)

        # Sort by timestamp descending (ISO strings compare lexicographically)
        customer_txns.sort(key=lambda r: r.get("ts", ""), reverse=True)

        identity_index = self._get_identity_index()
        recent_txns = [
            _format_txn(t, identity_index.get(t.get("TransactionID", ""), {}))
            for t in customer_txns[:limit]
        ]

        history = self._get_history_index().get(customer_id, [])
        closed_cases = [_format_closed_case(c) for c in history[:20]]

        total_amt = sum(_safe_float(t.get("TransactionAmt", "")) for t in customer_txns)
        fraud_cases = [c for c in history if c.get("outcome") == "confirmed_fraud"]
        total_exposure = sum(_safe_float(c.get("exposure_usd", "")) for c in fraud_cases)

        return {
            "customer_id": customer_id,
            "found": len(customer_txns) > 0,
            "transaction_count": len(customer_txns),
            "total_transaction_amt": round(total_amt, 2),
            "fraud_case_count": len(fraud_cases),
            "total_fraud_exposure_usd": round(total_exposure, 2),
            "recent_transactions": recent_txns,
            "closed_cases": closed_cases,
        }

    def find_connected_entities(
        self,
        entity_id: str,
        entity_type: str = "customer",
    ) -> dict[str, Any]:
        """
        Find entities connected to a customer or card via shared attributes.

        MockClient performs 1-hop shared-attribute matching only.
        It does NOT support configurable multi-hop traversal — that is handled
        by the TigerGraph GSQL query (find_connected_entities.gsql), which
        traverses the graph via Transaction → shared-attribute → Transaction
        edges (always 2 graph hops by definition of the attribute model).

        Each returned connection has an explicit `relationship` field indicating
        WHY the two entities are connected.  Possible values:
          - "shared_device"       : same canonical DeviceProfile (via inverted index)
          - "shared_email_domain" : same P_emaildomain
          - "shared_region"       : same addr1 billing region

        No relationship is ever fabricated.  The relationship type is always
        sourced from actual data.

        Returns
        -------
        dict with key "connected_entities": list of:
          {
            "entity_type": "customer",
            "entity_id": str,
            "relationship": str,          # "shared_device" | "shared_email_domain" | "shared_region"
            "source_device": str | None,  # canonical device_id, only for shared_device
            "source_email":  str | None,  # email domain, only for shared_email_domain
            "source_region": str | None,  # region code, only for shared_region
          }
        """
        if entity_type == "card":
            m = re.match(r"^(C\d+)-K", entity_id)
            seed_cid = m.group(1) if m else entity_id
        else:
            seed_cid = entity_id

        seed_txns = self._get_customer_txns(seed_cid)
        txn_index = self._get_txn_index()

        # ── Gather seed attributes ────────────────────────────────────────
        seed_emails: set[str] = set()
        seed_regions: set[str] = set()
        seed_devices: set[str] = self._get_customer_devices(seed_cid)

        for t in seed_txns:
            em = t.get("P_emaildomain", "").strip().lower()
            rg = t.get("addr1", "").strip()
            if em:
                seed_emails.add(em)
            if rg:
                seed_regions.add(rg)

        # ── Device connections — use the inverted index ───────────────────
        device_cust_idx = self._get_device_customer_idx()
        # device_id → set of other customers who used the same device
        device_connections: dict[str, set[str]] = {}
        for dev in seed_devices:
            others = device_cust_idx.get(dev, set()) - {seed_cid}
            if others:
                device_connections[dev] = others

        # ── Email / region connections — scan customer→txn index ──────────
        # This is O(customers × avg_txns_per_customer) but uses the inverted
        # index so there is no full 590k-row scan.
        cust_idx = self._get_customer_txn_idx()

        email_connections: dict[str, set[str]] = {}  # email → {other_cid}
        region_connections: dict[str, set[str]] = {}  # region → {other_cid}

        for other_cid, tid_list in cust_idx.items():
            if other_cid == seed_cid:
                continue
            for tid in tid_list:
                row = txn_index.get(tid, {})
                em = row.get("P_emaildomain", "").strip().lower()
                rg = row.get("addr1", "").strip()
                if em and em in seed_emails:
                    email_connections.setdefault(em, set()).add(other_cid)
                if rg and rg in seed_regions:
                    region_connections.setdefault(rg, set()).add(other_cid)

        # ── Build structured connection list ──────────────────────────────
        # Track which customers have already been added with their best
        # relationship type (device > email > region).
        seen_customers: dict[str, str] = {}  # customer_id → relationship type
        connected: list[dict[str, Any]] = []

        # 1. Device connections (highest confidence)
        for dev, customers in device_connections.items():
            for cid in customers:
                if cid not in seen_customers:
                    seen_customers[cid] = "shared_device"
                    connected.append({
                        "entity_type": "customer",
                        "entity_id": cid,
                        "relationship": "shared_device",
                        "source_device": dev,
                        "source_email": None,
                        "source_region": None,
                    })

        # 2. Email connections
        for email, customers in email_connections.items():
            for cid in customers:
                if cid not in seen_customers:
                    seen_customers[cid] = "shared_email_domain"
                    connected.append({
                        "entity_type": "customer",
                        "entity_id": cid,
                        "relationship": "shared_email_domain",
                        "source_device": None,
                        "source_email": email,
                        "source_region": None,
                    })

        # 3. Region connections
        for region, customers in region_connections.items():
            for cid in customers:
                if cid not in seen_customers:
                    seen_customers[cid] = "shared_region"
                    connected.append({
                        "entity_type": "customer",
                        "entity_id": cid,
                        "relationship": "shared_region",
                        "source_device": None,
                        "source_email": None,
                        "source_region": region,
                    })

        return {
            "entity_id": entity_id,
            "entity_type": entity_type,
            "matching": "1-hop shared-attribute (MockClient). TigerGraph traversal: 2 graph hops via Transaction→attribute→Transaction.",
            "seed_transaction_count": len(seed_txns),
            "seed_devices": list(seed_devices)[:10],
            "seed_email_domains": list(seed_emails)[:10],
            "seed_regions": list(seed_regions)[:10],
            "connected_entity_count": len(connected),
            "connected_entities": connected[:50],
        }

    def find_prior_cases(
        self,
        customer_id: str | None = None,
        card_id: str | None = None,
    ) -> dict[str, Any]:
        """Find prior closed cases for a customer or card."""
        history_index = self._get_history_index()
        results: list[dict[str, Any]] = []
        seen_case_ids: set[str] = set()

        if customer_id:
            for case in history_index.get(customer_id, []):
                cid = case.get("case_id", "")
                if cid not in seen_case_ids:
                    results.append(_format_closed_case(case))
                    seen_case_ids.add(cid)

        if card_id:
            for cases in history_index.values():
                for case in cases:
                    cid = case.get("case_id", "")
                    if case.get("card_id", "").strip() == card_id and cid not in seen_case_ids:
                        results.append(_format_closed_case(case))
                        seen_case_ids.add(cid)

        results.sort(key=lambda c: c.get("opened_at", ""), reverse=True)

        fraud_count = sum(1 for c in results if c.get("outcome") == "confirmed_fraud")
        total_exposure = sum(_safe_float(str(c.get("exposure_usd", 0))) for c in results)

        return {
            "customer_id": customer_id,
            "card_id": card_id,
            "total_cases": len(results),
            "fraud_cases": fraud_count,
            "cleared_cases": len(results) - fraud_count,
            "total_exposure_usd": round(total_exposure, 2),
            "cases": results[:30],
        }

    def detect_temporal_patterns(
        self,
        customer_id: str,
        window_hours: int = 24,
    ) -> dict[str, Any]:
        """
        Detect burst activity and card-testing patterns for a customer.

        TEMPORAL WINDOW
        ---------------
        window_hours controls a ROLLING window applied to the customer's
        most recent transaction.  Any transaction within window_hours
        before the latest transaction is considered "in the window".

        The `ts` field (ISO datetime string, e.g. "2016-07-02 00:02:21")
        is used for all time comparisons.  TransactionDT (an integer offset
        field) is NOT used for windowing because its epoch is unknown.

        A transaction is in the burst window if:
            latest_ts - window_hours <= txn_ts <= latest_ts

        This is a TRUE rolling window, not a calendar-day grouping.
        """
        customer_txns = self._get_customer_txns(customer_id)

        # Sort chronologically by ISO timestamp string (lexicographic = chronological)
        customer_txns.sort(key=lambda r: r.get("ts", ""))

        amounts = [_safe_float(t.get("TransactionAmt", "")) for t in customer_txns]
        channels = [t.get("channel", "") for t in customer_txns]

        micro_txns = [a for a in amounts if 0 < a < 5.0]
        online_count = channels.count("online")
        in_person_count = channels.count("in_person")

        # ── Rolling window burst detection ───────────────────────────────
        # Uses ts (ISO datetime) for an accurate rolling window.
        window_delta = timedelta(hours=window_hours)
        window_txns: list[dict[str, str]] = []

        if customer_txns:
            latest_ts = _parse_ts(customer_txns[-1].get("ts", ""))
            if latest_ts is not None:
                cutoff = latest_ts - window_delta
                for t in customer_txns:
                    t_ts = _parse_ts(t.get("ts", ""))
                    if t_ts is not None and t_ts >= cutoff:
                        window_txns.append(t)
            else:
                # ts field missing or malformed — fall back to all transactions
                window_txns = customer_txns

        window_amounts = [_safe_float(t.get("TransactionAmt", "")) for t in window_txns]
        window_txn_count = len(window_txns)

        # Burst = 3+ transactions within any rolling window_hours interval
        # (We already have the window; the count itself is the burst indicator)
        burst_detected = window_txn_count >= 3

        # Card testing: 3+ micro-transactions (< $5) globally
        card_testing_signal = len(micro_txns) >= 3
        channel_switch = online_count > 0 and in_person_count > 0

        return {
            "customer_id": customer_id,
            "total_transactions": len(customer_txns),
            "window_hours": window_hours,
            "window_note": (
                f"Rolling {window_hours}h window ending at latest transaction. "
                "Uses ts (ISO datetime). NOT calendar-day grouping."
            ),
            "transactions_in_window": window_txn_count,
            "micro_transaction_count": len(micro_txns),
            "online_transaction_count": online_count,
            "in_person_transaction_count": in_person_count,
            "signals": {
                "card_testing": card_testing_signal,
                "burst_activity": burst_detected,
                "channel_switching": channel_switch,
            },
            "avg_transaction_amt": round(
                sum(amounts) / len(amounts) if amounts else 0.0, 2
            ),
            "max_transaction_amt": round(max(amounts, default=0.0), 2),
            "min_transaction_amt": round(min(amounts, default=0.0), 2),
            "window_transaction_ids": [
                t.get("TransactionID", "") for t in window_txns[:20]
            ],
        }

    def calculate_exposure(
        self,
        customer_id: str | None = None,
        card_id: str | None = None,
    ) -> dict[str, Any]:
        """Calculate total fraud exposure for a customer or card."""
        history_index = self._get_history_index()
        txn_index = self._get_txn_index()

        cases: list[dict[str, str]] = []
        if customer_id:
            cases = history_index.get(customer_id, [])
        elif card_id:
            m = re.match(r"^(C\d+)-K", card_id or "")
            if m:
                cases = history_index.get(m.group(1), [])
            cases = [c for c in cases if c.get("card_id", "").strip() == card_id]

        fraud_cases = [c for c in cases if c.get("outcome") == "confirmed_fraud"]
        total_exposure = sum(_safe_float(c.get("exposure_usd", "")) for c in fraud_cases)

        pending_txns: list[dict[str, Any]] = []
        if customer_id:
            for row in self._get_case_pack():
                if row.get("customer_id", "").strip() == customer_id:
                    txn_id = row.get("flagged_txn_id", "").strip()
                    txn = txn_index.get(txn_id, {})
                    if txn:
                        pending_txns.append({
                            "case_id": row.get("case_id"),
                            "TransactionID": txn_id,
                            "TransactionAmt": _safe_float(txn.get("TransactionAmt", "")),
                        })

        return {
            "customer_id": customer_id,
            "card_id": card_id,
            "confirmed_fraud_cases": len(fraud_cases),
            "total_confirmed_exposure_usd": round(total_exposure, 2),
            "avg_fraud_exposure_usd": round(
                total_exposure / len(fraud_cases) if fraud_cases else 0.0, 2
            ),
            "pending_investigation_txns": pending_txns,
            "pending_exposure_usd": round(
                sum(t["TransactionAmt"] for t in pending_txns), 2
            ),
            "fraud_cases_detail": [_format_closed_case(c) for c in fraud_cases[:10]],
        }

    def find_shared_devices(self, customer_id: str) -> dict[str, Any]:
        """
        Find other customers who share devices with this customer.

        Uses the pre-built device→customers inverted index.
        No per-call scan of 144k identity rows is performed.

        IMPORTANT: Missing DeviceInfo is treated as "no device" and does NOT
        create a shared-device relationship.  Two transactions with missing
        device info are NOT considered to share a device.
        """
        seed_devices = self._get_customer_devices(customer_id)

        if not seed_devices:
            return {
                "customer_id": customer_id,
                "devices_found": 0,
                "devices_shared_with_others": 0,
                "total_shared_customer_count": 0,
                "shared_with_customers": [],
                "device_details": [],
                "message": "No device records found for this customer",
            }

        device_cust_idx = self._get_device_customer_idx()

        shared: list[dict[str, Any]] = []
        all_shared_customers: set[str] = set()

        for dev in seed_devices:
            others = device_cust_idx.get(dev, set()) - {customer_id}
            if others:
                shared.append({
                    "device_id": dev,
                    "shared_customer_count": len(others),
                    "customers": list(others)[:10],
                })
                all_shared_customers.update(others)

        return {
            "customer_id": customer_id,
            "devices_found": len(seed_devices),
            "devices_shared_with_others": len(shared),
            "total_shared_customer_count": len(all_shared_customers),
            "shared_with_customers": list(all_shared_customers)[:20],
            "device_details": shared[:10],
        }

    def get_transaction_context(self, txn_id: str) -> dict[str, Any]:
        """Return full context for a single transaction."""
        txn_index = self._get_txn_index()
        identity_index = self._get_identity_index()
        txn = txn_index.get(txn_id)

        if not txn:
            return {"found": False, "TransactionID": txn_id, "error": "Transaction not found"}

        identity = identity_index.get(txn_id, {})
        customer_id = txn.get("customer_id", "").strip()

        # Use the inverted index — no full scan needed
        customer_txns = self._get_customer_txns(customer_id)
        customer_txns.sort(key=lambda r: r.get("ts", ""), reverse=True)
        recent = [
            _format_txn(t, {})
            for t in customer_txns[:5]
            if t.get("TransactionID") != txn_id
        ]

        history_index = self._get_history_index()
        prior_fraud = [
            c for c in history_index.get(customer_id, [])
            if c.get("outcome") == "confirmed_fraud"
        ]

        return {
            "found": True,
            "TransactionID": txn_id,
            "transaction": _format_txn(txn, identity),
            "customer_id": customer_id,
            "customer_prior_fraud_cases": len(prior_fraud),
            "customer_recent_transactions": recent,
        }

    def is_connected(self) -> bool:
        return True


# ── Formatters ────────────────────────────────────────────────────────────────

def _format_txn(
    txn: dict[str, str],
    identity: dict[str, str],
) -> dict[str, Any]:
    return {
        "TransactionID": txn.get("TransactionID"),
        "ts": txn.get("ts"),
        "TransactionAmt": _safe_float(txn.get("TransactionAmt", "")),
        "ProductCD": txn.get("ProductCD"),
        "channel": txn.get("channel"),
        "card4": txn.get("card4"),
        "card6": txn.get("card6"),
        "addr1": txn.get("addr1"),
        "P_emaildomain": txn.get("P_emaildomain"),
        "risk_score": _safe_float(txn.get("risk_score", "")),
        "DeviceType": identity.get("DeviceType") if identity else None,
        "DeviceInfo": identity.get("DeviceInfo") if identity else None,
        "id_30": identity.get("id_30") if identity else None,
        "id_31": identity.get("id_31") if identity else None,
    }


def _format_closed_case(case: dict[str, str]) -> dict[str, Any]:
    return {
        "case_id": case.get("case_id"),
        "outcome": case.get("outcome"),
        "pattern": case.get("pattern"),
        "opened_at": case.get("opened_at"),
        "closed_at": case.get("closed_at"),
        "exposure_usd": _safe_float(case.get("exposure_usd", "")),
        "n_txns": case.get("n_txns"),
        "actions_taken": case.get("actions_taken"),
        "analyst_notes": case.get("analyst_notes", "")[:300],
    }
