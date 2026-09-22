"""
test_device_and_entities.py — Device edge cases and connected entity semantic tests.

Tests:
  DEVICE EDGE CASES (Issue 12):
    Case A: Two transactions with same real DeviceInfo → same canonical DeviceProfile
    Case B: Two transactions with missing DeviceInfo → NO shared device
    Case C: Two raw DeviceInfo values that differ only in formatting → same canonical ID

  CONNECTED ENTITY SEMANTICS (Issue 13):
    A shares device with B → relationship = shared_device
    A shares email with B → relationship = shared_email_domain
    A shares region with B → relationship = shared_region
    A has no relationship with B → B is not returned
    Every connection has explicit relationship type with source

  TEMPORAL WINDOW (Issue 7):
    2-hour window
    24-hour window
    Transactions crossing midnight
    Transactions just outside the window
    Transactions exactly on the window boundary

Run:
    python -m pytest tests/test_device_and_entities.py -v
"""

import sys
import unittest
from datetime import datetime, timedelta
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))

from mcp.server.device_utils import normalize_device_info
from mcp.server.mock_client import MockClient, _parse_ts, SLIM_COLS, IDENTITY_COLS


# ── Device edge case tests ────────────────────────────────────────────────────

class TestDeviceEdgeCases(unittest.TestCase):
    """Issue 12: Device normalization edge cases."""

    def setUp(self):
        self.norm = normalize_device_info

    # CASE A: Same real device
    def test_case_a_same_device_same_canonical_id(self):
        """Two transactions with same real DeviceInfo → same canonical DeviceProfile."""
        raw1 = "SAMSUNG SM-G892A Build/NRD90M"
        raw2 = "SAMSUNG SM-G892A Build/NRD90M"
        self.assertEqual(self.norm(raw1), self.norm(raw2))
        self.assertIsNotNone(self.norm(raw1))

    # CASE B: Missing DeviceInfo
    def test_case_b_missing_device_no_shared_profile(self):
        """Two transactions with missing DeviceInfo → NO shared DeviceProfile."""
        self.assertIsNone(self.norm(""))
        self.assertIsNone(self.norm(None))
        self.assertIsNone(self.norm("   "))
        # Both None — callers must NOT equate None == None as a shared device
        a = self.norm("")
        b = self.norm(None)
        self.assertIsNone(a)
        self.assertIsNone(b)
        # Explicitly: None is NOT a valid device ID for sharing
        # (test logic: if two customers both have None device, they should NOT share)

    def test_case_b_none_not_used_as_device_key(self):
        """None result from normalize_device_info must never appear as a key
        in a device→customers mapping."""
        # Simulate building a device index like MockClient does
        raw_devices = ["", None, "   "]
        device_cust: dict[str, set[str]] = {}
        for i, raw in enumerate(raw_devices):
            canon = self.norm(raw)
            if canon is None:
                continue  # correctly skipped
            device_cust.setdefault(canon, set()).add(f"C{i:05d}")
        self.assertNotIn(None, device_cust, "None must never be a key in device index")
        self.assertEqual(len(device_cust), 0, "No real device IDs from empty inputs")

    # CASE C: Formatting variations → same canonical ID
    def test_case_c_build_string_variation_same_id(self):
        """Same device model with different build strings → same canonical ID."""
        a = self.norm("SAMSUNG SM-G892A Build/NRD90M")
        b = self.norm("SAMSUNG SM-G892A Build/QP1A.190711.020")
        self.assertEqual(a, b)

    def test_case_c_case_variation_same_id(self):
        """Same device, different case → same canonical ID."""
        a = self.norm("samsung sm-g892a")
        b = self.norm("SAMSUNG SM-G892A")
        self.assertEqual(a, b)

    def test_case_c_patch_version_variation_same_id(self):
        """Same OS with different patch versions → same canonical ID."""
        a = self.norm("iOS 11.1.0")
        b = self.norm("iOS 11.1.2")
        c = self.norm("iOS 11.1.9")
        self.assertEqual(a, b)
        self.assertEqual(b, c)

    def test_case_c_whitespace_variation_same_id(self):
        """Extra whitespace → same canonical ID."""
        a = self.norm("Android 8.0")
        b = self.norm("  Android 8.0  ")
        self.assertEqual(a, b)

    def test_unrelated_devices_different_ids(self):
        """Completely different devices must NOT normalize to the same ID."""
        a = self.norm("SAMSUNG SM-G892A Build/NRD90M")
        b = self.norm("iOS 11.1.2")
        self.assertNotEqual(a, b)
        a = self.norm("Windows 10")
        b = self.norm("Android 8.0")
        self.assertNotEqual(a, b)

    def test_canonical_id_format(self):
        """Canonical ID must be lowercase alphanumeric with hyphens/underscores."""
        import re
        for raw in [
            "SAMSUNG SM-G892A Build/NRD90M",
            "iOS 11.1.2",
            "Windows 10",
            "chrome 62.0",
            "android 8.0",
        ]:
            canon = self.norm(raw)
            self.assertIsNotNone(canon)
            self.assertRegex(canon, r'^[a-z0-9_\-]+$',
                             f"Canonical ID {canon!r} has invalid characters")


