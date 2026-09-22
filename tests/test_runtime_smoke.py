"""
test_runtime_smoke.py — Full-data runtime smoke test.

Exercises the MockClient against the REAL supplied dataset.
Verifies that:
  1. MockClient starts and loads data without OOM errors.
  2. get_case("HHG-001") returns valid data.
  3. The flagged transaction can be retrieved.
  4. Customer history is accessible.
  5. Prior cases are accessible.
  6. Device information is retrieved where available.
  7. Temporal patterns are detected.
  8. Exposure is calculated.
  9. The full 397-column dataset is NEVER loaded into RAM
     (verified by checking that only SLIM_COLS appear in the txn_index).
 10. Missing DeviceInfo does NOT create false shared-device relationships.

NOTE: This test loads the real dataset. Allow ~30s for the transaction
index to build on first run.  Subsequent calls reuse the cached index.

Run:
    python -m pytest tests/test_runtime_smoke.py -v -s
"""

import sys
import time
import unittest
from pathlib import Path

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))

from mcp.server.mock_client import MockClient, SLIM_COLS
from mcp.server.device_utils import normalize_device_info

DATA_DIR = ROOT
_SHARED_CLIENT: MockClient | None = None


def get_client() -> MockClient:
    global _SHARED_CLIENT
    if _SHARED_CLIENT is None:
        _SHARED_CLIENT = MockClient(data_dir=DATA_DIR)
    return _SHARED_CLIENT


