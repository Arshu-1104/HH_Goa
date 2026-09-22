"""
test_data.py — Dataset integrity tests for FraudGraph Investigator.

Tests that all 4 CSV files exist, have the correct columns,
pass format checks, and maintain referential integrity.

Run:
    python -m pytest tests/test_data.py -v
"""

import csv
import re
import sys
import unittest
from pathlib import Path

# Ensure project root is on path
ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))

DATA_DIR = ROOT


# ── Helpers ───────────────────────────────────────────────────────────────────

def iter_csv(path: Path, limit: int | None = None):
    with open(path, encoding="utf-8", errors="replace") as f:
        reader = csv.DictReader(f)
        for i, row in enumerate(reader):
            if limit is not None and i >= limit:
                return
            yield row


def get_headers(path: Path) -> list[str]:
    with open(path, encoding="utf-8", errors="replace") as f:
        return next(csv.reader(f), [])


# ── Tests ─────────────────────────────────────────────────────────────────────

class TestFilesExist(unittest.TestCase):
    """All four dataset files must be present."""

    def test_transactions_exists(self):
        self.assertTrue((DATA_DIR / "transactions.csv").exists(), "transactions.csv missing")

    def test_identity_exists(self):
        self.assertTrue((DATA_DIR / "identity.csv").exists(), "identity.csv missing")

    def test_case_pack_exists(self):
        self.assertTrue((DATA_DIR / "case_pack.csv").exists(), "case_pack.csv missing")

    def test_closed_cases_exists(self):
        self.assertTrue((DATA_DIR / "closed_cases_history.csv").exists(),
                        "closed_cases_history.csv missing")


class TestTransactionsColumns(unittest.TestCase):
    """transactions.csv must have all required columns."""

    REQUIRED = [
        "TransactionID", "TransactionDT", "TransactionAmt", "ProductCD",
        "card1", "card4", "card6", "customer_id", "ts", "channel", "risk_score",
    ]

    def setUp(self):
        self.path = DATA_DIR / "transactions.csv"
        if not self.path.exists():
            self.skipTest("transactions.csv not found")
        self.headers = set(get_headers(self.path))

    def test_required_columns_present(self):
        missing = [c for c in self.REQUIRED if c not in self.headers]
        self.assertEqual(missing, [], f"Missing columns in transactions.csv: {missing}")

    def test_has_v_features(self):
        """At least some V-features should be present."""
        v_cols = [c for c in self.headers if re.match(r"^V\d+$", c)]
        self.assertGreater(len(v_cols), 100, "Expected 300+ V-feature columns")

    def test_has_c_features(self):
        c_cols = [c for c in self.headers if re.match(r"^C\d+$", c)]
        self.assertGreater(len(c_cols), 5, "Expected C1-C14 count features")


class TestTransactionsData(unittest.TestCase):
    """transactions.csv data quality checks on a 10k-row sample."""

    SAMPLE = 10_000
    CUSTOMER_RE = re.compile(r"^C\d+$")
    CHANNELS = {"online", "in_person"}
    PRODUCTS = {"H", "W", "C", "S", "R"}

    def setUp(self):
        self.path = DATA_DIR / "transactions.csv"
        if not self.path.exists():
            self.skipTest("transactions.csv not found")
        self.rows = list(iter_csv(self.path, limit=self.SAMPLE))

    def test_no_empty_transaction_ids(self):
        empty = [r for r in self.rows if not r.get("TransactionID", "").strip()]
        self.assertEqual(len(empty), 0, f"{len(empty)} rows with empty TransactionID")

    def test_no_duplicate_transaction_ids(self):
        ids = [r["TransactionID"] for r in self.rows]
        dupes = len(ids) - len(set(ids))
        self.assertEqual(dupes, 0, f"{dupes} duplicate TransactionIDs in sample")

    def test_customer_id_format(self):
        bad = [r["customer_id"] for r in self.rows
               if r.get("customer_id") and not self.CUSTOMER_RE.match(r["customer_id"])]
        self.assertEqual(len(bad), 0, f"Non-standard customer_ids: {bad[:5]}")

    def test_channel_values(self):
        bad = [r["channel"] for r in self.rows
               if r.get("channel") and r["channel"] not in self.CHANNELS]
        self.assertEqual(len(bad), 0, f"Unexpected channel values: {set(bad)}")

    def test_product_cd_values(self):
        bad = [r["ProductCD"] for r in self.rows
               if r.get("ProductCD") and r["ProductCD"] not in self.PRODUCTS]
        self.assertEqual(len(bad), 0, f"Unexpected ProductCD values: {set(bad)}")

    def test_transaction_amounts_positive(self):
        bad = []
        for r in self.rows:
            amt = r.get("TransactionAmt", "")
            if amt:
                try:
                    if float(amt) <= 0:
                        bad.append(amt)
                except ValueError:
                    bad.append(amt)
        self.assertEqual(len(bad), 0, f"{len(bad)} non-positive TransactionAmt values")

    def test_risk_score_range(self):
        """risk_score should be 0.0–1.0 when present."""
        out_of_range = []
        for r in self.rows:
            rs = r.get("risk_score", "")
            if rs:
                try:
                    v = float(rs)
                    if not (0.0 <= v <= 1.0):
                        out_of_range.append(v)
                except ValueError:
                    pass
        self.assertEqual(len(out_of_range), 0,
                         f"{len(out_of_range)} risk_score values outside [0,1]: {out_of_range[:5]}")