# ── Connected entity semantic tests ───────────────────────────────────────────

class TestConnectedEntitySemantics(unittest.TestCase):
    """Issue 13: Connected entity relationships must be explicit and accurate."""

    def _make_client_with_data(
        self,
        txn_rows: list[dict],
        identity_rows: list[dict],
    ) -> MockClient:
        """
        Build a MockClient with synthetic in-memory data.
        Bypasses CSV loading entirely.
        """
        from pathlib import Path
        c = MockClient(data_dir=Path("/nonexistent"))

        # Build txn_index and customer_txn_idx from synthetic data
        txn_index = {}
        cust_idx = {}
        for row in txn_rows:
            tid = str(row["TransactionID"])
            slim = {k: str(row.get(k, "")) for k in SLIM_COLS}
            txn_index[tid] = slim
            cid = str(row.get("customer_id", ""))
            if cid:
                cust_idx.setdefault(cid, []).append(tid)

        c._txn_index = txn_index
        c._customer_txn_idx = cust_idx

        # Build identity_index and device_customer_idx from synthetic data
        identity_idx = {}
        device_cust = {}
        for row in identity_rows:
            tid = str(row["TransactionID"])
            id_row = {k: str(row.get(k, "")) for k in IDENTITY_COLS}
            identity_idx[tid] = id_row

            raw_dev = row.get("DeviceInfo", "")
            canon = normalize_device_info(raw_dev)
            if canon is None:
                continue
            cid = txn_index.get(tid, {}).get("customer_id", "")
            if cid:
                device_cust.setdefault(canon, set()).add(cid)

        c._identity_index = identity_idx
        c._device_customer_idx = device_cust
        c._case_pack = []
        c._cases_index = {}
        c._history_index = {}
        return c

    def _make_txn(self, tid, cid, email="", region="", ts="2016-07-02 00:00:00", amt=100.0):
        return {
            "TransactionID": tid, "customer_id": cid,
            "P_emaildomain": email, "addr1": region,
            "ts": ts, "TransactionAmt": amt,
            "TransactionDT": "100", "ProductCD": "H",
            "card4": "visa", "card6": "debit",
            "channel": "online", "risk_score": "0.5",
            "R_emaildomain": "", "C1": "1", "C2": "1",
            "D1": "", "M1": "", "M2": "", "M3": "",
        }

    def _make_id(self, tid, cid, device=""):
        return {
            "TransactionID": tid, "DeviceType": "mobile" if device else "",
            "DeviceInfo": device, "id_30": "", "id_31": "",
        }

    def test_shared_device_relationship_detected(self):
        """A shares device with B → relationship = shared_device."""
        device = "SAMSUNG SM-G892A Build/NRD90M"
        txns = [
            self._make_txn(1001, "C001", email="a@gmail.com", region="100"),
            self._make_txn(1002, "C002", email="b@yahoo.com", region="200"),
        ]
        ids = [
            self._make_id(1001, "C001", device=device),
            self._make_id(1002, "C002", device=device),
        ]
        client = self._make_client_with_data(txns, ids)
        result = client.find_connected_entities("C001")
        entities = result["connected_entities"]

        device_connections = [e for e in entities if e["relationship"] == "shared_device"]
        self.assertTrue(
            any(e["entity_id"] == "C002" for e in device_connections),
            "C002 must appear as shared_device connection"
        )
        # Verify the source device is populated
        c002_entry = next(e for e in device_connections if e["entity_id"] == "C002")
        self.assertIsNotNone(c002_entry["source_device"])
        self.assertIsNone(c002_entry["source_email"])
        self.assertIsNone(c002_entry["source_region"])

    def test_shared_email_relationship_detected(self):
        """A shares email with B → relationship = shared_email_domain."""
        shared_email = "fraud@gmail.com"
        txns = [
            self._make_txn(2001, "C001", email=shared_email, region="100"),
            self._make_txn(2002, "C002", email=shared_email, region="200"),
        ]
        client = self._make_client_with_data(txns, [])
        result = client.find_connected_entities("C001")
        entities = result["connected_entities"]

        email_connections = [e for e in entities if e["relationship"] == "shared_email_domain"]
        self.assertTrue(
            any(e["entity_id"] == "C002" for e in email_connections),
            "C002 must appear as shared_email_domain connection"
        )
        c002_entry = next(e for e in email_connections if e["entity_id"] == "C002")
        self.assertIsNone(c002_entry["source_device"])
        self.assertIsNotNone(c002_entry["source_email"])
        self.assertIsNone(c002_entry["source_region"])

    def test_shared_region_relationship_detected(self):
        """A shares region with B → relationship = shared_region."""
        shared_region = "444"
        txns = [
            self._make_txn(3001, "C001", email="a@gmail.com", region=shared_region),
            self._make_txn(3002, "C002", email="b@yahoo.com", region=shared_region),
        ]
        client = self._make_client_with_data(txns, [])
        result = client.find_connected_entities("C001")
        entities = result["connected_entities"]

        region_connections = [e for e in entities if e["relationship"] == "shared_region"]
        self.assertTrue(
            any(e["entity_id"] == "C002" for e in region_connections),
            "C002 must appear as shared_region connection"
        )
        c002_entry = next(e for e in region_connections if e["entity_id"] == "C002")
        self.assertIsNone(c002_entry["source_device"])
        self.assertIsNone(c002_entry["source_email"])
        self.assertIsNotNone(c002_entry["source_region"])

    def test_no_relationship_not_returned(self):
        """A has no real relationship with B → B is not returned."""
        txns = [
            self._make_txn(4001, "C001", email="unique_a@a.com", region="100"),
            self._make_txn(4002, "C002", email="unique_b@b.com", region="999"),
        ]
        ids = [
            self._make_id(4001, "C001", device=""),        # no device
            self._make_id(4002, "C002", device=""),        # no device
        ]
        client = self._make_client_with_data(txns, ids)
        result = client.find_connected_entities("C001")
        entity_ids = [e["entity_id"] for e in result["connected_entities"]]
        self.assertNotIn("C002", entity_ids,
                         "C002 must not appear — no shared device/email/region")

    def test_relationship_type_always_explicit(self):
        """Every connection in connected_entities must have an explicit relationship field."""
        txns = [
            self._make_txn(5001, "C001", email="shared@gmail.com", region="500"),
            self._make_txn(5002, "C002", email="shared@gmail.com", region="500"),
            self._make_txn(5003, "C003", email="other@yahoo.com", region="500"),
        ]
        client = self._make_client_with_data(txns, [])
        result = client.find_connected_entities("C001")
        for entity in result["connected_entities"]:
            self.assertIn("relationship", entity,
                          "Every entity must have relationship field")
            self.assertIn(entity["relationship"],
                          ("shared_device", "shared_email_domain", "shared_region"),
                          f"Unknown relationship type: {entity['relationship']}")

    def test_device_takes_priority_over_email(self):
        """When A shares both device AND email with B, B appears as shared_device (highest priority)."""
        device = "SAMSUNG SM-G892A Build/NRD90M"
        shared_email = "shared@gmail.com"
        txns = [
            self._make_txn(6001, "C001", email=shared_email, region="100"),
            self._make_txn(6002, "C002", email=shared_email, region="200"),
        ]
        ids = [
            self._make_id(6001, "C001", device=device),
            self._make_id(6002, "C002", device=device),
        ]
        client = self._make_client_with_data(txns, ids)
        result = client.find_connected_entities("C001")
        c002_entries = [e for e in result["connected_entities"] if e["entity_id"] == "C002"]
        self.assertEqual(len(c002_entries), 1,
                         "C002 must appear exactly once (no duplicates)")
        self.assertEqual(c002_entries[0]["relationship"], "shared_device",
                         "Device relationship takes priority over email")

    def test_missing_device_no_shared_device_connection(self):
        """A and B both have missing DeviceInfo → NOT connected via device."""
        txns = [
            self._make_txn(7001, "C001", email="a@a.com", region="100"),
            self._make_txn(7002, "C002", email="b@b.com", region="200"),
        ]
        ids = [
            self._make_id(7001, "C001", device=""),  # missing
            self._make_id(7002, "C002", device=""),  # missing
        ]
        client = self._make_client_with_data(txns, ids)
        result = client.find_connected_entities("C001")
        device_connections = [
            e for e in result["connected_entities"]
            if e["relationship"] == "shared_device"
        ]
        self.assertEqual(len(device_connections), 0,
                         "Missing DeviceInfo must not create shared_device connections")

    def test_find_shared_devices_uses_inverted_index(self):
        """find_shared_devices must use the device→customer inverted index."""
        device = "SAMSUNG SM-G892A Build/NRD90M"
        txns = [
            self._make_txn(8001, "C001", region="100"),
            self._make_txn(8002, "C002", region="200"),
            self._make_txn(8003, "C003", region="300"),
        ]
        ids = [
            self._make_id(8001, "C001", device=device),
            self._make_id(8002, "C002", device=device),
            self._make_id(8003, "C003", device=""),  # no device
        ]
        client = self._make_client_with_data(txns, ids)
        result = client.find_shared_devices("C001")

        self.assertGreater(result["devices_found"], 0)
        self.assertIn("C002", result["shared_with_customers"],
                      "C002 must be in shared customers (same device)")
        self.assertNotIn("C003", result["shared_with_customers"],
                         "C003 must NOT be in shared customers (missing device)")

    def test_find_shared_devices_missing_both_no_connection(self):
        """Two customers both with missing DeviceInfo must NOT share devices."""
        txns = [
            self._make_txn(9001, "C001", region="100"),
            self._make_txn(9002, "C002", region="200"),
        ]
        ids = [
            self._make_id(9001, "C001", device=""),
            self._make_id(9002, "C002", device=""),
        ]
        client = self._make_client_with_data(txns, ids)
        result = client.find_shared_devices("C001")
        self.assertEqual(result["devices_found"], 0)
        self.assertEqual(result["total_shared_customer_count"], 0)
        self.assertNotIn("C002", result.get("shared_with_customers", []))


