"""
generate_graph_load_files.py — Generate TigerGraph-compatible CSV load files.

Reads normalized data from data/normalized/ and generates per-vertex and
per-edge CSV files in data/graph_load/.

Output files:
  Vertices:
    customers_vertex.csv
    cards_vertex.csv
    transactions_vertex.csv
    device_profiles_vertex.csv
    regions_vertex.csv
    email_domains_vertex.csv
    closed_cases_vertex.csv
    investigation_cases_vertex.csv
    fraud_patterns_vertex.csv

  Edges:
    owns_edges.csv                    (Customer -> Card)
    performed_edges.csv               (Customer -> Transaction)
    made_edges.csv                    (Card -> Transaction)
    uses_device_edges.csv             (Transaction -> DeviceProfile)
    billed_to_region_edges.csv        (Transaction -> Region)
    uses_email_edges.csv              (Transaction -> EmailDomain)
    closed_case_customer_edges.csv    (ClosedCase -> Customer)
    closed_case_card_edges.csv        (ClosedCase -> Card)
    closed_case_txn_edges.csv         (ClosedCase -> Transaction)
    has_pattern_edges.csv             (ClosedCase -> FraudPattern)
    investigation_customer_edges.csv  (InvestigationCase -> Customer)
    investigation_card_edges.csv      (InvestigationCase -> Card)
    investigation_txn_edges.csv       (InvestigationCase -> Transaction)

Usage:
    python scripts/generate_graph_load_files.py
"""

import csv
import sys
import re
import logging
from pathlib import Path
from typing import Iterator

# Ensure project root is on sys.path for device_utils import
sys.path.insert(0, str(Path(__file__).parent.parent))

# ── Configuration ─────────────────────────────────────────────────────────────

DATA_DIR = Path(__file__).parent.parent
NORM_DIR = DATA_DIR / "data" / "normalized"
OUTPUT_DIR = DATA_DIR / "data" / "graph_load"

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger(__name__)


# ── Helpers ───────────────────────────────────────────────────────────────────

def iter_csv(path: Path, limit: int | None = None) -> Iterator[dict[str, str]]:
    if not path.exists():
        return
    with open(path, encoding="utf-8", errors="replace") as f:
        reader = csv.DictReader(f)
        for i, row in enumerate(reader):
            if limit is not None and i >= limit:
                return
            yield row


def write_csv(path: Path, fieldnames: list[str], rows: list[dict[str, str]]) -> int:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)
    return len(rows)


def open_streaming_writer(
    path: Path, fieldnames: list[str]
) -> tuple["csv.DictWriter[str]", "typing.IO[str]"]:
    """Open a streaming CSV writer. Caller must close the returned file handle."""
    import typing
    path.parent.mkdir(parents=True, exist_ok=True)
    f = open(path, "w", newline="", encoding="utf-8")
    writer = csv.DictWriter(f, fieldnames=fieldnames, extrasaction="ignore")
    writer.writeheader()
    return writer, f


def file_size_kb(path: Path) -> float:
    if path.exists():
        return path.stat().st_size / 1024
    return 0.0


# Import canonical device normalisation — do NOT duplicate the logic here.
from mcp.server.device_utils import normalize_device_info


# ── Vertex file generators ─────────────────────────────────────────────────────

def gen_customers_vertex() -> int:
    src = NORM_DIR / "customers.csv"
    dst = OUTPUT_DIR / "customers_vertex.csv"
    rows = list(iter_csv(src))
    return write_csv(dst, ["customer_id", "first_seen", "last_seen"], rows)


def gen_cards_vertex() -> int:
    src = NORM_DIR / "cards.csv"
    dst = OUTPUT_DIR / "cards_vertex.csv"
    rows = list(iter_csv(src))
    return write_csv(dst, ["card_id", "card4", "card6", "card1"], rows)


