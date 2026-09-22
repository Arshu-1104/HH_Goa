"""
runtime_e2e_check.py — End-to-end smoke check for HHG-001, HHG-011, HHG-014, HHG-017.
Run: python scripts/runtime_e2e_check.py
"""
import sys
from pathlib import Path

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))
from mcp.server.mock_client import MockClient

c = MockClient(data_dir=ROOT)

CASES = ["HHG-001", "HHG-011", "HHG-014", "HHG-017"]

for case_id in CASES:
    print(f"\n{'='*60}")
    print(f"Case: {case_id}")
    print(f"{'='*60}")

    # 1. case
    case_r = c.get_case(case_id)
    assert case_r["found"], f"{case_id} not found"
    case = case_r["case"]
    cid = case["customer_id"]
    txn_id = str(case["flagged_txn_id"])
    print(f"  customer_id:     {cid}")
    print(f"  flagged_txn_id:  {txn_id}")
    print(f"  trigger_type:    {case['trigger_type']}")
    print(f"  risk_score:      {case['risk_score']}")

    # 2. transaction context
    ctx = c.get_transaction_context(txn_id)
    assert ctx["found"], f"Transaction {txn_id} not found"
    t = ctx["transaction"]
    print(f"  txn amount:      ${t['TransactionAmt']:.2f}  channel={t['channel']}")
    print(f"  device:          {t.get('DeviceInfo') or 'no identity record'}")

    # 3. customer history
    hist = c.get_customer_history(cid)
    print(f"  txn_count:       {hist['transaction_count']}")
    print(f"  fraud_cases:     {hist['fraud_case_count']}")

    # 4. connected entities
    ce = c.find_connected_entities(cid)
    devs = [x for x in ce["connected_entities"] if x["relationship"] == "shared_device"]
    emails = [x for x in ce["connected_entities"] if x["relationship"] == "shared_email_domain"]
    regions = [x for x in ce["connected_entities"] if x["relationship"] == "shared_region"]
    print(f"  connected:       {ce['connected_entity_count']} total  (device={len(devs)}, email={len(emails)}, region={len(regions)})")

    # 5. shared devices
    sd = c.find_shared_devices(cid)
    print(f"  shared_devices:  found={sd['devices_found']}  shared_with={sd['total_shared_customer_count']} customers")

    # 6. prior cases
    pc = c.find_prior_cases(customer_id=cid)
    print(f"  prior_cases:     total={pc['total_cases']}  fraud={pc['fraud_cases']}")

    # 7. temporal (24h window)
    tp = c.detect_temporal_patterns(cid, window_hours=24)
    print(f"  temporal(24h):   txns_in_window={tp['transactions_in_window']}  burst={tp['signals']['burst_activity']}  card_testing={tp['signals']['card_testing']}")

    # 8. exposure
    exp = c.calculate_exposure(customer_id=cid)
    print(f"  exposure:        confirmed=${exp['total_confirmed_exposure_usd']:.2f}  pending=${exp['pending_exposure_usd']:.2f}")

print("\nAll 4 cases passed end-to-end smoke test.")
