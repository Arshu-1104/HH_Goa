"""
validate_dataset.py — Dataset integrity validation for FraudGraph Investigator.

Checks:
  1. All 4 CSV files exist
  2. Required columns are present in each file
  3. Duplicate TransactionIDs in transactions.csv
  4. customer_id format: starts with C followed by digits
  5. card_id format: customer_id prefix + -K + digit
  6. flagged_txn_ids in case_pack exist in transactions.csv (sample check)
  7. Data quality statistics
  8. Exits with code 1 if critical errors found
"""

import csv
import sys
import re
import os
import collections
from pathlib import Path
from typing import Iterator

# ── Configuration ─────────────────────────────────────────────────────────────

DATA_DIR = Path(__file__).parent.parent

FILES: dict[str, Path] = {
    "transactions": DATA_DIR / "transactions.csv",
    "identity": DATA_DIR / "identity.csv",
    "case_pack": DATA_DIR / "case_pack.csv",
    "closed_cases": DATA_DIR / "closed_cases_history.csv",
}

REQUIRED_COLUMNS: dict[str, list[str]] = {
    "transactions": [
        "TransactionID", "TransactionDT", "TransactionAmt", "ProductCD",
        "card1", "card4", "card6", "addr1", "P_emaildomain",
        "customer_id", "ts", "channel", "risk_score",
    ],
    "identity": [
        "TransactionID", "DeviceType", "DeviceInfo",
        "id_30", "id_31",
    ],
    "case_pack": [
        "case_id", "opened_at", "trigger_type", "trigger_text",
        "flagged_txn_id", "card_id", "customer_id", "risk_score",
    ],
    "closed_cases": [
        "case_id", "customer_id", "card_id", "opened_at", "closed_at",
        "outcome", "pattern", "txn_ids", "n_txns", "exposure_usd",
        "actions_taken", "analyst_notes",
    ],
}

CUSTOMER_ID_RE = re.compile(r"^C\d+$")
CARD_ID_RE = re.compile(r"^(C\d+)-K\d+$")


# ── Helpers ───────────────────────────────────────────────────────────────────

def iter_csv(path: Path, limit: int | None = None) -> Iterator[dict[str, str]]:
    """Iterate rows of a CSV file as dicts, with optional row limit."""
    with open(path, encoding="utf-8", errors="replace") as f:
        reader = csv.DictReader(f)
        for i, row in enumerate(reader):
            if limit is not None and i >= limit:
                return
            yield row


def count_lines(path: Path) -> int:
    """Count data rows (excluding header)."""
    with open(path, encoding="utf-8", errors="replace") as f:
        return sum(1 for _ in f) - 1


def get_headers(path: Path) -> list[str]:
    with open(path, encoding="utf-8", errors="replace") as f:
        reader = csv.reader(f)
        return next(reader, [])


# ── Validation functions ───────────────────────────────────────────────────────

def check_files_exist() -> list[str]:
    errors: list[str] = []
    for name, path in FILES.items():
        if path.exists():
            size_mb = path.stat().st_size / (1024 * 1024)
            print(f"  [OK] {name}: {path.name}  ({size_mb:.1f} MB)")
        else:
            errors.append(f"MISSING FILE: {path}")
            print(f"  [FAIL] {name}: {path.name}  — NOT FOUND")
    return errors


def check_required_columns() -> list[str]:
    errors: list[str] = []
    for name, path in FILES.items():
        if not path.exists():
            continue
        headers = set(get_headers(path))
        required = REQUIRED_COLUMNS[name]
        missing = [c for c in required if c not in headers]
        if missing:
            errors.append(f"{name}: missing columns: {missing}")
            print(f"  [FAIL] {name}: missing columns: {missing}")
        else:
            print(f"  [OK] {name}: all {len(required)} required columns present")
    return errors