def gen_transactions_vertex() -> int:
    """Stream transactions_slim.csv → transactions_vertex.csv (no full accumulation)."""
    src = NORM_DIR / "transactions_slim.csv"
    dst = OUTPUT_DIR / "transactions_vertex.csv"
    COLS = [
        "TransactionID", "TransactionDT", "TransactionAmt", "ProductCD",
        "card4", "card6", "channel", "risk_score", "ts",
        "P_emaildomain", "R_emaildomain", "addr1", "addr2",
        "C1", "C2", "D1", "M1", "M2", "M3",
    ]
    writer, f = open_streaming_writer(dst, COLS)
    count = 0
    try:
        for row in iter_csv(src):
            writer.writerow({c: row.get(c, "") for c in COLS})
            count += 1
    finally:
        f.close()
    return count


def gen_device_profiles_vertex() -> int:
    src = NORM_DIR / "device_profiles.csv"
    dst = OUTPUT_DIR / "device_profiles_vertex.csv"
    rows = list(iter_csv(src))
    return write_csv(dst, ["device_id", "DeviceType", "DeviceInfo", "os", "browser"], rows)


def gen_regions_vertex() -> int:
    src = NORM_DIR / "regions.csv"
    dst = OUTPUT_DIR / "regions_vertex.csv"
    rows = list(iter_csv(src))
    return write_csv(dst, ["region_code"], rows)


def gen_email_domains_vertex() -> int:
    src = NORM_DIR / "email_domains.csv"
    dst = OUTPUT_DIR / "email_domains_vertex.csv"
    rows = list(iter_csv(src))
    return write_csv(dst, ["domain"], rows)


def gen_closed_cases_vertex() -> int:
    src = NORM_DIR / "closed_cases_norm.csv"
    dst = OUTPUT_DIR / "closed_cases_vertex.csv"
    COLS = [
        "case_id", "outcome", "pattern", "opened_at", "closed_at",
        "exposure_usd", "n_txns", "actions_taken", "analyst_notes",
    ]
    rows: list[dict[str, str]] = []
    for row in iter_csv(src):
        rows.append({c: row.get(c, "") for c in COLS})
    return write_csv(dst, COLS, rows)


def gen_investigation_cases_vertex() -> int:
    src = NORM_DIR / "investigation_cases.csv"
    dst = OUTPUT_DIR / "investigation_cases_vertex.csv"
    COLS = ["case_id", "opened_at", "trigger_type", "trigger_text", "risk_score"]
    rows: list[dict[str, str]] = []
    for row in iter_csv(src):
        rows.append({c: row.get(c, "") for c in COLS})
    return write_csv(dst, COLS, rows)


def gen_fraud_patterns_vertex() -> int:
    src = NORM_DIR / "fraud_patterns.csv"
    dst = OUTPUT_DIR / "fraud_patterns_vertex.csv"
    rows = list(iter_csv(src))
    return write_csv(dst, ["pattern_name", "description"], rows)


# ── Edge file generators ───────────────────────────────────────────────────────

def gen_owns_edges() -> int:
    """Customer -[OWNS]-> Card: derived from card_id prefix."""
    src = NORM_DIR / "cards.csv"
    dst = OUTPUT_DIR / "owns_edges.csv"
    rows: list[dict[str, str]] = []
    for row in iter_csv(src):
        card_id = row.get("card_id", "")
        m = re.match(r"^(C\d+)-K", card_id)
        if m:
            rows.append({"customer_id": m.group(1), "card_id": card_id})
    return write_csv(dst, ["customer_id", "card_id"], rows)


def gen_performed_edges() -> int:
    """Customer -[PERFORMED]-> Transaction. Streamed — no list accumulation."""
    src = NORM_DIR / "transactions_slim.csv"
    dst = OUTPUT_DIR / "performed_edges.csv"
    writer, f = open_streaming_writer(dst, ["customer_id", "TransactionID"])
    count = 0
    try:
        for row in iter_csv(src):
            cid = row.get("customer_id", "").strip()
            txn_id = row.get("TransactionID", "").strip()
            if cid and txn_id:
                writer.writerow({"customer_id": cid, "TransactionID": txn_id})
                count += 1
    finally:
        f.close()
    return count