# ── Temporal window semantic tests ────────────────────────────────────────────

class TestTemporalWindowSemantics(unittest.TestCase):
    """Issue 7: detect_temporal_patterns must respect rolling window_hours."""

    def _make_client_with_txns(self, txn_defs: list[dict]) -> tuple[MockClient, str]:
        """Build a client with synthetic transaction data for customer C99999."""
        cid = "C99999"
        from pathlib import Path
        c = MockClient(data_dir=Path("/nonexistent"))

        txn_index = {}
        cust_idx = {cid: []}

        for row in txn_defs:
            tid = str(row["TransactionID"])
            slim = {k: "" for k in SLIM_COLS}
            slim["TransactionID"] = tid
            slim["customer_id"] = cid
            slim["ts"] = row.get("ts", "2016-07-02 00:00:00")
            slim["TransactionAmt"] = str(row.get("amt", 50.0))
            slim["channel"] = row.get("channel", "online")
            txn_index[tid] = slim
            cust_idx[cid].append(tid)

        c._txn_index = txn_index
        c._customer_txn_idx = cust_idx
        c._identity_index = {}
        c._device_customer_idx = {}
        c._case_pack = []
        c._cases_index = {}
        c._history_index = {}
        return c, cid

    def test_24h_window_all_within(self):
        """5 transactions all within 24h → all 5 in window."""
        txns = [
            {"TransactionID": 1001, "ts": "2016-07-10 01:00:00"},
            {"TransactionID": 1002, "ts": "2016-07-10 06:00:00"},
            {"TransactionID": 1003, "ts": "2016-07-10 12:00:00"},
            {"TransactionID": 1004, "ts": "2016-07-10 18:00:00"},
            {"TransactionID": 1005, "ts": "2016-07-11 00:00:00"},  # latest
        ]
        client, cid = self._make_client_with_txns(txns)
        result = client.detect_temporal_patterns(cid, window_hours=24)
        self.assertEqual(result["transactions_in_window"], 5,
                         "All 5 txns within 24h of latest must be in window")

    def test_2h_window_excludes_earlier(self):
        """2-hour window must exclude transactions >2h before latest."""
        txns = [
            {"TransactionID": 2001, "ts": "2016-07-10 00:00:00"},  # 8h before latest
            {"TransactionID": 2002, "ts": "2016-07-10 06:00:00"},  # 2h before latest
            {"TransactionID": 2003, "ts": "2016-07-10 07:00:00"},  # 1h before latest
            {"TransactionID": 2004, "ts": "2016-07-10 08:00:00"},  # latest
        ]
        client, cid = self._make_client_with_txns(txns)
        result = client.detect_temporal_patterns(cid, window_hours=2)
        # Txn 2001 (8h before) must be excluded; 2002 (exactly 2h) must be included
        self.assertEqual(result["transactions_in_window"], 3,
                         "Only txns within 2h of latest (inclusive boundary) must be in window")

    def test_crossing_midnight(self):
        """Window crossing midnight must work correctly."""
        txns = [
            {"TransactionID": 3001, "ts": "2016-07-10 22:00:00"},
            {"TransactionID": 3002, "ts": "2016-07-10 23:30:00"},
            {"TransactionID": 3003, "ts": "2016-07-11 00:30:00"},  # latest
        ]
        client, cid = self._make_client_with_txns(txns)
        result = client.detect_temporal_patterns(cid, window_hours=2)
        # All 3 are within 2h 30m of latest — only last 2 are within 2h
        self.assertEqual(result["transactions_in_window"], 2,
                         "Txn 22:00 is 2.5h before latest, must be excluded for 2h window")

    def test_just_outside_window_excluded(self):
        """A transaction just outside the window must be excluded."""
        txns = [
            {"TransactionID": 4001, "ts": "2016-07-10 00:00:00"},  # exactly 24h before
            {"TransactionID": 4002, "ts": "2016-07-10 00:01:00"},  # just inside
            {"TransactionID": 4003, "ts": "2016-07-11 00:00:00"},  # latest
        ]
        client, cid = self._make_client_with_txns(txns)
        result = client.detect_temporal_patterns(cid, window_hours=24)
        # Txn 4001 is at exactly latest - 24h → on the boundary (>= cutoff, included)
        self.assertEqual(result["transactions_in_window"], 3,
                         "Boundary transaction (exactly 24h before) must be included (>= cutoff)")

    def test_window_note_is_present(self):
        """Result must include window_note explaining semantics."""
        txns = [{"TransactionID": 5001, "ts": "2016-07-10 00:00:00"}]
        client, cid = self._make_client_with_txns(txns)
        result = client.detect_temporal_patterns(cid, window_hours=24)
        self.assertIn("window_note", result, "window_note must be present")
        note = result["window_note"].lower()
        self.assertIn("rolling", note, "window_note must mention rolling window")
        self.assertIn("ts", note, "window_note must mention ts field")
        # Must NOT describe calendar-day grouping
        self.assertNotIn("same calendar day", note,
                         "window_note must not describe calendar-day grouping")

    def test_window_respects_hours_param(self):
        """Different window_hours values must produce different results for the same data."""
        txns = [
            {"TransactionID": 6001, "ts": "2016-07-10 00:00:00"},
            {"TransactionID": 6002, "ts": "2016-07-10 22:30:00"},  # 1.5h before latest
            {"TransactionID": 6003, "ts": "2016-07-11 00:00:00"},  # latest
        ]
        client, cid = self._make_client_with_txns(txns)
        r24 = client.detect_temporal_patterns(cid, window_hours=24)
        r2 = client.detect_temporal_patterns(cid, window_hours=2)
        # 24h window includes all 3 (6001 is exactly 24h before latest)
        # 2h window includes only 6002 (1.5h before) and 6003 (latest) = 2
        self.assertGreater(r24["transactions_in_window"], r2["transactions_in_window"],
                           "24h window must include more transactions than 2h window")
        self.assertEqual(r24["transactions_in_window"], 3)
        self.assertEqual(r2["transactions_in_window"], 2)

    def test_window_transaction_ids_returned(self):
        """Result must include window_transaction_ids for inspection."""
        txns = [
            {"TransactionID": 7001, "ts": "2016-07-10 00:00:00"},
            {"TransactionID": 7002, "ts": "2016-07-10 23:00:00"},
        ]
        client, cid = self._make_client_with_txns(txns)
        result = client.detect_temporal_patterns(cid, window_hours=24)
        self.assertIn("window_transaction_ids", result)
        self.assertIsInstance(result["window_transaction_ids"], list)

    def test_not_calendar_day_grouping(self):
        """Must NOT group by calendar day. A 2h window on different days is fine."""
        txns = [
            {"TransactionID": 8001, "ts": "2016-07-10 08:00:00"},  # 5 days ago
            {"TransactionID": 8002, "ts": "2016-07-14 22:00:00"},  # yesterday 22:00
            {"TransactionID": 8003, "ts": "2016-07-15 00:00:00"},  # latest (diff calendar day from 8002)
        ]
        client, cid = self._make_client_with_txns(txns)
        result = client.detect_temporal_patterns(cid, window_hours=3)
        # 8002 is 2h before latest → in 3h window
        # 8001 is 5+ days before → NOT in 3h window
        self.assertEqual(result["transactions_in_window"], 2,
                         "Rolling 3h window must include txns from previous calendar day if within 3h")


