"""
agent/run.py — CLI entrypoint for the FraudGraph Investigation Agent.

Usage:
    python -m agent.run --case-id HHG-001
    python -m agent.run --all
    python -m agent.run --case-id HHG-001 --debug

Runs investigations and saves results to investigation_reports/
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
from pathlib import Path

# Ensure project root is on path
ROOT = Path(__file__).parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from agent.graph.workflow import InvestigationWorkflow

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(name)s  %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger("agent.run")


def run_single(case_id: str, debug: bool = False) -> None:
    """Run investigation for a single case and print summary."""
    log.info(f"Investigating case: {case_id}")
    workflow = InvestigationWorkflow(debug=debug)
    state = dict(workflow.run(case_id))

    summary = state.get("final_summary")
    best = state.get("recommended_action")

    print(f"\n{'='*60}")
    print(f"INVESTIGATION COMPLETE: {case_id}")
    print(f"{'='*60}")
    print(f"Status:      {state.get('investigation_status')}")
    print(f"Action:      {best.action if best else 'UNKNOWN'}")
    print(f"Approval:    {best.approval_route if best else 'unknown'}")
    print(f"Required:    {best.approval_required if best else False}")
    if summary:
        print(f"Uncertainty: {summary.uncertainty_level}")
        print(f"Sufficiency: {summary.evidence_sufficiency_level}")
        print(f"Patterns:    {', '.join(summary.identified_patterns) or 'none'}")
        print(f"\nKey Findings:")
        for f in summary.key_findings[:5]:
            print(f"  • {f}")
        print(f"\nReasoning: {summary.decision_reasoning[:200]}")
    print(f"{'='*60}\n")

    report_path = ROOT / "investigation_reports" / f"{case_id}.json"
    if report_path.exists():
        print(f"Report saved: {report_path}")


def run_all(debug: bool = False) -> None:
    """Run investigations for all 20 cases."""
    import csv
    path = ROOT / "case_pack.csv"
    if not path.exists():
        log.error("case_pack.csv not found at project root")
        return

    with open(path, encoding="utf-8") as f:
        cases = [row["case_id"] for row in csv.DictReader(f)]

    log.info(f"Running investigations for {len(cases)} cases")
    workflow = InvestigationWorkflow(debug=debug)

    results = []
    for case_id in cases:
        try:
            state = dict(workflow.run(case_id))
            best = state.get("recommended_action")
            results.append({
                "case_id": case_id,
                "action": str(best.action) if best else "UNKNOWN",
                "approval": str(best.approval_route) if best else "unknown",
                "status": str(state.get("investigation_status")),
            })
            print(
                f"  {case_id}: {best.action if best else 'UNKNOWN'} "
                f"[{best.approval_route if best else '?'}]"
            )
        except Exception as exc:
            log.error(f"{case_id} FAILED: {exc}")
            results.append({"case_id": case_id, "action": "ERROR", "error": str(exc)})

    # Save batch summary
    summary_path = ROOT / "investigation_reports" / "batch_summary.json"
    summary_path.parent.mkdir(exist_ok=True)
    with open(summary_path, "w", encoding="utf-8") as f:
        json.dump(results, f, indent=2, default=str)
    print(f"\nBatch summary saved: {summary_path}")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="FraudGraph Investigation Agent"
    )
    parser.add_argument("--case-id", help="Single case ID to investigate (e.g. HHG-001)")
    parser.add_argument("--all", action="store_true", help="Investigate all 20 cases")
    parser.add_argument("--debug", action="store_true", help="Enable debug logging")
    args = parser.parse_args()

    if args.debug:
        logging.getLogger().setLevel(logging.DEBUG)

    if args.all:
        run_all(debug=args.debug)
    elif args.case_id:
        run_single(args.case_id, debug=args.debug)
    else:
        parser.print_help()
        sys.exit(1)


if __name__ == "__main__":
    main()