def gen_made_edges() -> int:
    """Card -[MADE]-> Transaction.

    DATA LIMITATION — NO FABRICATION
    ---------------------------------
    transactions.csv does NOT contain a card_id column.  It only contains
    customer_id.  There is therefore NO reliable data-supported mapping from
    an individual Transaction to a specific Card.

    A customer may own multiple cards (K1, K2, …).  Assigning every
    transaction to the customer's first known card would be factually wrong
    and could corrupt fraud-ring analysis.

    Decision: emit an EMPTY made_edges.csv.
    The graph will have Customer→Transaction (PERFORMED) edges but will NOT
    have Card→Transaction (MADE) edges unless actual per-transaction card
    data becomes available.

    This limitation is documented in:
      docs/DATA_DICTIONARY.md  (Card section)
      docs/TIGERGRAPH_SCHEMA.md  (MADE edge section)
    """
    dst = OUTPUT_DIR / "made_edges.csv"
    # Write header-only file so loading jobs don't fail on a missing file
    return write_csv(dst, ["card_id", "TransactionID"], [])


def gen_uses_device_edges() -> int:
    """Transaction -[USES_DEVICE]-> DeviceProfile (via identity.csv).

    IMPORTANT: Only creates an edge when DeviceInfo is present and
    normalize_device_info() returns a non-None value.
    Missing device info does NOT create a shared DeviceProfile vertex.
    """
    identity_src = DATA_DIR / "identity.csv"
    dst = OUTPUT_DIR / "uses_device_edges.csv"
    rows: list[dict[str, str]] = []
    skipped = 0
    for row in iter_csv(identity_src):
        txn_id = row.get("TransactionID", "").strip()
        raw_device = row.get("DeviceInfo", "").strip()
        canon = normalize_device_info(raw_device)
        if txn_id and canon:  # canon is None when DeviceInfo is missing
            rows.append({"TransactionID": txn_id, "device_id": canon})
        elif txn_id and not canon:
            skipped += 1
    if skipped:
        log.info(f"  uses_device_edges: {skipped:,} transactions skipped (missing DeviceInfo)")
    return write_csv(dst, ["TransactionID", "device_id"], rows)


def gen_billed_to_region_edges() -> int:
    """Transaction -[BILLED_TO_REGION]-> Region. Streamed."""
    src = NORM_DIR / "transactions_slim.csv"
    dst = OUTPUT_DIR / "billed_to_region_edges.csv"
    writer, f = open_streaming_writer(dst, ["TransactionID", "region_code"])
    count = 0
    try:
        for row in iter_csv(src):
            txn_id = row.get("TransactionID", "").strip()
            addr1 = row.get("addr1", "").strip()
            if txn_id and addr1:
                writer.writerow({"TransactionID": txn_id, "region_code": addr1})
                count += 1
    finally:
        f.close()
    return count


def gen_uses_email_edges() -> int:
    """Transaction -[USES_EMAIL]-> EmailDomain. Streamed."""
    src = NORM_DIR / "transactions_slim.csv"
    dst = OUTPUT_DIR / "uses_email_edges.csv"
    writer, f = open_streaming_writer(dst, ["TransactionID", "domain"])
    count = 0
    try:
        for row in iter_csv(src):
            txn_id = row.get("TransactionID", "").strip()
            domain = row.get("P_emaildomain", "").strip().lower()
            if txn_id and domain:
                writer.writerow({"TransactionID": txn_id, "domain": domain})
                count += 1
    finally:
        f.close()
    return count


