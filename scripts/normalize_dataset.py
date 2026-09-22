"""
normalize_dataset.py — Normalize CSV data for graph loading.

Produces normalized entity files in data/normalized/:
  customers.csv         — unique customers from transactions.csv
  cards.csv             — unique cards from case_pack + closed_cases
  device_profiles.csv   — normalized DeviceProfiles from identity.csv
  regions.csv           — unique addr1 region codes
  email_domains.csv     — unique P_emaildomain and R_emaildomain values
  fraud_patterns.csv    — unique patterns from closed_cases_history
  transactions_slim.csv — transactions with selected columns only
  closed_cases_norm.csv — closed cases normalized
  investigation_cases.csv — case_pack normalized

MEMORY STRATEGY
---------------
transactions.csv is ~800 MB with 397 columns.  We never load all 397 columns.
Instead we stream the file once and extract only SLIM_COLS per row.
All normalisation functions that touch transactions.csv share a single
streaming pass where possible.

Usage:
    python scripts/normalize_dataset.py
"""

import csv
import re
import os
import sys
import logging
from pathlib import Path
from typing import Iterator

# ── Configuration ─────────────────────────────────────────────────────────────

ROOT_DIR = Path(__file__).parent.parent
DATA_DIR = ROOT_DIR
OUTPUT_DIR = ROOT_DIR / "data" / "normalized"

# Add project root to path so we can import device_utils
sys.path.insert(0, str(ROOT_DIR))
from mcp.server.device_utils import normalize_device_info  # canonical function

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger(__name__)

# Minimal columns required from transactions.csv
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
    "addr2",
    "C1",
    "C2",
    "D1",
    "M1",
    "M2",
    "M3",
    "customer_id",
)

PATTERN_DESCRIPTIONS: dict[str, str] = {
    "card_not_present_fraud": "Card used for online/phone transactions without physical card",
    "account_takeover": "Fraudster gained access to legitimate customer account",
    "card_not_present_new_device": "Card-not-present transaction from a new/unrecognized device",
    "out_of_region_use": "Card used far outside the customer's normal geographic region",
    "card_testing": "Small repeated transactions to test if stolen card is active",
    "none": "No fraud pattern — case was cleared",
    "undocumented": "Fraud confirmed but specific pattern not documented",
}


# ── Helpers ───────────────────────────────────────────────────────────────────

def iter_csv(path: Path, limit: int | None = None) -> Iterator[dict[str, str]]:
    with open(path, encoding="utf-8", errors="replace") as f:
        reader = csv.DictReader(f)
        for i, row in enumerate(reader):
            if limit is not None and i >= limit:
                return
            yield row


def iter_csv_cols(
    path: Path,
    cols: tuple[str, ...],
    limit: int | None = None,
) -> Iterator[dict[str, str]]:
    """Stream a CSV keeping only the specified columns to reduce heap usage."""
    with open(path, encoding="utf-8", errors="replace") as f:
        reader = csv.DictReader(f)
        available = set(reader.fieldnames or [])
        keep = set(cols) & available
        for i, row in enumerate(reader):
            if limit is not None and i >= limit:
                return
            yield {k: row[k] for k in keep if k in row}