def check_duplicate_transaction_ids() -> list[str]:
    """FULL CHECK: Scan the entire transactions.csv for duplicate TransactionIDs."""
    path = FILES["transactions"]
    if not path.exists():
        return []
    errors: list[str] = []
    seen: set[str] = set()
    dupes: list[str] = []
    count = 0
    print("  [FULL CHECK] Scanning entire transactions.csv for duplicates …")
    for row in iter_csv(path):
        txn_id = row.get("TransactionID", "")
        if txn_id in seen:
            dupes.append(txn_id)
        seen.add(txn_id)
        count += 1
    if dupes:
        errors.append(f"transactions.csv: {len(dupes)} duplicate TransactionIDs in {count:,} rows")
        print(f"  [FAIL] {len(dupes)} duplicate TransactionIDs found in {count:,} rows")
    else:
        print(f"  [OK] No duplicate TransactionIDs in {count:,} rows (FULL CHECK)")
    return errors


def check_customer_id_format(sample_limit: int = 10_000) -> list[str]:
    path = FILES["transactions"]
    if not path.exists():
        return []
    errors: list[str] = []
    bad: list[str] = []
    count = 0
    for row in iter_csv(path, limit=sample_limit):
        cid = row.get("customer_id", "")
        if cid and not CUSTOMER_ID_RE.match(cid):
            bad.append(cid)
        count += 1
    if bad:
        errors.append(f"transactions.csv: {len(bad)} invalid customer_id formats: {bad[:5]}")
        print(f"  [WARN] {len(bad)} non-standard customer_id values in {count}-row sample (first 5: {bad[:5]})")
    else:
        print(f"  [OK] customer_id format valid in {count}-row sample")
    return errors


def check_card_id_format() -> list[str]:
    path = FILES["case_pack"]
    if not path.exists():
        return []
    errors: list[str] = []
    bad: list[tuple[str, str]] = []
    rows = list(iter_csv(path))
    for row in rows:
        card_id = row.get("card_id", "")
        customer_id = row.get("customer_id", "")
        m = CARD_ID_RE.match(card_id)
        if not m:
            bad.append((card_id, "invalid format"))
        elif m.group(1) != customer_id:
            bad.append((card_id, f"prefix {m.group(1)!r} != customer_id {customer_id!r}"))
    if bad:
        errors.append(f"case_pack.csv: {len(bad)} invalid card_id entries: {bad}")
        print(f"  [FAIL] {len(bad)} card_id issues: {bad}")
    else:
        print(f"  [OK] All {len(rows)} card_ids match expected format")
    return errors


def check_flagged_txns_exist() -> list[str]:
    """
    FULL CHECK: Verify ALL flagged_txn_ids from case_pack exist in
    the complete transactions.csv (not just a sample).

    This scans the entire transactions.csv which is necessary to guarantee
    correctness for the 20 investigation cases.
    """
    if not FILES["case_pack"].exists() or not FILES["transactions"].exists():
        return []
    errors: list[str] = []

    # Collect all flagged IDs from case_pack
    flagged_ids: dict[str, str] = {}  # txn_id -> case_id
    for row in iter_csv(FILES["case_pack"]):
        fid = row.get("flagged_txn_id", "").strip()
        if fid:
            flagged_ids[fid] = row.get("case_id", "?")

    remaining = set(flagged_ids.keys())
    rows_scanned = 0

    # Full scan of transactions.csv — required for correctness
    print(f"  [FULL CHECK] Scanning entire transactions.csv for {len(flagged_ids)} flagged IDs …")
    for row in iter_csv(FILES["transactions"]):
        txn_id = row.get("TransactionID", "").strip()
        rows_scanned += 1
        if txn_id in remaining:
            remaining.discard(txn_id)
        if not remaining:
            break  # all found — stop early

    if remaining:
        missing_detail = [(fid, flagged_ids[fid]) for fid in sorted(remaining)]
        errors.append(
            f"case_pack.csv: {len(remaining)} flagged_txn_ids NOT FOUND in "
            f"full transactions.csv scan ({rows_scanned:,} rows scanned): "
            f"{missing_detail}"
        )
        print(f"  [FAIL] {len(remaining)} flagged_txn_ids not found in {rows_scanned:,}-row FULL scan:")
        for fid, cid in missing_detail:
            print(f"         case {cid}: txn {fid}")
    else:
        print(
            f"  [OK] All {len(flagged_ids)} flagged_txn_ids verified in transactions.csv "
            f"(scanned {rows_scanned:,} rows, early-exit when all found)"
        )
    return errors


