"""
inspect_dataset.py — Quick dataset inspection and statistics.
Produces a summary of all CSV files in the dataset directory.
"""

import csv
import collections
import os
import json
from pathlib import Path
from typing import Any

DATA_DIR = Path(__file__).parent.parent

FILES = [
    "transactions.csv",
    "identity.csv",
    "case_pack.csv",
    "closed_cases_history.csv",
]


def count_rows(path: Path) -> int:
    with open(path, encoding="utf-8") as f:
        return sum(1 for _ in f) - 1  # subtract header


def get_headers(path: Path) -> list[str]:
    with open(path, encoding="utf-8") as f:
        reader = csv.reader(f)
        return next(reader)


def sample_rows(path: Path, n: int = 3) -> list[dict]:
    with open(path, encoding="utf-8") as f:
        reader = csv.DictReader(f)
        return [row for _, row in zip(range(n), reader)]


def count_values(path: Path, col: str) -> dict[str, int]:
    counter: collections.Counter = collections.Counter()
    with open(path, encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            counter[row.get(col, "")] += 1
    return dict(counter.most_common(20))


def missing_stats(path: Path) -> dict[str, int]:
    """Count missing/empty values per column."""
    headers = get_headers(path)
    missing: dict[str, int] = {h: 0 for h in headers}
    total = 0
    with open(path, encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            total += 1
            for h in headers:
                v = row.get(h, "")
                if v == "" or v is None:
                    missing[h] += 1
    # Only return columns with missing > 0
    return {k: v for k, v in missing.items() if v > 0}, total


def main():
    print("=" * 70)
    print("DATASET INSPECTION REPORT")
    print("=" * 70)

    for fname in FILES:
        path = DATA_DIR / fname
        if not path.exists():
            print(f"\n[MISSING] {fname}")
            continue

        print(f"\n{'='*70}")
        print(f"FILE: {fname}")
        print(f"{'='*70}")

        headers = get_headers(path)
        rows = count_rows(path)
        print(f"Rows: {rows:,}")
        print(f"Columns: {len(headers)}")
        print(f"Columns: {', '.join(headers[:30])}{'...' if len(headers) > 30 else ''}")

        missing, total = missing_stats(path)
        high_missing = {k: f"{v}/{total} ({100*v//total}%)" for k, v in missing.items() if v > total * 0.3}
        if high_missing:
            print(f"\nHigh-missing columns (>30%):")
            for col, stat in list(high_missing.items())[:10]:
                print(f"  {col}: {stat}")

        # File-specific value distributions
        if fname == "transactions.csv":
            print("\nChannel distribution:", count_values(path, "channel"))
            print("ProductCD distribution:", count_values(path, "ProductCD"))
            print("card4 (network):", count_values(path, "card4"))
            print("card6 (type):", count_values(path, "card6"))

        if fname == "identity.csv":
            print("DeviceType distribution:", count_values(path, "DeviceType"))

        if fname == "closed_cases_history.csv":
            print("Outcome distribution:", count_values(path, "outcome"))
            print("Pattern distribution:", count_values(path, "pattern"))
            print("Actions distribution:", count_values(path, "actions_taken"))

        if fname == "case_pack.csv":
            print("Trigger type distribution:", count_values(path, "trigger_type"))
            print("\nAll cases:")
            rows_data = sample_rows(path, 25)
            for r in rows_data:
                print(f"  {r['case_id']} | {r['trigger_type']} | txn={r['flagged_txn_id']} | cust={r['customer_id']} | card={r['card_id']}")

        # Sample rows
        print("\nSample rows (first 2):")
        samples = sample_rows(path, 2)
        for s in samples:
            # Only show key fields
            key_fields = {k: v for i, (k, v) in enumerate(s.items()) if i < 15}
            print(f"  {json.dumps(key_fields, indent=None)}")

    print("\n" + "=" * 70)
    print("INSPECTION COMPLETE")
    print("=" * 70)


if __name__ == "__main__":
    main()