class TestIdentityColumns(unittest.TestCase):
    """identity.csv must have all required columns."""

    REQUIRED = ["TransactionID", "DeviceType", "DeviceInfo", "id_30", "id_31"]

    def setUp(self):
        self.path = DATA_DIR / "identity.csv"
        if not self.path.exists():
            self.skipTest("identity.csv not found")
        self.headers = set(get_headers(self.path))

    def test_required_columns_present(self):
        missing = [c for c in self.REQUIRED if c not in self.headers]
        self.assertEqual(missing, [], f"Missing columns in identity.csv: {missing}")

    def test_has_id_features(self):
        id_cols = [c for c in self.headers if re.match(r"^id_\d+$", c)]
        self.assertGreater(len(id_cols), 30, "Expected ~38 id_ columns")


class TestIdentityData(unittest.TestCase):
    """identity.csv data quality."""

    DEVICE_TYPES = {"mobile", "desktop", ""}

    def setUp(self):
        self.path = DATA_DIR / "identity.csv"
        if not self.path.exists():
            self.skipTest("identity.csv not found")
        self.rows = list(iter_csv(self.path, limit=5_000))

    def test_no_empty_transaction_ids(self):
        empty = [r for r in self.rows if not r.get("TransactionID", "").strip()]
        self.assertEqual(len(empty), 0, f"{len(empty)} rows with empty TransactionID")

    def test_device_type_values(self):
        bad = [r["DeviceType"] for r in self.rows
               if r.get("DeviceType") and r["DeviceType"].lower() not in self.DEVICE_TYPES]
        self.assertEqual(len(bad), 0, f"Unexpected DeviceType values: {set(bad)}")


class TestCasePackColumns(unittest.TestCase):
    """case_pack.csv must have all required columns."""

    REQUIRED = [
        "case_id", "opened_at", "trigger_type", "trigger_text",
        "flagged_txn_id", "card_id", "customer_id", "risk_score",
    ]

    def setUp(self):
        self.path = DATA_DIR / "case_pack.csv"
        if not self.path.exists():
            self.skipTest("case_pack.csv not found")
        self.headers = set(get_headers(self.path))

    def test_required_columns_present(self):
        missing = [c for c in self.REQUIRED if c not in self.headers]
        self.assertEqual(missing, [], f"Missing columns in case_pack.csv: {missing}")


class TestCasePackData(unittest.TestCase):
    """case_pack.csv data integrity."""

    CASE_ID_RE = re.compile(r"^HHG-\d{3}$")
    CARD_ID_RE = re.compile(r"^(C\d+)-K\d+$")
    CUSTOMER_RE = re.compile(r"^C\d+$")
    TRIGGER_TYPES = {"risk_score", "customer_report", "analyst_request"}

    def setUp(self):
        self.path = DATA_DIR / "case_pack.csv"
        if not self.path.exists():
            self.skipTest("case_pack.csv not found")
        self.rows = list(iter_csv(self.path))

    def test_has_rows(self):
        self.assertGreater(len(self.rows), 0, "case_pack.csv is empty")

    def test_case_id_format(self):
        bad = [r["case_id"] for r in self.rows if not self.CASE_ID_RE.match(r.get("case_id", ""))]
        self.assertEqual(len(bad), 0, f"Bad case_id formats: {bad}")

    def test_card_id_format(self):
        bad = [r["card_id"] for r in self.rows if not self.CARD_ID_RE.match(r.get("card_id", ""))]
        self.assertEqual(len(bad), 0, f"Bad card_id formats: {bad}")

    def test_card_id_customer_id_consistency(self):
        """card_id prefix must match customer_id."""
        mismatches = []
        for r in self.rows:
            card_id = r.get("card_id", "")
            customer_id = r.get("customer_id", "")
            m = self.CARD_ID_RE.match(card_id)
            if m and m.group(1) != customer_id:
                mismatches.append((card_id, customer_id))
        self.assertEqual(len(mismatches), 0,
                         f"card_id/customer_id mismatches: {mismatches}")

    def test_trigger_type_values(self):
        bad = [r["trigger_type"] for r in self.rows
               if r.get("trigger_type") and r["trigger_type"] not in self.TRIGGER_TYPES]
        self.assertEqual(len(bad), 0, f"Unexpected trigger_type values: {set(bad)}")

    def test_no_duplicate_case_ids(self):
        ids = [r["case_id"] for r in self.rows]
        dupes = len(ids) - len(set(ids))
        self.assertEqual(dupes, 0, f"{dupes} duplicate case_ids in case_pack.csv")


