"""
validate_benchmark_cases.py — Validate ALL 20 benchmark investigation cases.

For every case in case_pack.csv:
  1. Reads its flagged transaction ID.
  2. Verifies the transaction exists in the COMPLETE transactions.csv.
  3. Verifies the customer relationship is present in transactions.csv.
  4. Checks whether identity information is available in identity.csv.
  5. Reports status for each case.

ALL 20 cases are checked.  No sampling.

Output columns:
  case_id | transaction_id | transaction_exists | customer_id | identity_available | status

Usage:
    python scripts/validate_benchmark_cases.py
"""

import csv
import sys
from pathlib import Path

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))
from mcp.server.csv_utils import iter_selected_csv_columns

DATA_DIR = ROOT


def main() -> int:
    case_pack_path = DATA_DIR / "case_pack.csv"
    txn_path = DATA_DIR / "transactions.csv"
    identity_path = DATA_DIR / "identity.csv"

    # ── Read all 20 cases ──────────────────────────────────────────────────
    cases: list[dict[str, str]] = []
    with open(case_pack_path, encoding="utf-8", errors="replace") as f:
        reader = csv.DictReader(f)
        for row in reader:
            cases.append(row)

    if not cases:
        print("ERROR: case_pack.csv is empty or missing")
        return 1

    flagged_ids: set[str] = {
        row.get("flagged_txn_id", "").strip()
        for row in cases
        if row.get("flagged_txn_id", "").strip()
    }

    # ── Full scan of transactions.csv ──────────────────────────────────────
    print(f"Scanning transactions.csv for {len(flagged_ids)} flagged transaction IDs …")
    txn_to_customer: dict[str, str] = {}  # TransactionID → customer_id
    rows_scanned = 0

    for row in iter_selected_csv_columns(txn_path, ("TransactionID", "customer_id")):
        tid = row.get("TransactionID", "").strip()
        cid = row.get("customer_id", "").strip()
        rows_scanned += 1
        if tid in flagged_ids:
            txn_to_customer[tid] = cid
        if len(txn_to_customer) == len(flagged_ids):
            break  # all found — stop early

    print(f"Scanned {rows_scanned:,} rows. Found {len(txn_to_customer)}/{len(flagged_ids)} flagged txn IDs.")

    # ── Scan identity.csv ──────────────────────────────────────────────────
    print("Scanning identity.csv for identity records …")
    identity_txn_ids: set[str] = set()
    for row in iter_selected_csv_columns(identity_path, ("TransactionID",)):
        tid = row.get("TransactionID", "").strip()
        if tid:
            identity_txn_ids.add(tid)
    print(f"  {len(identity_txn_ids):,} identity records loaded")

    # ── Build results ──────────────────────────────────────────────────────
    results: list[dict[str, str]] = []
    all_ok = True

    for case in cases:
        case_id = case.get("case_id", "").strip()
        txn_id = case.get("flagged_txn_id", "").strip()
        expected_customer = case.get("customer_id", "").strip()

        txn_exists = txn_id in txn_to_customer
        found_customer = txn_to_customer.get(txn_id, "")
        identity_available = txn_id in identity_txn_ids

        if not txn_exists:
            status = "FAIL: transaction not found in full dataset"
            all_ok = False
        elif found_customer != expected_customer:
            status = (
                f"WARN: customer mismatch "
                f"(case_pack={expected_customer!r}, txn={found_customer!r})"
            )
            all_ok = False
        else:
            status = "OK"

        results.append({
            "case_id": case_id,
            "transaction_id": txn_id,
            "transaction_exists": "yes" if txn_exists else "NO",
            "customer_id": expected_customer,
            "found_customer_id": found_customer,
            "identity_available": "yes" if identity_available else "no",
            "status": status,
        })

    # ── Print table ────────────────────────────────────────────────────────
    print()
    print("=" * 95)
    print(f"{'case_id':<12} {'txn_id':<12} {'txn_exists':<12} {'customer_id':<12} "
          f"{'identity':<10} status")
    print("-" * 95)
    for r in results:
        print(
            f"{r['case_id']:<12} {r['transaction_id']:<12} {r['transaction_exists']:<12} "
            f"{r['customer_id']:<12} {r['identity_available']:<10} {r['status']}"
        )
    print("=" * 95)

    ok_count = sum(1 for r in results if r["status"] == "OK")
    identity_count = sum(1 for r in results if r["identity_available"] == "yes")
    print(f"\nSummary: {ok_count}/{len(results)} cases OK, "
          f"{identity_count}/{len(results)} have identity records")
    print(f"Rows scanned in transactions.csv: {rows_scanned:,}")

    if not all_ok:
        print("\nFAILED — see issues above")
        return 1
    print("\nALL 20 CASES VERIFIED")
    return 0


if __name__ == "__main__":
    sys.exit(main())