def write_csv(path: Path, fieldnames: list[str], rows: list[dict[str, str]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def write_csv_streaming(path: Path, fieldnames: list[str]) -> csv.DictWriter:
    """Open a CSV writer for streaming row-by-row output. Caller must close the file."""
    path.parent.mkdir(parents=True, exist_ok=True)
    f = open(path, "w", newline="", encoding="utf-8")
    writer = csv.DictWriter(f, fieldnames=fieldnames, extrasaction="ignore")
    writer.writeheader()
    return writer, f


# ── Single-pass transaction normaliser ────────────────────────────────────────

def normalize_transactions_single_pass() -> dict[str, int]:
    """
    Perform ONE streaming pass over transactions.csv.

    Produces simultaneously:
      - transactions_slim.csv
      - customers.csv
      - regions.csv
      - email_domains.csv

    Returns dict of row counts for each output.
    """
    path = DATA_DIR / "transactions.csv"
    if not path.exists():
        log.warning("transactions.csv not found — skipping transaction-derived normalization")
        return {"transactions_slim": 0, "customers": 0, "regions": 0, "email_domains": 0}

    log.info("Single-pass: streaming transactions.csv (slim columns) …")

    slim_path = OUTPUT_DIR / "transactions_slim.csv"
    slim_writer, slim_f = write_csv_streaming(slim_path, list(SLIM_COLS))

    customers: dict[str, dict[str, str]] = {}
    regions: set[str] = set()
    email_domains: set[str] = set()
    slim_count = 0

    for row in iter_csv_cols(path, SLIM_COLS):
        # Write slim row
        slim_writer.writerow({c: row.get(c, "") for c in SLIM_COLS})
        slim_count += 1

        # Accumulate customers
        cid = row.get("customer_id", "").strip()
        ts = row.get("ts", "").strip()
        if cid:
            if cid not in customers:
                customers[cid] = {"customer_id": cid, "first_seen": ts, "last_seen": ts}
            else:
                if ts and ts < customers[cid]["first_seen"]:
                    customers[cid]["first_seen"] = ts
                if ts and ts > customers[cid]["last_seen"]:
                    customers[cid]["last_seen"] = ts

        # Accumulate regions
        addr1 = row.get("addr1", "").strip()
        if addr1:
            regions.add(addr1)

        # Accumulate email domains
        for col in ("P_emaildomain", "R_emaildomain"):
            d = row.get(col, "").strip().lower()
            if d:
                email_domains.add(d)

    slim_f.close()
    log.info(f"  transactions_slim: {slim_count:,} rows")

    # Write customers
    cust_rows = list(customers.values())
    write_csv(
        OUTPUT_DIR / "customers.csv",
        ["customer_id", "first_seen", "last_seen"],
        cust_rows,
    )
    log.info(f"  customers: {len(cust_rows):,} unique customers")

    # Write regions
    region_rows = [{"region_code": r} for r in sorted(regions)]
    write_csv(OUTPUT_DIR / "regions.csv", ["region_code"], region_rows)
    log.info(f"  regions: {len(region_rows):,} unique regions")

    # Write email domains
    domain_rows = [{"domain": d} for d in sorted(email_domains)]
    write_csv(OUTPUT_DIR / "email_domains.csv", ["domain"], domain_rows)
    log.info(f"  email_domains: {len(domain_rows):,} unique domains")

    return {
        "transactions_slim": slim_count,
        "customers": len(cust_rows),
        "regions": len(region_rows),
        "email_domains": len(domain_rows),
    }


# ── Cards ─────────────────────────────────────────────────────────────────────

def normalize_cards() -> int:
    """
    Extract unique cards from case_pack.csv and closed_cases_history.csv.

    card4 / card6 / card1 are enriched from transactions_slim.csv
    (which is already written by the single-pass step).

    IMPORTANT: card_id exists only in case_pack and closed_cases_history.
    transactions.csv has NO card_id column — only customer_id.
    Therefore we cannot create a reliable Transaction → Card mapping from
    transactions.csv alone.  See docs/DATA_DICTIONARY.md for the limitation.
    """
    cards: dict[str, dict[str, str]] = {}

    for filename in ("case_pack.csv", "closed_cases_history.csv"):
        p = DATA_DIR / filename
        if p.exists():
            for row in iter_csv(p):
                card_id = row.get("card_id", "").strip()
                if card_id and card_id not in cards:
                    cards[card_id] = {"card_id": card_id, "card4": "", "card6": "", "card1": ""}

    # Enrich from transactions_slim (already written — minimal memory cost)
    slim_path = OUTPUT_DIR / "transactions_slim.csv"
    if slim_path.exists():
        customer_meta: dict[str, dict[str, str]] = {}
        for row in iter_csv(slim_path):
            cid = row.get("customer_id", "").strip()
            if cid and cid not in customer_meta:
                customer_meta[cid] = {
                    "card4": row.get("card4", "").strip(),
                    "card6": row.get("card6", "").strip(),
                    "card1": "",  # card1 not in slim — leave blank
                }
        for card_id, card_data in cards.items():
            m = re.match(r"^(C\d+)-K", card_id)
            if m:
                meta = customer_meta.get(m.group(1), {})
                cards[card_id]["card4"] = meta.get("card4", "")
                cards[card_id]["card6"] = meta.get("card6", "")

    rows = list(cards.values())
    write_csv(OUTPUT_DIR / "cards.csv", ["card_id", "card4", "card6", "card1"], rows)
    log.info(f"  cards: {len(rows):,} unique cards")
    return len(rows)


# ── Device profiles ───────────────────────────────────────────────────────────

def normalize_device_profiles() -> int:
    """
    Normalize DeviceProfiles from identity.csv.

    IMPORTANT: Missing DeviceInfo is silently skipped.
    No sentinel value is ever written for a missing device.
    Only rows with a non-empty, non-None canonical device ID are included.
    """
    path = DATA_DIR / "identity.csv"
    if not path.exists():
        log.warning("identity.csv not found — skipping device profiles")
        return 0

    log.info("Extracting device profiles from identity.csv …")
    IDENTITY_COLS = ("TransactionID", "DeviceType", "DeviceInfo", "id_30", "id_31")
    profiles: dict[str, dict[str, str]] = {}

    for row in iter_csv_cols(path, IDENTITY_COLS):
        raw_device = row.get("DeviceInfo", "")
        canon = normalize_device_info(raw_device)

        if canon is None:
            # Missing device — do NOT create a DeviceProfile vertex
            continue

        if canon not in profiles:
            profiles[canon] = {
                "device_id": canon,
                "DeviceType": row.get("DeviceType", "").strip(),
                "DeviceInfo": raw_device.strip(),
                "os": row.get("id_30", "").strip(),
                "browser": row.get("id_31", "").strip(),
            }

    rows = list(profiles.values())
    write_csv(
        OUTPUT_DIR / "device_profiles.csv",
        ["device_id", "DeviceType", "DeviceInfo", "os", "browser"],
        rows,
    )
    log.info(f"  device_profiles: {len(rows):,} unique device profiles (missing DeviceInfo excluded)")
    return len(rows)


# ── Fraud patterns ─────────────────────────────────────────────────────────────

def normalize_fraud_patterns() -> int:
    path = DATA_DIR / "closed_cases_history.csv"
    if not path.exists():
        return 0
    patterns: set[str] = set()
    for row in iter_csv(path):
        pat = row.get("pattern", "").strip()
        if pat:
            patterns.add(pat)
    rows = [
        {"pattern_name": p, "description": PATTERN_DESCRIPTIONS.get(p, "")}
        for p in sorted(patterns)
    ]
    write_csv(OUTPUT_DIR / "fraud_patterns.csv", ["pattern_name", "description"], rows)
    log.info(f"  fraud_patterns: {len(rows):,} unique fraud patterns")
    return len(rows)


# ── Closed cases ─────────────────────────────────────────────────────────────

def normalize_closed_cases() -> int:
    path = DATA_DIR / "closed_cases_history.csv"
    if not path.exists():
        return 0
    COLS = [
        "case_id", "customer_id", "card_id", "opened_at", "closed_at",
        "outcome", "pattern", "first_fraud_txn_id", "txn_ids",
        "n_txns", "exposure_usd", "actions_taken", "analyst_notes",
    ]
    rows = [{c: row.get(c, "") for c in COLS} for row in iter_csv(path)]
    write_csv(OUTPUT_DIR / "closed_cases_norm.csv", COLS, rows)
    log.info(f"  closed_cases_norm: {len(rows):,} rows")
    return len(rows)


# ── Investigation cases ───────────────────────────────────────────────────────

def normalize_investigation_cases() -> int:
    path = DATA_DIR / "case_pack.csv"
    if not path.exists():
        return 0
    COLS = [
        "case_id", "opened_at", "trigger_type", "trigger_text",
        "flagged_txn_id", "card_id", "customer_id", "risk_score",
    ]
    rows = [{c: row.get(c, "") for c in COLS} for row in iter_csv(path)]
    write_csv(OUTPUT_DIR / "investigation_cases.csv", COLS, rows)
    log.info(f"  investigation_cases: {len(rows):,} rows")
    return len(rows)


# ── Main ───────────────────────────────────────────────────────────────────────

def main() -> int:
    import time
    t0 = time.time()

    log.info("=" * 60)
    log.info("FraudGraph Dataset Normalizer")
    log.info("=" * 60)
    log.info(f"Output directory: {OUTPUT_DIR}")
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    results: dict[str, int] = {}

    # ONE pass over the large transactions.csv
    log.info("Step 1/5: Single-pass transaction normalization …")
    pass_counts = normalize_transactions_single_pass()
    results.update(pass_counts)

    # Remaining small-file steps
    log.info("Step 2/5: Cards …")
    results["cards"] = normalize_cards()

    log.info("Step 3/5: Device profiles …")
    results["device_profiles"] = normalize_device_profiles()

    log.info("Step 4/5: Fraud patterns …")
    results["fraud_patterns"] = normalize_fraud_patterns()

    log.info("Step 5/5: Closed cases + investigation cases …")
    results["closed_cases"] = normalize_closed_cases()
    results["investigation_cases"] = normalize_investigation_cases()

    elapsed = time.time() - t0

    log.info("=" * 60)
    log.info(f"Normalization complete in {elapsed:.1f}s. Row counts:")
    for name, count in results.items():
        # Map result key to actual output filename
        filename_map = {
            "transactions_slim": "transactions_slim.csv",
            "customers": "customers.csv",
            "regions": "regions.csv",
            "email_domains": "email_domains.csv",
            "cards": "cards.csv",
            "device_profiles": "device_profiles.csv",
            "fraud_patterns": "fraud_patterns.csv",
            "closed_cases": "closed_cases_norm.csv",
            "investigation_cases": "investigation_cases.csv",
        }
        fname = filename_map.get(name, f"{name}.csv")
        out_file = OUTPUT_DIR / fname
        exists = "✓" if out_file.exists() else "MISSING"
        log.info(f"  {exists}  {name}: {count:,} rows")
    log.info(f"Files written to: {OUTPUT_DIR}")
    log.info("=" * 60)
    return 0


if __name__ == "__main__":
    sys.exit(main())
