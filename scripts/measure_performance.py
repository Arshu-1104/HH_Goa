"""
measure_performance.py — Measure real latency of all MockClient tools.
Run: python scripts/measure_performance.py
"""
import sys, time
from pathlib import Path

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))
from mcp.server.mock_client import MockClient

c = MockClient(data_dir=ROOT)
results = []

def measure(label, fn, n=5):
    times = []
    for _ in range(n):
        t0 = time.time()
        r = fn()
        times.append(time.time() - t0)
    avg_ms = (sum(times) / len(times)) * 1000
    min_ms = min(times) * 1000
    results.append((label, avg_ms, min_ms, "OK"))
    print(f"  {label:<40} avg={avg_ms:>8.1f}ms  min={min_ms:>8.1f}ms")
    return r

print("Building indexes...")
t0 = time.time()
c._build_txn_indexes()
txn_t = time.time() - t0
print(f"  txn index build:      {txn_t:.2f}s")

t0 = time.time()
c._build_identity_indexes()
id_t = time.time() - t0
print(f"  identity index build: {id_t:.2f}s")

case = c.get_case("HHG-001")
cid = case["case"]["customer_id"]
txn_id = str(case["case"]["flagged_txn_id"])

print("\nTool latencies (5 warm calls each):")
measure("get_case(HHG-001)",             lambda: c.get_case("HHG-001"))
measure("get_transaction_context",       lambda: c.get_transaction_context(txn_id))
measure("get_customer_history",          lambda: c.get_customer_history(cid))
measure("find_shared_devices",           lambda: c.find_shared_devices(cid))
measure("detect_temporal_patterns(24h)", lambda: c.detect_temporal_patterns(cid, 24))
measure("detect_temporal_patterns(2h)",  lambda: c.detect_temporal_patterns(cid, 2))
measure("calculate_exposure",            lambda: c.calculate_exposure(customer_id=cid))
measure("find_prior_cases",              lambda: c.find_prior_cases(customer_id=cid))

# find_connected_entities is slower (scans all customers for email/region)
print("  find_connected_entities (1 call, no avg)...")
t0 = time.time()
ce = c.find_connected_entities(cid)
ce_ms = (time.time() - t0) * 1000
results.append(("find_connected_entities", ce_ms, ce_ms, "OK"))
print(f"  {'find_connected_entities':<40} single={ce_ms:>8.1f}ms  connected={ce['connected_entity_count']}")

print("\n=== SUMMARY ===")
print(f"  Index build: txn={txn_t:.1f}s  identity={id_t:.1f}s")
for label, avg, mn, status in results:
    print(f"  {label:<40} avg={avg:>8.1f}ms  [{status}]")
