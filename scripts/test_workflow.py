"""Quick smoke test for the investigation workflow."""
import logging
import sys
from pathlib import Path

ROOT = Path(__file__).parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")

from agent.graph.workflow import InvestigationWorkflow

wf = InvestigationWorkflow()
state = dict(wf.run("HHG-001"))

best    = state.get("recommended_action")
suf     = state.get("evidence_sufficiency")
unc     = state.get("uncertainty")
summary = state.get("final_summary")
errors  = state.get("errors", [])

print()
print("=== HHG-001 INVESTIGATION RESULT ===")
print(f"Status:        {state.get('investigation_status')}")
print(f"Action:        {best.action if best else 'NONE'}")
print(f"Approval:      {best.approval_route if best else '?'}")
print(f"Sufficiency:   {suf.level.value if suf else '?'}")
print(f"Uncertainty:   {unc.level.value if unc else '?'}")
print(f"Evidence:      {len(state.get('evidence', []))} items")
print(f"Supporting:    {len(state.get('supporting_evidence', []))}")
print(f"Contradictory: {len(state.get('contradictory_evidence', []))}")
print(f"Patterns:      {state.get('fraud_patterns', [])}")
print(f"Tool calls:    {[tc.tool_name for tc in state.get('tool_calls', [])]}")
if errors:
    print(f"Errors:        {errors}")
if summary:
    print(f"\nKey Findings ({len(summary.key_findings)}):")
    for f in summary.key_findings[:3]:
        print(f"  - {f[:90]}")
    print(f"\nDecision reasoning: {summary.decision_reasoning[:150]}")
print()