class TestRuntimeSmoke(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.client = get_client()
        # Force index build and time it
        t0 = time.time()
        cls.client._build_txn_indexes()
        cls.build_time = time.time() - t0
        print(f"\n  Index build time: {cls.build_time:.1f}s")

    # ── Issue 1: Memory — only slim columns in txn_index ─────────────────

    def test_txn_index_only_contains_slim_cols(self):
        """Verify the transaction index never holds the full 397-column row."""
        txn_index = self.client._get_txn_index()
        # Sample 100 transactions from the index
        sample = list(txn_index.values())[:100]
        slim_set = set(SLIM_COLS)
        v_pattern_found = False
        for row in sample:
            extra_cols = set(row.keys()) - slim_set
            if extra_cols:
                self.fail(
                    f"Transaction row contains non-slim columns: {sorted(extra_cols)[:5]}"
                )
            for col in row.keys():
                if col.startswith("V") and col[1:].isdigit():
                    v_pattern_found = True
        self.assertFalse(v_pattern_found, "V-feature columns must not be in the transaction index")

    def test_txn_index_has_expected_row_count(self):
        txn_index = self.client._get_txn_index()
        # Dataset has 590,742 rows
        self.assertGreater(len(txn_index), 500_000, "Expected ~590k transactions")

    def test_customer_inverted_index_populated(self):
        cust_idx = self.client._get_customer_txn_idx()
        self.assertGreater(len(cust_idx), 1000, "Expected thousands of unique customers")

    # ── Issue 1: get_case ─────────────────────────────────────────────────

    def test_get_case_hgg001(self):
        result = self.client.get_case("HHG-001")
        self.assertTrue(result["found"], "HHG-001 must be found")
        case = result["case"]
        self.assertEqual(case["case_id"], "HHG-001")
        self.assertIsNotNone(case["customer_id"])
        self.assertIsNotNone(case["flagged_txn_id"])
        flagged_txn = result.get("flagged_transaction")
        self.assertIsNotNone(flagged_txn, "Flagged transaction must be retrieved")
        self.assertIsNotNone(flagged_txn["TransactionAmt"])

    def test_get_case_all_20_cases(self):
        """All 20 open investigation cases must be retrievable."""
        found_count = 0
        for i in range(1, 21):
            case_id = f"HHG-{i:03d}"
            result = self.client.get_case(case_id)
            if result["found"]:
                found_count += 1
                self.assertIsNotNone(
                    result["case"]["customer_id"],
                    f"{case_id} must have a customer_id"
                )
                self.assertIsNotNone(
                    result["case"]["flagged_txn_id"],
                    f"{case_id} must have a flagged_txn_id"
                )
        self.assertEqual(found_count, 20, f"Expected 20 cases, found {found_count}")

    # ── Issue 1: get_transaction_context ──────────────────────────────────

    def test_get_transaction_context_for_hgg001(self):
        case_result = self.client.get_case("HHG-001")
        txn_id = case_result["case"]["flagged_txn_id"]

        result = self.client.get_transaction_context(str(txn_id))
        self.assertTrue(result["found"], f"Transaction {txn_id} must be found")
        txn = result["transaction"]
        self.assertIsNotNone(txn["TransactionAmt"])
        self.assertIn(txn.get("channel"), ("online", "in_person"))
        self.assertIsNotNone(result["customer_id"])

    def test_all_20_flagged_txns_found(self):
        """
        FULL CHECK: All 20 flagged transaction IDs from case_pack must
        exist in the complete transaction index.
        """
        missing = []
        for i in range(1, 21):
            case_id = f"HHG-{i:03d}"
            case_result = self.client.get_case(case_id)
            if not case_result["found"]:
                continue
            txn_id = case_result["case"]["flagged_txn_id"]
            ctx = self.client.get_transaction_context(str(txn_id))
            if not ctx["found"]:
                missing.append((case_id, txn_id))

        self.assertEqual(
            len(missing), 0,
            f"Flagged transactions not found in full dataset: {missing}"
        )

    # ── Issue 1: get_customer_history ─────────────────────────────────────

    def test_get_customer_history_for_hgg001(self):
        case_result = self.client.get_case("HHG-001")
        customer_id = case_result["case"]["customer_id"]

        result = self.client.get_customer_history(customer_id)
        self.assertTrue(result["found"])
        self.assertGreater(result["transaction_count"], 0)
        self.assertIsInstance(result["recent_transactions"], list)
        self.assertGreater(len(result["recent_transactions"]), 0)

    def test_customer_history_uses_inverted_index_not_full_scan(self):
        """
        Verify that get_customer_history uses the inverted index.
        After index is built, a second call must NOT scan txn_index.values().
        (Indirectly verified: if _build_txn_indexes was only called once,
        the inverted index is populated and used.)
        """
        # Force both indexes to be built
        self.client._build_txn_indexes()
        cust_idx = self.client._get_customer_txn_idx()

        # Pick an arbitrary customer
        any_cid = next(iter(cust_idx))
        result = self.client.get_customer_history(any_cid)
        # The result must match what the inverted index would produce
        expected_count = len(cust_idx[any_cid])
        self.assertEqual(result["transaction_count"], expected_count,
                         "transaction_count must match inverted index length")

    # ── Issue 4 & 5: Missing device / no false relationships ─────────────

    def test_missing_device_no_false_shared_device(self):
        """
        Customers whose transactions all lack DeviceInfo must return
        devices_found=0 and must NOT appear to share devices with anyone.
        """
        import csv
        identity_path = DATA_DIR / "identity.csv"
        identity_txn_ids: set[str] = set()
        if identity_path.exists():
            with open(identity_path, encoding="utf-8", errors="replace") as f:
                reader = csv.DictReader(f)
                for row in reader:
                    identity_txn_ids.add(row.get("TransactionID", "").strip())

        cust_idx = self.client._get_customer_txn_idx()
        no_device_cid = None
        for cid, tids in cust_idx.items():
            if not any(tid in identity_txn_ids for tid in tids):
                no_device_cid = cid
                break

        if no_device_cid is None:
            self.skipTest("Could not find a customer with no identity records")

        result = self.client.find_shared_devices(no_device_cid)
        self.assertEqual(
            result["devices_found"], 0,
            f"Customer {no_device_cid} has no identity records; must not find devices"
        )
        # When no devices are found, the early-exit path is taken.
        # Verify no shared customers are reported (field may be absent on early exit).
        shared_count = result.get("total_shared_customer_count", 0)
        self.assertEqual(
            shared_count, 0,
            "Must not create false shared-device relationships for missing DeviceInfo"
        )

    def test_normalize_device_none_for_empty(self):
        self.assertIsNone(normalize_device_info(""))
        self.assertIsNone(normalize_device_info(None))
        self.assertIsNone(normalize_device_info("  "))

    # ── Prior cases ───────────────────────────────────────────────────────

    def test_find_prior_cases_for_hgg001_customer(self):
        case_result = self.client.get_case("HHG-001")
        customer_id = case_result["case"]["customer_id"]

        result = self.client.find_prior_cases(customer_id=customer_id)
        self.assertIn("total_cases", result)
        self.assertIn("cases", result)
        self.assertIsInstance(result["cases"], list)

    # ── Temporal patterns ─────────────────────────────────────────────────

    def test_detect_temporal_patterns_for_hgg001_customer(self):
        case_result = self.client.get_case("HHG-001")
        customer_id = case_result["case"]["customer_id"]

        result = self.client.detect_temporal_patterns(customer_id)
        self.assertIn("signals", result)
        self.assertIn("card_testing", result["signals"])
        self.assertIn("burst_activity", result["signals"])
        self.assertIn("channel_switching", result["signals"])
        self.assertGreater(result["total_transactions"], 0)

    # ── Exposure ──────────────────────────────────────────────────────────

    def test_calculate_exposure_for_hgg001_customer(self):
        case_result = self.client.get_case("HHG-001")
        customer_id = case_result["case"]["customer_id"]

        result = self.client.calculate_exposure(customer_id=customer_id)
        self.assertIn("total_confirmed_exposure_usd", result)
        self.assertIn("confirmed_fraud_cases", result)
        self.assertGreaterEqual(result["total_confirmed_exposure_usd"], 0.0)

    # ── find_connected_entities ───────────────────────────────────────────

    def test_find_connected_entities_hgg001(self):
        """find_connected_entities must run and return explicit relationship types."""
        case_result = self.client.get_case("HHG-001")
        customer_id = case_result["case"]["customer_id"]

        result = self.client.find_connected_entities(customer_id)
        self.assertIn("connected_entities", result)
        self.assertIn("connected_entity_count", result)
        self.assertIsInstance(result["connected_entities"], list)

        valid_rels = {"shared_device", "shared_email_domain", "shared_region"}
        for entity in result["connected_entities"]:
            self.assertIn("relationship", entity,
                          "Every connected entity must have explicit relationship")
            self.assertIn(entity["relationship"], valid_rels)

    # ── find_shared_devices ───────────────────────────────────────────────

    def test_find_shared_devices_hgg001(self):
        """find_shared_devices must use inverted index and return valid structure."""
        case_result = self.client.get_case("HHG-001")
        customer_id = case_result["case"]["customer_id"]

        result = self.client.find_shared_devices(customer_id)
        self.assertIn("devices_found", result)
        self.assertIn("total_shared_customer_count", result)
        self.assertIn("device_details", result)
        device_idx = self.client._get_device_customer_idx()
        self.assertIsNotNone(device_idx)
        self.assertGreater(len(device_idx), 0)

    # ── Performance ───────────────────────────────────────────────────────

    def test_index_build_time_reasonable(self):
        """Index build should complete within 120 seconds on a normal machine."""
        self.assertLess(self.build_time, 120,
                        f"Index build took {self.build_time:.1f}s — too slow")


if __name__ == "__main__":
    unittest.main(verbosity=2)
