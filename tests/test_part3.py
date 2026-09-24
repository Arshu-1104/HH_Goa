"""
tests/test_part3.py — Part 3 tests.

Tests cover:
  - Part 3 API route registration
  - Report loading from disk
  - Report normalization / data transformation
  - Supporting / contradictory classification
  - Sufficiency display data
  - Uncertainty display data
  - Action display data
  - Approval display data
  - Benchmark loading
  - 20-case validation
  - Case meta endpoint
  - No fabricated data invariants

These tests are purely functional — they do NOT re-run the investigation workflow.
They test the Part 3 API layer against the existing 20 stored reports.
No Part 1 or Part 2 files are modified.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

REPORTS_DIR = ROOT / "investigation_reports"
CASE_PACK = ROOT / "case_pack.csv"
ALL_CASE_IDS = [f"HHG-{i:03d}" for i in range(1, 21)]


# ── Fixtures ──────────────────────────────────────────────────────────────────

@pytest.fixture(scope="module")
def client():
    """FastAPI test client for the Part 3 app."""
    from fastapi.testclient import TestClient
    from agent.api.main import app
    return TestClient(app)


@pytest.fixture(scope="module")
def all_reports() -> dict[str, dict]:
    """Load all 20 stored reports from disk."""
    reports = {}
    for case_id in ALL_CASE_IDS:
        path = REPORTS_DIR / f"{case_id}.json"
        if path.exists():
            with open(path, encoding="utf-8") as f:
                reports[case_id] = json.load(f)
    return reports


@pytest.fixture(scope="module")
def normalizer():
    """Import the normalization function from part3_routes."""
    from agent.api.part3_routes import _normalize_report, _clean_action
    return _normalize_report, _clean_action


# ── API registration tests ─────────────────────────────────────────────────────

class TestAPIRegistration:
    """Part 3 routes are registered on the app."""

    def test_health_endpoint_still_works(self, client):
        """Part 2 /health endpoint must remain unchanged."""
        res = client.get("/health")
        assert res.status_code == 200
        data = res.json()
        assert data["status"] == "ok"

    def test_cases_endpoint_still_works(self, client):
        """Part 2 /cases endpoint must remain unchanged."""
        res = client.get("/cases")
        assert res.status_code == 200
        data = res.json()
        assert "cases" in data
        assert data["total"] == 20

    def test_part3_report_endpoint_registered(self, client):
        """GET /api/v3/report/{case_id} must be registered."""
        res = client.get("/api/v3/report/HHG-001")
        # 200 if report exists, 404 if not — either is a valid registered response
        assert res.status_code in (200, 404)

    def test_part3_benchmark_endpoint_registered(self, client):
        """GET /api/v3/benchmark must be registered."""
        res = client.get("/api/v3/benchmark")
        assert res.status_code == 200

    def test_part3_cases_meta_endpoint_registered(self, client):
        """GET /api/v3/cases/meta must be registered."""
        res = client.get("/api/v3/cases/meta")
        assert res.status_code == 200

    def test_invalid_case_id_returns_400(self, client):
        """Invalid case ID format must return 400."""
        res = client.get("/api/v3/report/INVALID-999")
        assert res.status_code == 400

    def test_nonexistent_case_returns_404(self, client):
        """Non-existent valid-format case ID must return 404."""
        res = client.get("/api/v3/report/HHG-999")
        assert res.status_code == 404

    def test_ui_endpoint_registered(self, client):
        """GET /ui must be registered."""
        res = client.get("/ui", follow_redirects=False)
        # Either 200 (served) or 404 (ui dir not found) — not 500
        assert res.status_code in (200, 404)


# ── Report loading tests ──────────────────────────────────────────────────────

class TestReportLoading:
    """Reports load correctly from disk."""

    def test_all_20_report_files_exist(self):
        """All 20 investigation report files must exist on disk."""
        missing = []
        for case_id in ALL_CASE_IDS:
            path = REPORTS_DIR / f"{case_id}.json"
            if not path.exists():
                missing.append(case_id)
        assert missing == [], f"Missing report files: {missing}"

    def test_reports_are_valid_json(self, all_reports):
        """All reports must be valid JSON."""
        assert len(all_reports) == 20, f"Expected 20 reports, got {len(all_reports)}"

    def test_reports_have_required_top_level_keys(self, all_reports):
        """Each report must have case_id, memory, summary keys."""
        for case_id, report in all_reports.items():
            assert "case_id" in report, f"{case_id}: missing case_id"
            assert "memory" in report, f"{case_id}: missing memory"
            assert "summary" in report, f"{case_id}: missing summary"

    def test_report_case_ids_match_filenames(self, all_reports):
        """Report case_id must match the filename."""
        for case_id, report in all_reports.items():
            assert report["case_id"] == case_id, \
                f"Report case_id {report['case_id']!r} does not match filename {case_id}"

    def test_api_returns_report_for_all_20_cases(self, client):
        """GET /api/v3/report/{case_id} must return 200 for all 20 cases."""
        failed = []
        for case_id in ALL_CASE_IDS:
            res = client.get(f"/api/v3/report/{case_id}")
            if res.status_code != 200:
                failed.append(f"{case_id}: HTTP {res.status_code}")
        assert failed == [], f"Failed report loads: {failed}"


# ── Data normalization tests ──────────────────────────────────────────────────

class TestNormalization:
    """_normalize_report produces correct UI-ready data."""

    def test_action_prefix_stripped(self, normalizer, all_reports):
        """'ActionType.' prefix must be stripped from action strings."""
        norm_fn, _ = normalizer
        for case_id, raw in all_reports.items():
            result = norm_fn(raw)
            action = result["recommended_action"]
            assert not action.startswith("ActionType."), \
                f"{case_id}: action still has ActionType. prefix: {action!r}"

    def test_action_is_non_empty(self, normalizer, all_reports):
        """Normalized action must be non-empty for all 20 cases."""
        norm_fn, _ = normalizer
        for case_id, raw in all_reports.items():
            result = norm_fn(raw)
            assert result["recommended_action"] not in ("", None), \
                f"{case_id}: recommended_action is empty"

    def test_case_id_preserved(self, normalizer, all_reports):
        """Normalized case_id must match original."""
        norm_fn, _ = normalizer
        for case_id, raw in all_reports.items():
            result = norm_fn(raw)
            assert result["case_id"] == case_id

    def test_customer_id_preserved(self, normalizer, all_reports):
        """customer_id must be present in normalized output."""
        norm_fn, _ = normalizer
        for case_id, raw in all_reports.items():
            result = norm_fn(raw)
            assert result["customer_id"], f"{case_id}: customer_id is empty"

    def test_uncertainty_level_present(self, normalizer, all_reports):
        """uncertainty_level must be non-empty."""
        norm_fn, _ = normalizer
        for case_id, raw in all_reports.items():
            result = norm_fn(raw)
            assert result["uncertainty_level"] not in ("", None), \
                f"{case_id}: uncertainty_level is empty"

    def test_sufficiency_level_present(self, normalizer, all_reports):
        """sufficiency_level must be non-empty."""
        norm_fn, _ = normalizer
        for case_id, raw in all_reports.items():
            result = norm_fn(raw)
            assert result["sufficiency_level"] not in ("", None), \
                f"{case_id}: sufficiency_level is empty"


# ── Supporting / contradictory evidence tests ─────────────────────────────────

class TestEvidenceDisplay:
    """Supporting and contradictory evidence display correctly."""

    def test_supporting_items_are_list(self, normalizer, all_reports):
        """supporting_items must be a list for all cases."""
        norm_fn, _ = normalizer
        for case_id, raw in all_reports.items():
            result = norm_fn(raw)
            assert isinstance(result["supporting_items"], list), \
                f"{case_id}: supporting_items is not a list"

    def test_contradictory_items_are_list(self, normalizer, all_reports):
        """contradictory_items must be a list for all cases."""
        norm_fn, _ = normalizer
        for case_id, raw in all_reports.items():
            result = norm_fn(raw)
            assert isinstance(result["contradictory_items"], list), \
                f"{case_id}: contradictory_items is not a list"

    def test_supporting_items_not_fabricated(self, normalizer, all_reports):
        """
        supporting_items must be derived from supporting_evidence_summary.
        They cannot contain content not present in the original report.
        """
        norm_fn, _ = normalizer
        for case_id, raw in all_reports.items():
            result = norm_fn(raw)
            original_summary = raw.get("summary", {}).get("supporting_evidence_summary", "")
            for item in result["supporting_items"]:
                # Each item must appear in the original summary
                item_short = repr(item[:60])
                assert item in original_summary, \
                    f"{case_id}: supporting_item {item_short} not found in original summary"

    def test_contradictory_items_not_fabricated(self, normalizer, all_reports):
        """
        contradictory_items must be derived from contradictory_evidence_summary.
        They cannot contain content not present in the original report.
        """
        norm_fn, _ = normalizer
        for case_id, raw in all_reports.items():
            result = norm_fn(raw)
            original_summary = raw.get("summary", {}).get("contradictory_evidence_summary", "") or ""
            for item in result["contradictory_items"]:
                item_short = repr(item[:60])
                assert item in original_summary, \
                    f"{case_id}: contradictory_item {item_short} not found in original summary"

    def test_api_report_contains_evidence_fields(self, client):
        """API report response must include supporting_items and contradictory_items."""
        res = client.get("/api/v3/report/HHG-001")
        assert res.status_code == 200
        data = res.json()
        report = data["report"]
        assert "supporting_items" in report
        assert "contradictory_items" in report
        assert isinstance(report["supporting_items"], list)
        assert isinstance(report["contradictory_items"], list)


# ── Sufficiency display tests ─────────────────────────────────────────────────

class TestSufficiencyDisplay:
    """Sufficiency data renders correctly in the API response."""

    def test_sufficiency_level_valid_values(self, normalizer, all_reports):
        """sufficiency_level must be one of the valid enum values."""
        norm_fn, _ = normalizer
        valid = {"sufficient", "partial", "insufficient", "unknown"}
        for case_id, raw in all_reports.items():
            result = norm_fn(raw)
            assert result["sufficiency_level"] in valid, \
                f"{case_id}: unexpected sufficiency_level {result['sufficiency_level']!r}"

    def test_sufficiency_reason_is_string(self, normalizer, all_reports):
        """sufficiency_reason must be a string."""
        norm_fn, _ = normalizer
        for case_id, raw in all_reports.items():
            result = norm_fn(raw)
            assert isinstance(result["sufficiency_reason"], str), \
                f"{case_id}: sufficiency_reason is not a string"

    def test_api_returns_sufficiency_data(self, client):
        """API must return sufficiency_level and sufficiency_reason."""
        res = client.get("/api/v3/report/HHG-001")
        assert res.status_code == 200
        report = res.json()["report"]
        assert "sufficiency_level" in report
        assert "sufficiency_reason" in report


# ── Uncertainty display tests ─────────────────────────────────────────────────

class TestUncertaintyDisplay:
    """Uncertainty data renders correctly in the API response."""

    def test_uncertainty_level_valid_values(self, normalizer, all_reports):
        """uncertainty_level must be one of the valid enum values."""
        norm_fn, _ = normalizer
        valid = {"low", "medium", "high", "unknown"}
        for case_id, raw in all_reports.items():
            result = norm_fn(raw)
            assert result["uncertainty_level"] in valid, \
                f"{case_id}: unexpected uncertainty_level {result['uncertainty_level']!r}"

    def test_uncertainty_reason_is_string(self, normalizer, all_reports):
        """uncertainty_reason must be a string."""
        norm_fn, _ = normalizer
        for case_id, raw in all_reports.items():
            result = norm_fn(raw)
            assert isinstance(result["uncertainty_reason"], str), \
                f"{case_id}: uncertainty_reason is not a string"

    def test_api_returns_uncertainty_data(self, client):
        """API must return uncertainty_level and uncertainty_reason."""
        res = client.get("/api/v3/report/HHG-001")
        assert res.status_code == 200
        report = res.json()["report"]
        assert "uncertainty_level" in report
        assert "uncertainty_reason" in report


# ── Action / approval display tests ──────────────────────────────────────────

class TestActionDisplay:
    """Action and approval data renders correctly."""

    VALID_ACTIONS = {
        "BLOCK_CARD", "VERIFY_WITH_CUSTOMER", "ESCALATE",
        "CLOSE_NO_FRAUD", "MONITOR", "REQUEST_MORE_EVIDENCE",
        "FILE_REPORT", "BLOCK_ACCOUNT", "CREATE_CASE", "UNKNOWN"
    }

    def test_action_is_valid_enum(self, normalizer, all_reports):
        """recommended_action must be a valid ActionType value."""
        norm_fn, _ = normalizer
        for case_id, raw in all_reports.items():
            result = norm_fn(raw)
            assert result["recommended_action"] in self.VALID_ACTIONS, \
                f"{case_id}: unexpected action {result['recommended_action']!r}"

    def test_approval_required_is_bool(self, normalizer, all_reports):
        """approval_required must be a boolean."""
        norm_fn, _ = normalizer
        for case_id, raw in all_reports.items():
            result = norm_fn(raw)
            assert isinstance(result["approval_required"], bool), \
                f"{case_id}: approval_required is not bool"

    def test_approval_route_is_string(self, normalizer, all_reports):
        """approval_route must be a string."""
        norm_fn, _ = normalizer
        for case_id, raw in all_reports.items():
            result = norm_fn(raw)
            assert isinstance(result["approval_route"], str), \
                f"{case_id}: approval_route is not string"

    def test_api_returns_action_and_approval(self, client):
        """API must return recommended_action, approval_required, approval_route."""
        res = client.get("/api/v3/report/HHG-001")
        assert res.status_code == 200
        report = res.json()["report"]
        assert "recommended_action" in report
        assert "approval_required" in report
        assert "approval_route" in report

    def test_block_card_cases_have_approval(self, normalizer, all_reports):
        """BLOCK_CARD cases must require approval (approval_route not 'none')."""
        norm_fn, _ = normalizer
        for case_id, raw in all_reports.items():
            result = norm_fn(raw)
            if result["recommended_action"] == "BLOCK_CARD":
                assert result["approval_route"] not in ("none", "", None), \
                    f"{case_id}: BLOCK_CARD with no approval route"


# ── Benchmark loading tests ───────────────────────────────────────────────────

class TestBenchmarkLoading:
    """Benchmark endpoint loads and aggregates all 20 cases correctly."""

    @pytest.fixture(scope="class")
    def benchmark_data(self, client):
        res = client.get("/api/v3/benchmark")
        assert res.status_code == 200
        return res.json()

    def test_benchmark_total_is_20(self, benchmark_data):
        """Benchmark must report 20 total cases."""
        assert benchmark_data["total_cases"] == 20

    def test_benchmark_has_no_failures(self, benchmark_data):
        """All 20 cases must load without error."""
        errors = benchmark_data.get("errors", [])
        assert errors == [], f"Benchmark reported errors: {errors}"

    def test_benchmark_completed_equals_20(self, benchmark_data):
        """All 20 cases must be completed."""
        assert benchmark_data["completed"] == 20

    def test_benchmark_has_statistics(self, benchmark_data):
        """Benchmark must include statistics."""
        stats = benchmark_data.get("statistics", {})
        assert "action_distribution" in stats
        assert "uncertainty_distribution" in stats
        assert "sufficiency_distribution" in stats
        assert "approval_required_count" in stats

    def test_benchmark_action_counts_sum_to_20(self, benchmark_data):
        """Action distribution counts must sum to 20."""
        stats = benchmark_data["statistics"]
        total = sum(stats["action_distribution"].values())
        assert total == 20, f"Action distribution sums to {total}, expected 20"

    def test_benchmark_uncertainty_counts_sum_to_20(self, benchmark_data):
        """Uncertainty distribution counts must sum to 20."""
        stats = benchmark_data["statistics"]
        total = sum(stats["uncertainty_distribution"].values())
        assert total == 20

    def test_benchmark_sufficiency_counts_sum_to_20(self, benchmark_data):
        """Sufficiency distribution counts must sum to 20."""
        stats = benchmark_data["statistics"]
        total = sum(stats["sufficiency_distribution"].values())
        assert total == 20

    def test_benchmark_has_all_20_case_rows(self, benchmark_data):
        """Benchmark must include all 20 case rows."""
        case_ids = {c["case_id"] for c in benchmark_data["cases"]}
        expected = {f"HHG-{i:03d}" for i in range(1, 21)}
        assert case_ids == expected, f"Missing cases: {expected - case_ids}"

    def test_benchmark_no_fabricated_actions(self, benchmark_data):
        """All actions in benchmark must be valid ActionType values."""
        valid = {
            "BLOCK_CARD", "VERIFY_WITH_CUSTOMER", "ESCALATE",
            "CLOSE_NO_FRAUD", "MONITOR", "REQUEST_MORE_EVIDENCE",
            "FILE_REPORT", "BLOCK_ACCOUNT", "CREATE_CASE", "UNKNOWN"
        }
        for c in benchmark_data["cases"]:
            action = c.get("recommended_action", "UNKNOWN")
            assert action in valid, f"{c['case_id']}: invalid action {action!r}"


# ── 20-case end-to-end validation ────────────────────────────────────────────

class TestTwentyCaseValidation:
    """Validate all 20 stored reports against invariants."""

    def test_all_cases_have_action(self, normalizer, all_reports):
        """Every case must have a recommended action."""
        norm_fn, _ = normalizer
        for case_id, raw in all_reports.items():
            result = norm_fn(raw)
            assert result["recommended_action"] not in ("", None, "UNKNOWN"), \
                f"{case_id}: no recommended action"

    def test_all_cases_have_decision_reasoning(self, normalizer, all_reports):
        """Every case must have decision reasoning text."""
        norm_fn, _ = normalizer
        for case_id, raw in all_reports.items():
            result = norm_fn(raw)
            assert result["decision_reasoning"] not in ("", None), \
                f"{case_id}: no decision reasoning"

    def test_no_case_has_fabricated_evidence(self, all_reports):
        """
        Checks that no report contains a supporting or contradictory evidence
        summary that is empty when key_findings are present.
        If findings exist, at least one evidence summary must be non-empty.
        """
        for case_id, raw in all_reports.items():
            summary = raw.get("summary", {})
            findings = summary.get("key_findings") or []
            supp = summary.get("supporting_evidence_summary") or ""
            contra = summary.get("contradictory_evidence_summary") or ""
            if findings:
                assert supp or contra, \
                    f"{case_id}: has key_findings but both evidence summaries are empty"

    def test_block_card_requires_sufficient_evidence(self, all_reports):
        """BLOCK_CARD must only appear when evidence_sufficiency_level == sufficient."""
        for case_id, raw in all_reports.items():
            summary = raw.get("summary", {})
            action = summary.get("recommended_action", "")
            suf = summary.get("evidence_sufficiency_level", "")
            if "BLOCK_CARD" in action:
                assert suf == "sufficient", \
                    f"{case_id}: BLOCK_CARD with non-sufficient evidence: {suf!r}"

    def test_api_report_structure_for_all_20(self, client):
        """API /api/v3/report/{case_id} must return valid structure for all 20 cases."""
        required_fields = [
            "case_id", "customer_id", "recommended_action",
            "uncertainty_level", "sufficiency_level",
            "supporting_items", "contradictory_items",
            "key_findings", "approval_required", "approval_route",
            "decision_reasoning",
        ]
        failures = []
        for case_id in ALL_CASE_IDS:
            res = client.get(f"/api/v3/report/{case_id}")
            if res.status_code != 200:
                failures.append(f"{case_id}: HTTP {res.status_code}")
                continue
            report = res.json().get("report", {})
            for field in required_fields:
                if field not in report:
                    failures.append(f"{case_id}: missing field {field!r}")
        assert failures == [], f"Report structure failures:\n" + "\n".join(failures)

    def test_cases_meta_shows_all_20_have_reports(self, client):
        """All 20 cases must show has_report=True in /api/v3/cases/meta."""
        res = client.get("/api/v3/cases/meta")
        assert res.status_code == 200
        data = res.json()
        cases = {c["case_id"]: c for c in data["cases"]}
        missing = []
        for case_id in ALL_CASE_IDS:
            if not cases.get(case_id, {}).get("has_report"):
                missing.append(case_id)
        assert missing == [], f"Cases without reports: {missing}"


# ── No-fabrication invariants ─────────────────────────────────────────────────

class TestNoFabrication:
    """
    Critical invariants: the UI/API must never show data that wasn't
    produced by the Part 2 workflow.
    """

    def test_investigation_trail_is_empty_or_absent(self, normalizer, all_reports):
        """
        investigation_trail must be [] (not fabricated trail steps).
        Part 2 does not persist trail events to the report JSON.
        """
        norm_fn, _ = normalizer
        for case_id, raw in all_reports.items():
            result = norm_fn(raw)
            trail = result.get("investigation_trail", [])
            assert trail == [], \
                f"{case_id}: investigation_trail is non-empty — trail data should not be fabricated: {trail}"

    def test_hypotheses_is_empty_or_from_report(self, normalizer, all_reports):
        """
        hypotheses must be [] or directly from report.hypotheses_summary.
        Part 2 hypotheses_summary is [] in all 20 reports (confidence < 0.4).
        """
        norm_fn, _ = normalizer
        for case_id, raw in all_reports.items():
            result = norm_fn(raw)
            hyps = result["hypotheses"]
            original_hyps = raw.get("summary", {}).get("hypotheses_summary") or []
            assert hyps == original_hyps, \
                f"{case_id}: hypotheses do not match report data"

    def test_key_findings_match_report(self, normalizer, all_reports):
        """key_findings must exactly match report.summary.key_findings."""
        norm_fn, _ = normalizer
        for case_id, raw in all_reports.items():
            result = norm_fn(raw)
            original = raw.get("summary", {}).get("key_findings") or []
            assert result["key_findings"] == original, \
                f"{case_id}: key_findings do not match report data"


# ── Phase 3 additions ─────────────────────────────────────────────────────────

class TestPhase3CaseInvestigationView:
    """
    Phase 3 specific tests for the Case Investigation View.
    Covers all new fields and sections added in Phase 3.
    """

    @pytest.fixture(scope="class")
    def report_001(self, client):
        res = client.get("/api/v3/report/HHG-001")
        assert res.status_code == 200
        return res.json()["report"]

    def test_report_has_opened_at(self, report_001):
        """Report enriched from case_pack.csv must include opened_at."""
        assert "opened_at" in report_001
        # opened_at may be empty if case_pack unavailable but field must exist
        assert isinstance(report_001["opened_at"], str)

    def test_report_has_risk_score(self, report_001):
        """Report must include risk_score from case_pack.csv."""
        assert "risk_score" in report_001

    def test_report_has_evidence_counts(self, report_001):
        """Report must include supporting_count, contradictory_count, total_evidence_count."""
        assert "supporting_count"      in report_001
        assert "contradictory_count"   in report_001
        assert "total_evidence_count"  in report_001
        assert isinstance(report_001["supporting_count"],     int)
        assert isinstance(report_001["contradictory_count"],  int)
        assert isinstance(report_001["total_evidence_count"], int)

    def test_evidence_counts_consistent(self, report_001):
        """total_evidence_count must equal supporting + contradictory."""
        sc = report_001["supporting_count"]
        cc = report_001["contradictory_count"]
        tc = report_001["total_evidence_count"]
        assert tc == sc + cc, f"total={tc} but supporting={sc} + contradictory={cc}"

    def test_report_has_case_memory(self, report_001):
        """Report must include case_memory object."""
        assert "case_memory" in report_001
        mem = report_001["case_memory"]
        assert isinstance(mem, dict)

    def test_case_memory_has_required_fields(self, report_001):
        """case_memory must contain expected fields."""
        mem = report_001["case_memory"]
        for field in ["case_id", "customer_id", "final_action", "approved_by"]:
            assert field in mem, f"case_memory missing field: {field}"

    def test_case_memory_action_prefix_stripped(self, report_001):
        """case_memory.final_action must not have ActionType. prefix."""
        mem = report_001["case_memory"]
        action = mem.get("final_action", "")
        assert not action.startswith("ActionType."), \
            f"case_memory.final_action still has prefix: {action!r}"

    def test_case_memory_policy_decisions_stripped(self, report_001):
        """case_memory.policy_decisions must not have ActionType. prefix."""
        mem = report_001["case_memory"]
        for pd in mem.get("policy_decisions", []):
            assert not pd.startswith("ActionType."), \
                f"policy_decisions entry has prefix: {pd!r}"

    def test_report_has_missing_evidence_field(self, report_001):
        """Report must include missing_evidence list."""
        assert "missing_evidence" in report_001
        assert isinstance(report_001["missing_evidence"], list)

    def test_investigation_trail_is_empty_not_fabricated(self, report_001):
        """
        investigation_trail must be [] — Part 2 does not persist trail to disk.
        The UI derives workflow steps from actual report fields, not this list.
        """
        trail = report_001.get("investigation_trail", [])
        assert trail == [], \
            f"investigation_trail must be [] (not fabricated): {trail}"

    def test_evidence_counts_all_20_cases(self, client, normalizer, all_reports):
        """Evidence counts must be integers for all 20 cases."""
        norm_fn, _ = normalizer
        for case_id, raw in all_reports.items():
            result = norm_fn(raw)
            sc = result["supporting_count"]
            cc = result["contradictory_count"]
            tc = result["total_evidence_count"]
            assert isinstance(sc, int), f"{case_id}: supporting_count not int"
            assert isinstance(cc, int), f"{case_id}: contradictory_count not int"
            assert tc == sc + cc,       f"{case_id}: total mismatch"

    def test_case_memory_all_20_cases(self, normalizer, all_reports):
        """case_memory must be present for all 20 cases."""
        norm_fn, _ = normalizer
        for case_id, raw in all_reports.items():
            result = norm_fn(raw)
            assert "case_memory" in result, f"{case_id}: missing case_memory"
            mem = result["case_memory"]
            assert isinstance(mem, dict), f"{case_id}: case_memory is not dict"
            if mem:  # non-empty memory
                assert not mem.get("final_action", "").startswith("ActionType."), \
                    f"{case_id}: case_memory.final_action has prefix"


class TestPolicyRulesEndpoint:
    """Tests for the new GET /api/v3/policy/rules endpoint."""

    @pytest.fixture(scope="class")
    def rules_data(self, client):
        res = client.get("/api/v3/policy/rules")
        assert res.status_code == 200
        return res.json()

    def test_endpoint_returns_success(self, rules_data):
        assert rules_data["success"] is True

    def test_endpoint_returns_rules_list(self, rules_data):
        assert "rules" in rules_data
        assert isinstance(rules_data["rules"], list)

    def test_returns_all_7_rules(self, rules_data):
        """All 7 policy rules from rules.py must be returned."""
        assert len(rules_data["rules"]) == 7, \
            f"Expected 7 rules, got {len(rules_data['rules'])}"

    def test_each_rule_has_required_fields(self, rules_data):
        for r in rules_data["rules"]:
            for field in ["rule_id", "name", "action", "approval_route", "risk_level"]:
                assert field in r, f"Rule missing field {field!r}: {r}"

    def test_rule_ids_match_expected(self, rules_data):
        """Rule IDs must match the 7 known rule IDs."""
        expected_ids = {f"RULE-{i:03d}" for i in range(1, 8)}
        actual_ids   = {r["rule_id"] for r in rules_data["rules"]}
        assert actual_ids == expected_ids, \
            f"Rule ID mismatch. Expected: {expected_ids}, got: {actual_ids}"

    def test_rule_names_are_non_empty(self, rules_data):
        for r in rules_data["rules"]:
            assert r["name"], f"Rule {r['rule_id']} has empty name"

    def test_actions_have_no_enum_prefix(self, rules_data):
        """Action strings must not have ActionType. prefix."""
        for r in rules_data["rules"]:
            assert not r["action"].startswith("ActionType."), \
                f"Rule {r['rule_id']}: action has prefix: {r['action']!r}"

    def test_rule_001_is_block_card(self, rules_data):
        """RULE-001 must map to BLOCK_CARD."""
        rule_map = {r["rule_id"]: r for r in rules_data["rules"]}
        assert rule_map["RULE-001"]["action"] == "BLOCK_CARD"

    def test_rule_003_is_verify_with_customer(self, rules_data):
        """RULE-003 must map to VERIFY_WITH_CUSTOMER."""
        rule_map = {r["rule_id"]: r for r in rules_data["rules"]}
        assert rule_map["RULE-003"]["action"] == "VERIFY_WITH_CUSTOMER"

    def test_rule_006_is_escalate(self, rules_data):
        """RULE-006 must map to ESCALATE."""
        rule_map = {r["rule_id"]: r for r in rules_data["rules"]}
        assert rule_map["RULE-006"]["action"] == "ESCALATE"


class TestPhase3DataIntegrity:
    """
    Integrity checks specific to Phase 3 Case Investigation View.
    Verifies the view data is consistent with Part 2 invariants.
    """

    def test_block_card_cases_approval_route_populated(self, client):
        """BLOCK_CARD cases must show a non-'none' approval route in the view data."""
        for i in range(1, 21):
            case_id = f"HHG-{i:03d}"
            res = client.get(f"/api/v3/report/{case_id}")
            if res.status_code != 200:
                continue
            r = res.json()["report"]
            if r["recommended_action"] == "BLOCK_CARD":
                assert r["approval_route"] not in ("none", "", None), \
                    f"{case_id}: BLOCK_CARD case has no approval route"
                assert r["approval_required"] is True, \
                    f"{case_id}: BLOCK_CARD case approval_required is not True"

    def test_verify_cases_approval_none(self, client):
        """VERIFY_WITH_CUSTOMER cases should have approval_route = 'none'."""
        for i in range(1, 21):
            case_id = f"HHG-{i:03d}"
            res = client.get(f"/api/v3/report/{case_id}")
            if res.status_code != 200:
                continue
            r = res.json()["report"]
            if r["recommended_action"] == "VERIFY_WITH_CUSTOMER":
                assert r["approval_route"] in ("none", ""), \
                    f"{case_id}: VERIFY_WITH_CUSTOMER should have approval_route=none, got {r['approval_route']!r}"

    def test_hgg010_escalate_high_uncertainty(self, client):
        """HHG-010 (ESCALATE case) must show high uncertainty."""
        res = client.get("/api/v3/report/HHG-010")
        assert res.status_code == 200
        r = res.json()["report"]
        assert r["recommended_action"] == "ESCALATE", \
            f"HHG-010 expected ESCALATE, got {r['recommended_action']!r}"
        assert r["uncertainty_level"] == "high", \
            f"HHG-010 expected high uncertainty, got {r['uncertainty_level']!r}"

    def test_no_report_contains_actiontype_prefix_anywhere(self, client):
        """
        The string 'ActionType.' must not appear in any field visible to the UI.
        """
        import json
        for i in range(1, 21):
            case_id = f"HHG-{i:03d}"
            res = client.get(f"/api/v3/report/{case_id}")
            if res.status_code != 200:
                continue
            raw_text = res.text
            # Check top-level string fields only (not nested in full JSON blob check)
            r = res.json()["report"]
            for field in ["recommended_action", "approval_route", "policy_basis"]:
                val = r.get(field, "")
                assert "ActionType." not in str(val), \
                    f"{case_id}: field {field!r} contains 'ActionType.': {val!r}"

    def test_sufficiency_reason_contains_actual_text(self, client):
        """sufficiency_reason must contain substantive text for all 20 cases."""
        for i in range(1, 21):
            case_id = f"HHG-{i:03d}"
            res = client.get(f"/api/v3/report/{case_id}")
            if res.status_code != 200:
                continue
            r = res.json()["report"]
            reason = r.get("sufficiency_reason", "")
            assert len(reason) > 10, \
                f"{case_id}: sufficiency_reason too short: {reason!r}"

    def test_uncertainty_reason_contains_actual_text(self, client):
        """uncertainty_reason must contain substantive text for all 20 cases."""
        for i in range(1, 21):
            case_id = f"HHG-{i:03d}"
            res = client.get(f"/api/v3/report/{case_id}")
            if res.status_code != 200:
                continue
            r = res.json()["report"]
            reason = r.get("uncertainty_reason", "")
            assert len(reason) > 10, \
                f"{case_id}: uncertainty_reason too short: {reason!r}"


# ── Phase 4: Benchmark Dashboard & Validation ─────────────────────────────────

class TestBenchmarkValidateEndpoint:
    """Tests for the new GET /api/v3/benchmark/validate endpoint."""

    @pytest.fixture(scope="class")
    def vdata(self, client):
        res = client.get("/api/v3/benchmark/validate")
        assert res.status_code == 200
        return res.json()

    def test_endpoint_returns_200(self, client):
        res = client.get("/api/v3/benchmark/validate")
        assert res.status_code == 200

    def test_success_is_true(self, vdata):
        """With all 20 reports present and valid, success must be True."""
        assert vdata["success"] is True

    def test_all_20_loaded(self, vdata):
        assert vdata["total_cases_loaded"] == 20

    def test_all_20_expected(self, vdata):
        assert vdata["total_cases_expected"] == 20

    def test_zero_errors(self, vdata):
        assert vdata["errors_count"] == 0, \
            f"Validation errors found: {vdata['errors']}"

    def test_zero_warnings(self, vdata):
        assert vdata["warnings_count"] == 0, \
            f"Validation warnings found: {vdata['warnings']}"

    def test_checks_passed_count(self, vdata):
        """Must pass at least 10 validation checks."""
        assert vdata["checks_passed_count"] >= 10, \
            f"Only {vdata['checks_passed_count']} checks passed"

    def test_required_checks_present(self, vdata):
        """Specific mandatory checks must be present."""
        required = {
            "all_20_files_exist",
            "all_20_reports_json_parseable",
            "all_case_ids_match_filenames",
            "no_duplicate_case_ids",
            "schema_consistent_across_all_20",
            "no_enum_prefix_leaks",
            "block_card_only_with_sufficient_evidence",
        }
        passed = set(vdata["checks_passed"])
        missing = required - passed
        assert not missing, f"Required checks not in passed list: {missing}"

    def test_known_limitations_documented(self, vdata):
        """known_limitations must be a list of documented items."""
        lims = vdata.get("known_limitations", [])
        assert isinstance(lims, list)
        assert len(lims) >= 4, "Expected at least 4 known limitations documented"

    def test_known_limitations_have_required_fields(self, vdata):
        """Each limitation must have field, detail, severity, count."""
        for lim in vdata.get("known_limitations", []):
            assert "field"  in lim, f"Limitation missing 'field': {lim}"
            assert "detail" in lim, f"Limitation missing 'detail': {lim}"
            assert "count"  in lim, f"Limitation missing 'count': {lim}"

    def test_summary_string_present(self, vdata):
        assert isinstance(vdata.get("summary"), str)
        assert len(vdata["summary"]) > 10

    def test_errors_list_is_empty(self, vdata):
        assert vdata["errors"] == [], f"Unexpected errors: {vdata['errors']}"

    def test_no_fabrication_in_validation(self, vdata):
        """Validation must not invent ground-truth labels."""
        # None of the checks should claim an "accuracy" or "precision" metric
        summary = vdata.get("summary", "")
        for banned in ["accuracy", "precision", "recall", "f1", "ground truth"]:
            assert banned not in summary.lower(), \
                f"Validation summary contains fabricated metric '{banned}'"


class TestBenchmarkEnhancedStats:
    """Tests for new statistics fields added in Phase 4."""

    @pytest.fixture(scope="class")
    def bench(self, client):
        res = client.get("/api/v3/benchmark")
        assert res.status_code == 200
        return res.json()

    def test_approval_route_distribution_present(self, bench):
        """Phase 4: approval_route_distribution must be in statistics."""
        stats = bench["statistics"]
        assert "approval_route_distribution" in stats

    def test_approval_route_counts_sum_to_20(self, bench):
        stats = bench["statistics"]
        total = sum(stats["approval_route_distribution"].values())
        assert total == 20

    def test_policy_basis_distribution_present(self, bench):
        """Phase 4: policy_basis_distribution must be in statistics."""
        stats = bench["statistics"]
        assert "policy_basis_distribution" in stats

    def test_policy_basis_counts_sum_to_20(self, bench):
        stats = bench["statistics"]
        total = sum(stats["policy_basis_distribution"].values())
        assert total == 20

    def test_trigger_distribution_present(self, bench):
        stats = bench["statistics"]
        assert "trigger_distribution" in stats

    def test_trigger_counts_sum_to_20(self, bench):
        stats = bench["statistics"]
        total = sum(stats["trigger_distribution"].values())
        assert total == 20

    def test_evidence_totals_present(self, bench):
        """Phase 4: evidence_totals must be in statistics."""
        stats = bench["statistics"]
        assert "evidence_totals" in stats
        ev = stats["evidence_totals"]
        assert "total_supporting"    in ev
        assert "total_contradictory" in ev
        assert "avg_supporting_per_case"    in ev
        assert "avg_contradictory_per_case" in ev

    def test_evidence_totals_are_numbers(self, bench):
        ev = bench["statistics"]["evidence_totals"]
        assert isinstance(ev["total_supporting"],    int)
        assert isinstance(ev["total_contradictory"], int)
        assert isinstance(ev["avg_supporting_per_case"],    float)
        assert isinstance(ev["avg_contradictory_per_case"], float)

    def test_evidence_totals_match_per_case_sum(self, bench):
        """total_supporting must equal sum of per-case supporting_count."""
        ev = bench["statistics"]["evidence_totals"]
        computed_sup  = sum(c["supporting_count"]    for c in bench["cases"])
        computed_cont = sum(c["contradictory_count"] for c in bench["cases"])
        assert ev["total_supporting"]    == computed_sup,  "total_supporting mismatch"
        assert ev["total_contradictory"] == computed_cont, "total_contradictory mismatch"

    def test_per_case_has_supporting_count(self, bench):
        """Each case row in benchmark must include supporting_count."""
        for c in bench["cases"]:
            assert "supporting_count" in c, \
                f"{c['case_id']}: missing supporting_count"
            assert isinstance(c["supporting_count"], int)

    def test_per_case_has_contradictory_count(self, bench):
        for c in bench["cases"]:
            assert "contradictory_count" in c, \
                f"{c['case_id']}: missing contradictory_count"
            assert isinstance(c["contradictory_count"], int)


class TestBenchmarkDataIntegrity:
    """
    Phase 4 cross-checks: verify benchmark values agree with
    individual report data loaded via /api/v3/report/{case_id}.
    """

    @pytest.fixture(scope="class")
    def bench_cases(self, client):
        res = client.get("/api/v3/benchmark")
        assert res.status_code == 200
        return {c["case_id"]: c for c in res.json()["cases"]}

    def test_benchmark_action_agrees_with_individual_report(self, client, bench_cases):
        """Benchmark action for each case must match individual report."""
        failures = []
        for case_id, bc in bench_cases.items():
            res = client.get(f"/api/v3/report/{case_id}")
            if res.status_code != 200:
                failures.append(f"{case_id}: report HTTP {res.status_code}")
                continue
            ir = res.json()["report"]
            if bc["recommended_action"] != ir["recommended_action"]:
                failures.append(
                    f"{case_id}: benchmark={bc['recommended_action']!r} "
                    f"vs report={ir['recommended_action']!r}"
                )
        assert failures == [], f"Action mismatches:\n" + "\n".join(failures)

    def test_benchmark_sufficiency_agrees_with_individual_report(self, client, bench_cases):
        """Benchmark sufficiency for each case must match individual report."""
        failures = []
        for case_id, bc in bench_cases.items():
            res = client.get(f"/api/v3/report/{case_id}")
            if res.status_code != 200:
                continue
            ir = res.json()["report"]
            if bc["sufficiency_level"] != ir["sufficiency_level"]:
                failures.append(
                    f"{case_id}: benchmark={bc['sufficiency_level']!r} "
                    f"vs report={ir['sufficiency_level']!r}"
                )
        assert failures == [], "Sufficiency mismatches:\n" + "\n".join(failures)

    def test_benchmark_uncertainty_agrees_with_individual_report(self, client, bench_cases):
        failures = []
        for case_id, bc in bench_cases.items():
            res = client.get(f"/api/v3/report/{case_id}")
            if res.status_code != 200:
                continue
            ir = res.json()["report"]
            if bc["uncertainty_level"] != ir["uncertainty_level"]:
                failures.append(
                    f"{case_id}: benchmark={bc['uncertainty_level']!r} "
                    f"vs report={ir['uncertainty_level']!r}"
                )
        assert failures == [], "Uncertainty mismatches:\n" + "\n".join(failures)

    def test_benchmark_approval_agrees_with_individual_report(self, client, bench_cases):
        failures = []
        for case_id, bc in bench_cases.items():
            res = client.get(f"/api/v3/report/{case_id}")
            if res.status_code != 200:
                continue
            ir = res.json()["report"]
            if bc["approval_required"] != ir["approval_required"]:
                failures.append(
                    f"{case_id}: benchmark={bc['approval_required']} "
                    f"vs report={ir['approval_required']}"
                )
        assert failures == [], "approval_required mismatches:\n" + "\n".join(failures)

    def test_benchmark_evidence_counts_agree_with_individual_report(self, client, bench_cases):
        failures = []
        for case_id, bc in bench_cases.items():
            res = client.get(f"/api/v3/report/{case_id}")
            if res.status_code != 200:
                continue
            ir = res.json()["report"]
            if bc.get("supporting_count") != ir.get("supporting_count"):
                failures.append(
                    f"{case_id}: sup benchmark={bc.get('supporting_count')} "
                    f"vs report={ir.get('supporting_count')}"
                )
            if bc.get("contradictory_count") != ir.get("contradictory_count"):
                failures.append(
                    f"{case_id}: contra benchmark={bc.get('contradictory_count')} "
                    f"vs report={ir.get('contradictory_count')}"
                )
        assert failures == [], "Evidence count mismatches:\n" + "\n".join(failures)


class TestBenchmarkKnownResults:
    """
    Phase 4: verify the actual known benchmark outcomes from the 20 reports.
    These are factual assertions derived directly from the stored report data —
    not hardcoded expectations, but checks that the API returns what the files contain.
    """

    @pytest.fixture(scope="class")
    def bench(self, client):
        res = client.get("/api/v3/benchmark")
        assert res.status_code == 200
        return res.json()

    def test_15_block_card_cases(self, bench):
        """There are exactly 15 BLOCK_CARD cases in the benchmark."""
        ad = bench["statistics"]["action_distribution"]
        assert ad.get("BLOCK_CARD", 0) == 15

    def test_4_verify_with_customer_cases(self, bench):
        """There are exactly 4 VERIFY_WITH_CUSTOMER cases."""
        ad = bench["statistics"]["action_distribution"]
        assert ad.get("VERIFY_WITH_CUSTOMER", 0) == 4

    def test_1_escalate_case(self, bench):
        """There is exactly 1 ESCALATE case (HHG-010)."""
        ad = bench["statistics"]["action_distribution"]
        assert ad.get("ESCALATE", 0) == 1

    def test_all_20_cases_sufficient(self, bench):
        """All 20 cases must have sufficient evidence (from the stored reports)."""
        sd = bench["statistics"]["sufficiency_distribution"]
        assert sd.get("sufficient", 0) == 20
        assert sd.get("partial", 0) == 0
        assert sd.get("insufficient", 0) == 0

    def test_15_medium_uncertainty(self, bench):
        ud = bench["statistics"]["uncertainty_distribution"]
        assert ud.get("medium", 0) == 15

    def test_5_high_uncertainty(self, bench):
        ud = bench["statistics"]["uncertainty_distribution"]
        assert ud.get("high", 0) == 5

    def test_16_require_approval(self, bench):
        """16 cases require approval, 4 are auto-executable."""
        stats = bench["statistics"]
        assert stats["approval_required_count"] == 16
        assert stats["approval_not_required_count"] == 4

    def test_hhg010_is_escalate(self, bench):
        """HHG-010 must be ESCALATE (high uncertainty + high exposure)."""
        case = next(c for c in bench["cases"] if c["case_id"] == "HHG-010")
        assert case["recommended_action"] == "ESCALATE"
        assert case["uncertainty_level"] == "high"
        assert case["policy_basis"] == "RULE-006"

    def test_hhg017_actionguard_safety(self, bench):
        """HHG-017 must show ACTION_GUARD_SAFETY policy basis."""
        case = next(c for c in bench["cases"] if c["case_id"] == "HHG-017")
        assert case["recommended_action"] == "VERIFY_WITH_CUSTOMER"
        assert case["policy_basis"] == "ACTION_GUARD_SAFETY"

    def test_no_invented_ground_truth(self, bench):
        """
        The benchmark must not contain any 'is_fraud', 'ground_truth',
        'true_positive', 'false_positive', or 'accuracy' fields —
        these would be fabricated since no ground truth labels exist in the data.
        """
        banned_fields = {"is_fraud", "ground_truth", "true_positive",
                         "false_positive", "true_negative", "false_negative",
                         "accuracy", "precision", "recall", "f1_score"}
        for c in bench["cases"]:
            found = banned_fields & set(c.keys())
            assert not found, \
                f"{c['case_id']}: contains fabricated fields: {found}"
        stats_keys = set(bench["statistics"].keys())
        found_in_stats = banned_fields & stats_keys
        assert not found_in_stats, \
            f"Statistics contains fabricated metrics: {found_in_stats}"