def gen_closed_case_customer_edges() -> int:
    """ClosedCase -[INVOLVES_CUSTOMER]-> Customer."""
    src = NORM_DIR / "closed_cases_norm.csv"
    dst = OUTPUT_DIR / "closed_case_customer_edges.csv"
    rows: list[dict[str, str]] = []
    for row in iter_csv(src):
        case_id = row.get("case_id", "").strip()
        cid = row.get("customer_id", "").strip()
        if case_id and cid:
            rows.append({"case_id": case_id, "customer_id": cid})
    return write_csv(dst, ["case_id", "customer_id"], rows)


def gen_closed_case_card_edges() -> int:
    """ClosedCase -[INVOLVES_CARD]-> Card."""
    src = NORM_DIR / "closed_cases_norm.csv"
    dst = OUTPUT_DIR / "closed_case_card_edges.csv"
    rows: list[dict[str, str]] = []
    for row in iter_csv(src):
        case_id = row.get("case_id", "").strip()
        card_id = row.get("card_id", "").strip()
        if case_id and card_id:
            rows.append({"case_id": case_id, "card_id": card_id})
    return write_csv(dst, ["case_id", "card_id"], rows)


def gen_closed_case_txn_edges() -> int:
    """ClosedCase -[FLAGGED_TRANSACTION]-> Transaction.
    
    Uses first_fraud_txn_id and all txn_ids (pipe-separated).
    """
    src = NORM_DIR / "closed_cases_norm.csv"
    dst = OUTPUT_DIR / "closed_case_txn_edges.csv"
    rows: list[dict[str, str]] = []
    seen: set[tuple[str, str]] = set()

    for row in iter_csv(src):
        case_id = row.get("case_id", "").strip()
        if not case_id:
            continue

        # first_fraud_txn_id
        first_txn = row.get("first_fraud_txn_id", "").strip()
        if first_txn and (case_id, first_txn) not in seen:
            rows.append({"case_id": case_id, "TransactionID": first_txn})
            seen.add((case_id, first_txn))

        # all txn_ids (pipe-separated)
        txn_ids_raw = row.get("txn_ids", "").strip()
        if txn_ids_raw:
            for txn_id in txn_ids_raw.split("|"):
                txn_id = txn_id.strip()
                if txn_id and (case_id, txn_id) not in seen:
                    rows.append({"case_id": case_id, "TransactionID": txn_id})
                    seen.add((case_id, txn_id))

    return write_csv(dst, ["case_id", "TransactionID"], rows)


def gen_has_pattern_edges() -> int:
    """ClosedCase -[HAS_PATTERN]-> FraudPattern."""
    src = NORM_DIR / "closed_cases_norm.csv"
    dst = OUTPUT_DIR / "has_pattern_edges.csv"
    rows: list[dict[str, str]] = []
    for row in iter_csv(src):
        case_id = row.get("case_id", "").strip()
        pattern = row.get("pattern", "").strip()
        if case_id and pattern:
            rows.append({"case_id": case_id, "pattern_name": pattern})
    return write_csv(dst, ["case_id", "pattern_name"], rows)


def gen_investigation_customer_edges() -> int:
    """InvestigationCase -[ABOUT_CUSTOMER]-> Customer."""
    src = NORM_DIR / "investigation_cases.csv"
    dst = OUTPUT_DIR / "investigation_customer_edges.csv"
    rows: list[dict[str, str]] = []
    for row in iter_csv(src):
        case_id = row.get("case_id", "").strip()
        cid = row.get("customer_id", "").strip()
        if case_id and cid:
            rows.append({"case_id": case_id, "customer_id": cid})
    return write_csv(dst, ["case_id", "customer_id"], rows)


def gen_investigation_card_edges() -> int:
    """InvestigationCase -[INVESTIGATION_INVOLVES_CARD]-> Card."""
    src = NORM_DIR / "investigation_cases.csv"
    dst = OUTPUT_DIR / "investigation_card_edges.csv"
    rows: list[dict[str, str]] = []
    for row in iter_csv(src):
        case_id = row.get("case_id", "").strip()
        card_id = row.get("card_id", "").strip()
        if case_id and card_id:
            rows.append({"case_id": case_id, "card_id": card_id})
    return write_csv(dst, ["case_id", "card_id"], rows)