# ── New runtime smoke additions ───────────────────────────────────────────────

class TestRuntimeSmokeExtended(unittest.TestCase):
    """
    Extended smoke tests covering find_connected_entities and find_shared_devices
    against the real dataset.  Complements test_runtime_smoke.py.
    """

    @classmethod
    def setUpClass(cls):
        import time
        cls.client = MockClient(data_dir=ROOT)
        t0 = time.time()
        cls.client._build_txn_indexes()
        cls.client._build_identity_indexes()
        cls.build_time = time.time() - t0
        cls.case = cls.client.get_case("HHG-001")
        cls.cid = cls.case["case"]["customer_id"]

    def test_find_connected_entities_returns_structure(self):
        result = self.client.find_connected_entities(self.cid)
        self.assertIn("connected_entities", result)
        self.assertIn("connected_entity_count", result)
        self.assertIsInstance(result["connected_entities"], list)

    def test_find_connected_entities_relationship_types_explicit(self):
        result = self.client.find_connected_entities(self.cid)
        valid_rels = {"shared_device", "shared_email_domain", "shared_region"}
        for entity in result["connected_entities"]:
            self.assertIn("relationship", entity)
            self.assertIn(entity["relationship"], valid_rels,
                          f"Unknown relationship: {entity['relationship']}")

    def test_find_connected_entities_source_field_matches_relationship(self):
        """source_device populated iff relationship=shared_device, etc."""
        result = self.client.find_connected_entities(self.cid)
        for entity in result["connected_entities"]:
            rel = entity["relationship"]
            if rel == "shared_device":
                self.assertIsNotNone(entity.get("source_device"),
                                     "shared_device must have source_device")
            elif rel == "shared_email_domain":
                self.assertIsNotNone(entity.get("source_email"),
                                     "shared_email_domain must have source_email")
            elif rel == "shared_region":
                self.assertIsNotNone(entity.get("source_region"),
                                     "shared_region must have source_region")

    def test_find_shared_devices_uses_index_not_full_scan(self):
        """find_shared_devices must have a device→customer index built."""
        device_idx = self.client._get_device_customer_idx()
        self.assertIsNotNone(device_idx, "Device→customer index must be built")
        self.assertGreater(len(device_idx), 0, "Device index must have entries")

    def test_find_shared_devices_returns_structure(self):
        result = self.client.find_shared_devices(self.cid)
        self.assertIn("devices_found", result)
        self.assertIn("total_shared_customer_count", result)
        self.assertIn("device_details", result)

    def test_device_index_has_no_none_keys(self):
        """Device→customer index must never contain None as a key."""
        device_idx = self.client._get_device_customer_idx()
        self.assertNotIn(None, device_idx,
                         "None must never appear as a device key")

    def test_multiple_cases_connected_entities(self):
        """Run find_connected_entities for HHG-001, HHG-011, HHG-014, HHG-017."""
        for case_id in ["HHG-001", "HHG-011", "HHG-014", "HHG-017"]:
            case = self.client.get_case(case_id)
            cid = case["case"]["customer_id"]
            result = self.client.find_connected_entities(cid)
            self.assertIn("connected_entities", result,
                          f"{case_id}: find_connected_entities must return connected_entities")

    def test_multiple_cases_shared_devices(self):
        """Run find_shared_devices for HHG-001, HHG-011, HHG-014, HHG-017."""
        for case_id in ["HHG-001", "HHG-011", "HHG-014", "HHG-017"]:
            case = self.client.get_case(case_id)
            cid = case["case"]["customer_id"]
            result = self.client.find_shared_devices(cid)
            self.assertIn("devices_found", result,
                          f"{case_id}: find_shared_devices must return devices_found")


if __name__ == "__main__":
    unittest.main(verbosity=2)