def report_statistics() -> None:
    """Print data quality statistics for all files."""
    print("\n  === Data Quality Statistics ===")
    for name, path in FILES.items():
        if not path.exists():
            print(f"  {name}: FILE MISSING")
            continue
        row_count = count_lines(path)
        headers = get_headers(path)
        print(f"\n  {name}:")
        print(f"    Rows: {row_count:,}")
        print(f"    Columns: {len(headers)}")

        # Missingness check for key columns
        key_cols = REQUIRED_COLUMNS.get(name, [])[:8]
        miss_counts: dict[str, int] = collections.defaultdict(int)
        sample_count = 0
        sample_limit = min(row_count, 10_000)
        for row in iter_csv(path, limit=sample_limit):
            sample_count += 1
            for col in key_cols:
                if row.get(col, "") in ("", None):
                    miss_counts[col] += 1

        if sample_count > 0:
            print(f"    Missing rates (from {sample_count:,}-row sample):")
            for col in key_cols:
                pct = 100 * miss_counts[col] / sample_count
                if pct > 5:
                    print(f"      {col}: {pct:.1f}%")
                else:
                    print(f"      {col}: <5%")

    # Special stats for closed_cases outcomes and patterns
    if FILES["closed_cases"].exists():
        outcomes: collections.Counter[str] = collections.Counter()
        patterns: collections.Counter[str] = collections.Counter()
        for row in iter_csv(FILES["closed_cases"]):
            outcomes[row.get("outcome", "")] += 1
            patterns[row.get("pattern", "")] += 1
        print(f"\n  closed_cases outcomes: {dict(outcomes)}")
        print(f"  closed_cases patterns: {dict(patterns.most_common(10))}")

    # Special stats for case_pack triggers
    if FILES["case_pack"].exists():
        triggers: collections.Counter[str] = collections.Counter()
        for row in iter_csv(FILES["case_pack"]):
            triggers[row.get("trigger_type", "")] += 1
        print(f"\n  case_pack trigger_types: {dict(triggers)}")


# ── Main ───────────────────────────────────────────────────────────────────────

def main() -> int:
    print("=" * 70)
    print("FraudGraph Dataset Validator")
    print("=" * 70)

    all_errors: list[str] = []

    print("\n[1] Checking files exist...")
    all_errors.extend(check_files_exist())

    print("\n[2] Checking required columns...")
    all_errors.extend(check_required_columns())

    print("\n[3] Checking for duplicate TransactionIDs (FULL SCAN) ...")
    all_errors.extend(check_duplicate_transaction_ids())

    print("\n[4] Checking customer_id format (10k sample)...")
    all_errors.extend(check_customer_id_format())

    print("\n[5] Checking card_id format (case_pack)...")
    all_errors.extend(check_card_id_format())

    print("\n[6] Checking ALL 20 flagged_txn_ids exist in transactions.csv (FULL SCAN) ...")
    all_errors.extend(check_flagged_txns_exist())

    print("\n[7] Reporting data quality statistics...")
    report_statistics()

    print("\n" + "=" * 70)
    if all_errors:
        print(f"VALIDATION FAILED — {len(all_errors)} critical error(s):")
        for err in all_errors:
            print(f"  ERROR: {err}")
        print("=" * 70)
        return 1
    else:
        print("VALIDATION PASSED — all checks OK")
        print("=" * 70)
        return 0


if __name__ == "__main__":
    sys.exit(main())