def gen_investigation_txn_edges() -> int:
    """InvestigationCase -[INVESTIGATION_FLAGGED_TRANSACTION]-> Transaction."""
    src = NORM_DIR / "investigation_cases.csv"
    dst = OUTPUT_DIR / "investigation_txn_edges.csv"
    rows: list[dict[str, str]] = []
    for row in iter_csv(src):
        case_id = row.get("case_id", "").strip()
        txn_id = row.get("flagged_txn_id", "").strip()
        if case_id and txn_id:
            rows.append({"case_id": case_id, "TransactionID": txn_id})
    return write_csv(dst, ["case_id", "TransactionID"], rows)


# ── Main ───────────────────────────────────────────────────────────────────────

def main() -> int:
    log.info("=" * 60)
    log.info("FraudGraph Load File Generator")
    log.info("=" * 60)
    log.info(f"Input:  {NORM_DIR}")
    log.info(f"Output: {OUTPUT_DIR}")
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    generators: list[tuple[str, str]] = [
        ("customers_vertex.csv", "gen_customers_vertex"),
        ("cards_vertex.csv", "gen_cards_vertex"),
        ("transactions_vertex.csv", "gen_transactions_vertex"),
        ("device_profiles_vertex.csv", "gen_device_profiles_vertex"),
        ("regions_vertex.csv", "gen_regions_vertex"),
        ("email_domains_vertex.csv", "gen_email_domains_vertex"),
        ("closed_cases_vertex.csv", "gen_closed_cases_vertex"),
        ("investigation_cases_vertex.csv", "gen_investigation_cases_vertex"),
        ("fraud_patterns_vertex.csv", "gen_fraud_patterns_vertex"),
        ("owns_edges.csv", "gen_owns_edges"),
        ("performed_edges.csv", "gen_performed_edges"),
        ("made_edges.csv", "gen_made_edges"),
        ("uses_device_edges.csv", "gen_uses_device_edges"),
        ("billed_to_region_edges.csv", "gen_billed_to_region_edges"),
        ("uses_email_edges.csv", "gen_uses_email_edges"),
        ("closed_case_customer_edges.csv", "gen_closed_case_customer_edges"),
        ("closed_case_card_edges.csv", "gen_closed_case_card_edges"),
        ("closed_case_txn_edges.csv", "gen_closed_case_txn_edges"),
        ("has_pattern_edges.csv", "gen_has_pattern_edges"),
        ("investigation_customer_edges.csv", "gen_investigation_customer_edges"),
        ("investigation_card_edges.csv", "gen_investigation_card_edges"),
        ("investigation_txn_edges.csv", "gen_investigation_txn_edges"),
    ]

    current_module = sys.modules[__name__]
    total_rows = 0
    results: list[tuple[str, int, float]] = []

    for filename, func_name in generators:
        func = getattr(current_module, func_name)
        log.info(f"Generating {filename} ...")
        try:
            count = func()
            size_kb = file_size_kb(OUTPUT_DIR / filename)
            results.append((filename, count, size_kb))
            total_rows += count
            log.info(f"  {count:,} rows  ({size_kb:.1f} KB)")
        except Exception as exc:
            log.error(f"  FAILED: {exc}")
            results.append((filename, -1, 0.0))

    log.info("=" * 60)
    log.info("Summary:")
    log.info(f"  {'File':<45} {'Rows':>10} {'Size KB':>10}")
    log.info(f"  {'-'*45} {'-'*10} {'-'*10}")
    for filename, count, size_kb in results:
        status = f"{count:,}" if count >= 0 else "FAILED"
        log.info(f"  {filename:<45} {status:>10} {size_kb:>9.1f}")
    log.info(f"\n  Total rows: {total_rows:,}")
    log.info(f"  Output: {OUTPUT_DIR}")
    log.info("=" * 60)
    return 0


if __name__ == "__main__":
    sys.exit(main())