class TestClosedCasesColumns(unittest.TestCase):
    """closed_cases_history.csv must have all required columns."""

    REQUIRED = [
        "case_id", "customer_id", "card_id", "opened_at", "closed_at",
        "outcome", "pattern", "txn_ids", "n_txns", "exposure_usd",
        "actions_taken", "analyst_notes",
    ]

    def setUp(self):
        self.path = DATA_DIR / "closed_cases_history.csv"
        if not self.path.exists():
            self.skipTest("closed_cases_history.csv not found")
        self.headers = set(get_headers(self.path))

    def test_required_columns_present(self):
        missing = [c for c in self.REQUIRED if c not in self.headers]
        self.assertEqual(missing, [], f"Missing columns in closed_cases_history.csv: {missing}")


class TestClosedCasesData(unittest.TestCase):
    """closed_cases_history.csv data integrity."""

    OUTCOMES = {"confirmed_fraud", "cleared"}
    PATTERNS = {
        "card_not_present_fraud", "account_takeover", "card_not_present_new_device",
        "out_of_region_use", "card_testing", "none", "undocumented",
    }

    def setUp(self):
        self.path = DATA_DIR / "closed_cases_history.csv"
        if not self.path.exists():
            self.skipTest("closed_cases_history.csv not found")
        self.rows = list(iter_csv(self.path, limit=2_000))

    def test_has_sufficient_rows(self):
        # Full file has ~5,565 rows; sample of 2000 confirms it's loaded
        self.assertGreater(len(self.rows), 100, "closed_cases_history.csv has too few rows")

    def test_outcome_values(self):
        bad = [r["outcome"] for r in self.rows
               if r.get("outcome") and r["outcome"] not in self.OUTCOMES]
        self.assertEqual(len(bad), 0, f"Unexpected outcome values: {set(bad)}")

    def test_pattern_values(self):
        bad = [r["pattern"] for r in self.rows
               if r.get("pattern") and r["pattern"] not in self.PATTERNS]
        self.assertEqual(len(bad), 0, f"Unexpected pattern values: {set(bad)}")

    def test_exposure_non_negative(self):
        bad = []
        for r in self.rows:
            exp = r.get("exposure_usd", "")
            if exp:
                try:
                    if float(exp) < 0:
                        bad.append(exp)
                except ValueError:
                    pass
        self.assertEqual(len(bad), 0, f"{len(bad)} negative exposure_usd values")

    def test_cleared_cases_zero_exposure(self):
        """Cleared cases should have zero exposure."""
        bad = []
        for r in self.rows:
            if r.get("outcome") == "cleared":
                exp = r.get("exposure_usd", "0")
                try:
                    if float(exp or "0") > 0:
                        bad.append(r.get("case_id"))
                except ValueError:
                    pass
        self.assertEqual(len(bad), 0,
                         f"{len(bad)} cleared cases with non-zero exposure: {bad[:5]}")

    def test_fraud_cases_have_pattern(self):
        """Confirmed fraud cases must have a non-empty, non-none pattern."""
        bad = []
        for r in self.rows:
            if r.get("outcome") == "confirmed_fraud":
                pattern = r.get("pattern", "").strip()
                if not pattern or pattern == "none":
                    bad.append(r.get("case_id"))
        self.assertEqual(len(bad), 0,
                         f"{len(bad)} fraud cases without a proper pattern: {bad[:5]}")


class TestReferentialIntegrity(unittest.TestCase):
    """Cross-file referential integrity checks."""

    def test_flagged_txns_in_transactions(self):
        """All flagged_txn_ids in case_pack must exist in transactions.csv."""
        cp_path = DATA_DIR / "case_pack.csv"
        txn_path = DATA_DIR / "transactions.csv"

        if not cp_path.exists() or not txn_path.exists():
            self.skipTest("Required CSV files not found")

        flagged = {
            r["flagged_txn_id"].strip()
            for r in iter_csv(cp_path)
            if r.get("flagged_txn_id", "").strip()
        }

        txn_ids: set[str] = set()
        for row in iter_csv(txn_path):
            txn_ids.add(row.get("TransactionID", "").strip())
            if flagged <= txn_ids:
                break  # All found — stop early

        missing = flagged - txn_ids
        self.assertEqual(len(missing), 0,
                         f"flagged_txn_ids not found in transactions.csv: {missing}")

    def test_identity_txn_ids_in_transactions(self):
        """TransactionIDs in identity.csv (sample) must exist in transactions.csv."""
        id_path = DATA_DIR / "identity.csv"
        txn_path = DATA_DIR / "transactions.csv"

        if not id_path.exists() or not txn_path.exists():
            self.skipTest("Required CSV files not found")

        # Sample 500 from identity
        sample_ids = {
            r["TransactionID"].strip()
            for r in iter_csv(id_path, limit=500)
            if r.get("TransactionID", "").strip()
        }

        txn_ids: set[str] = set()
        for row in iter_csv(txn_path):
            txn_ids.add(row.get("TransactionID", "").strip())
            if sample_ids <= txn_ids:
                break

        missing = sample_ids - txn_ids
        self.assertEqual(len(missing), 0,
                         f"{len(missing)} identity TransactionIDs not found in transactions.csv: "
                         f"{list(missing)[:5]}")


if __name__ == "__main__":
    unittest.main(verbosity=2)
