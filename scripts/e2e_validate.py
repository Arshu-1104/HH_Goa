"""
Phase 17 E2E validation script.
Runs investigations for all 20 cases and reports:
  - Sufficiency level for each case
  - Whether BLOCK_CARD was recommended and whether it was genuinely justified
  - Reassessment counts
  - Final actions
"""
import sys
import logging
from pathlib import Path

ROOT = Path(__file__).parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

logging.basicConfig(level=logging.WARNING)  # suppress INFO noise

from agent.graph.workflow import InvestigationWorkflow
from agent.state.models import ActionType, InvestigationStatus, SufficiencyLevel
from agent.sufficiency.config import MAX_REASSESSMENTS

import csv

# Load all 20 case IDs
cases = []
with open(ROOT / "case_pack.csv", encoding="utf-8") as f:
    for row in csv.DictReader(f):
        cases.append(row["case_id"])

wf = InvestigationWorkflow()

print(f"\n{'='*72}")
print(f"PHASE 17 — END-TO-END VALIDATION ({len(cases)} cases)")
print(f"{'='*72}")
print(f"{'Case':<10} {'Status':<12} {'Sufficiency':<14} {'Action':<28} {'Reassess':<5} {'OK?'}")
print(f"{'-'*72}")

errors = []
violations = []  # BLOCK_CARD without SUFFICIENT

for case_id in cases:
    state = dict(wf.run(case_id))
    status = state.get("investigation_status", "?")
    suf    = state.get("evidence_sufficiency")
    best   = state.get("recommended_action")
    rcount = state.get("reassessment_count", 0)

    suf_level = suf.level.value if suf else "none"
    action    = str(best.action.value if best and hasattr(best.action,"value") else best.action if best else "NONE")
    ok        = "✓"

    # Key invariant: BLOCK_CARD only when SUFFICIENT
    if best and best.action == ActionType.BLOCK_CARD:
        if not suf or suf.level != SufficiencyLevel.SUFFICIENT:
            ok = "✗ VIOLATION"
            violations.append(f"{case_id}: BLOCK_CARD without SUFFICIENT (suf={suf_level})")

    # Key invariant: reassessment count never exceeds max
    if rcount > MAX_REASSESSMENTS:
        ok = f"✗ REASSESS>{MAX_REASSESSMENTS}"
        errors.append(f"{case_id}: reassessment_count={rcount} > MAX={MAX_REASSESSMENTS}")

    if status == InvestigationStatus.ERROR:
        ok = "⚠ ERROR"
        errors.append(f"{case_id}: investigation error — {state.get('errors', [])}")

    print(f"{case_id:<10} {str(status).split('.')[-1]:<12} {suf_level:<14} {action:<28} {rcount:<5} {ok}")

print(f"{'='*72}")
print(f"\nSUMMARY")
print(f"  Cases run:    {len(cases)}")
print(f"  Violations:   {len(violations)}  (BLOCK_CARD without SUFFICIENT)")
print(f"  Errors:       {len(errors)}")
print(f"  MAX_REASSESS: {MAX_REASSESSMENTS}")

if violations:
    print("\nVIOLATIONS:")
    for v in violations:
        print(f"  {v}")

if errors:
    print("\nERRORS:")
    for e in errors:
        print(f"  {e}")

if not violations and not errors:
    print("\n  All invariants satisfied. Sufficiency fix verified.")
    sys.exit(0)
else:
    sys.exit(1)
