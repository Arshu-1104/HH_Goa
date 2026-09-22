"""
quick_inspect.py — Fast dataset inspection using only stdlib.
Reads only the first 10,000 rows of large files for speed.
"""
import csv
import collections
import sys
from pathlib import Path

DATA_DIR = Path(__file__).parent.parent
SAMPLE_LIMIT = 10000  # rows to sample for distributions


def get_headers(path):
    with open(path, encoding="utf-8") as f:
        return next(csv.reader(f))


def count_lines(path):
    with open(path, encoding="utf-8", errors="replace") as f:
        return sum(1 for _ in f) - 1


def value_counts(path, col, limit=SAMPLE_LIMIT):
    c = collections.Counter()
    with open(path, encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for i, row in enumerate(reader):
            if i >= limit:
                break
            c[row.get(col, "__EMPTY__")] += 1
    return dict(c.most_common(15))


def missing_pct(path, cols, limit=SAMPLE_LIMIT):
    miss = collections.Counter()
    total = 0
    with open(path, encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for i, row in enumerate(reader):
            if i >= limit:
                break
            total += 1
            for c in cols:
                if row.get(c, "") in ("", None):
                    miss[c] += 1
    return {k: f"{100*v//total}%" for k, v in miss.most_common(20) if v > total * 0.1}, total


def read_all_rows(path):
    with open(path, encoding="utf-8") as f:
        return list(csv.DictReader(f))


print("=" * 70)
print("FAST DATASET INSPECTION (stdlib only, 10k-row sample)")
print("=" * 70)

# ── transactions.csv ──────────────────────────────────────────────────
path = DATA_DIR / "transactions.csv"
print(f"\n{'─'*70}")
print("transactions.csv")
print(f"{'─'*70}")
headers = get_headers(path)
print(f"Rows: ~590,742  Columns: {len(headers)}")
key_cols = ["TransactionID","TransactionDT","TransactionAmt","ProductCD",
            "card1","card2","card3","card4","card5","card6",
            "addr1","addr2","dist1","dist2",
            "P_emaildomain","R_emaildomain",
            "C1","C2","C3","C4","C5","C6","C7","C8","C9","C10","C11","C12","C13","C14",
            "D1","D2","D3","D4","D5","D6","D7","D8","D9","D10","D11","D12","D13","D14","D15",
            "M1","M2","M3","M4","M5","M6","M7","M8","M9",
            "customer_id","ts","channel","risk_score"]
print(f"\nKey columns ({len(key_cols)}):")
for c in key_cols:
    print(f"  {c}")
print(f"\nV-features: V1–V339 ({len([c for c in headers if c.startswith('V')])} cols)")
print("\nchannel:", value_counts(path, "channel"))
print("ProductCD:", value_counts(path, "ProductCD"))
print("card4 (network):", value_counts(path, "card4"))
print("card6 (type):", value_counts(path, "card6"))
miss, total = missing_pct(path, key_cols)
print(f"\nHigh-missing key cols (>{10}%, from {total} sample rows):")
for k, v in miss.items():
    print(f"  {k}: {v}")

# ── identity.csv ──────────────────────────────────────────────────────
path = DATA_DIR / "identity.csv"
print(f"\n{'─'*70}")
print("identity.csv")
print(f"{'─'*70}")
headers_id = get_headers(path)
print(f"Rows: 144,432  Columns: {len(headers_id)}")
print(f"Columns: {', '.join(headers_id)}")
print("DeviceType:", value_counts(path, "DeviceType"))
print("id_15 (new/found):", value_counts(path, "id_15"))
print("id_28 (new/found):", value_counts(path, "id_28"))
miss, total = missing_pct(path, headers_id)
print(f"\nHigh-missing cols (>{10}%, from {total} sample):")
for k, v in miss.items():
    print(f"  {k}: {v}")

# ── case_pack.csv ──────────────────────────────────────────────────────
path = DATA_DIR / "case_pack.csv"
print(f"\n{'─'*70}")
print("case_pack.csv  (20 open investigation cases)")
print(f"{'─'*70}")
rows = read_all_rows(path)
print(f"Rows: {len(rows)}")
print(f"Columns: {', '.join(rows[0].keys())}")
print("\nAll 20 cases:")
for r in rows:
    rs = r.get("risk_score","")
    print(f"  {r['case_id']:8s} {r['trigger_type']:20s} txn={r['flagged_txn_id']:9s} cust={r['customer_id']:10s} card={r['card_id']:15s} rs={rs}")

# ── closed_cases_history.csv ───────────────────────────────────────────
path = DATA_DIR / "closed_cases_history.csv"
print(f"\n{'─'*70}")
print("closed_cases_history.csv")
print(f"{'─'*70}")
headers_cc = get_headers(path)
rows_cc = count_lines(path)
print(f"Rows: {rows_cc:,}  Columns: {len(headers_cc)}")
print(f"Columns: {', '.join(headers_cc)}")
print("outcome:", value_counts(path, "outcome", limit=99999))
print("pattern:", value_counts(path, "pattern", limit=99999))
print("actions_taken:", value_counts(path, "actions_taken", limit=99999))
miss, total = missing_pct(path, headers_cc, limit=99999)
print(f"\nMissing cols (from {total} rows):")
for k, v in miss.items():
    print(f"  {k}: {v}")

print("\n" + "=" * 70)
print("INSPECTION COMPLETE")
print("=" * 70)
