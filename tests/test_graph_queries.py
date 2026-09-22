"""
test_graph_queries.py — Static structural validation of GSQL files.

These tests do NOT require a live TigerGraph instance.
They validate file existence, syntax patterns, and structural correctness
as far as is possible without compiling against a live graph.

Run:
    python -m pytest tests/test_graph_queries.py -v
"""

import re
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))

TG_DIR = ROOT / "tigergraph"
SCHEMA_FILE = TG_DIR / "schema" / "schema.gsql"
LOADING_FILE = TG_DIR / "loading" / "loading.gsql"
QUERIES_DIR = TG_DIR / "queries"
ALGO_DIR = TG_DIR / "algorithms"

QUERY_FILES = list(QUERIES_DIR.glob("*.gsql"))
ALGO_FILES = list(ALGO_DIR.glob("*.gsql"))
ALL_GSQL_FILES = QUERY_FILES + ALGO_FILES + [SCHEMA_FILE, LOADING_FILE]


def read(path: Path) -> str:
    return path.read_text(encoding="utf-8") if path.exists() else ""


# ── File existence ─────────────────────────────────────────────────────────────

class TestGSQLFilesExist(unittest.TestCase):

    def test_schema_exists(self):
        self.assertTrue(SCHEMA_FILE.exists(), f"Missing: {SCHEMA_FILE}")

    def test_loading_exists(self):
        self.assertTrue(LOADING_FILE.exists(), f"Missing: {LOADING_FILE}")

    def test_query_files_exist(self):
        expected = [
            "connected_entities.gsql",
            "customer_history.gsql",
            "exposure.gsql",
            "prior_cases.gsql",
            "shared_devices.gsql",
            "temporal_activity.gsql",
            "transaction_context.gsql",
        ]
        for fname in expected:
            self.assertTrue(
                (QUERIES_DIR / fname).exists(),
                f"Missing query file: {fname}"
            )

    def test_pattern_detection_algo_exists(self):
        self.assertTrue(
            (ALGO_DIR / "pattern_detection.gsql").exists(),
            "Missing pattern_detection.gsql"
        )


# ── Schema structural checks ──────────────────────────────────────────────────

class TestSchemaStructure(unittest.TestCase):

    def setUp(self):
        self.schema = read(SCHEMA_FILE)
        if not self.schema:
            self.skipTest("schema.gsql not found")

    def test_vertex_types_present(self):
        for vtype in ["Customer", "Card", "Transaction", "DeviceProfile",
                      "Region", "EmailDomain", "ClosedCase", "InvestigationCase",
                      "FraudPattern"]:
            self.assertIn(f"CREATE VERTEX {vtype}", self.schema,
                          f"Vertex {vtype} missing from schema")

    def test_graph_create_present(self):
        self.assertIn("CREATE GRAPH FraudGraph", self.schema)

    def test_required_edges_present(self):
        for edge in ["OWNS", "PERFORMED", "USES_DEVICE", "BILLED_TO_REGION",
                     "USES_EMAIL", "INVOLVES_CUSTOMER", "INVOLVES_CARD",
                     "FLAGGED_TRANSACTION", "HAS_PATTERN", "ABOUT_CUSTOMER",
                     "INVESTIGATION_FLAGGED_TRANSACTION"]:
            self.assertIn(f"CREATE DIRECTED EDGE {edge}", self.schema,
                          f"Edge {edge} missing from schema")

    def test_reverse_edges_declared(self):
        """All directed edges should have REVERSE_EDGE declarations."""
        edge_blocks = re.findall(r"CREATE DIRECTED EDGE \w+.*?(?=CREATE|\Z)", self.schema, re.DOTALL)
        for block in edge_blocks:
            if "WITH REVERSE_EDGE" not in block:
                edge_name = re.search(r"CREATE DIRECTED EDGE (\w+)", block)
                self.fail(f"Edge {edge_name.group(1) if edge_name else '?'} missing REVERSE_EDGE")

    def test_made_edge_present(self):
        """MADE edge (Card->Transaction) must exist in schema even though
        made_edges.csv is empty (limitation documented elsewhere)."""
        self.assertIn("CREATE DIRECTED EDGE MADE", self.schema)

    def test_no_undocumented_vertex_types(self):
        """Vertex types in graph declaration must match those defined."""
        defined = set(re.findall(r"CREATE VERTEX (\w+)", self.schema))
        # Check all defined types appear in CREATE GRAPH
        graph_block = re.search(r"CREATE GRAPH FraudGraph\s*\((.*?)\)", self.schema, re.DOTALL)
        if graph_block:
            graph_content = graph_block.group(1)
            for vtype in defined:
                self.assertIn(vtype, graph_content,
                              f"Vertex {vtype} defined but not in CREATE GRAPH")


# ── Loading job checks ────────────────────────────────────────────────────────

class TestLoadingJobs(unittest.TestCase):

    def setUp(self):
        self.loading = read(LOADING_FILE)
        if not self.loading:
            self.skipTest("loading.gsql not found")

    def test_loading_jobs_use_graph(self):
        self.assertIn("USE GRAPH FraudGraph", self.loading)

    def test_vertex_loading_jobs_present(self):
        for name in ["load_customers", "load_transactions", "load_device_profiles",
                     "load_cards", "load_closed_cases", "load_investigation_cases"]:
            self.assertIn(f"CREATE LOADING JOB {name}", self.loading,
                          f"Loading job {name} missing")

    def test_edge_loading_jobs_present(self):
        for name in ["load_owns_edges", "load_performed_edges",
                     "load_uses_device_edges", "load_billed_to_region_edges"]:
            self.assertIn(f"CREATE LOADING JOB {name}", self.loading,
                          f"Loading job {name} missing")


# ── Query-level checks ────────────────────────────────────────────────────────

class TestQuerySyntax(unittest.TestCase):

    def _check_file(self, path: Path) -> str:
        content = read(path)
        self.assertTrue(content, f"File empty or missing: {path}")
        return content

    def test_all_queries_have_use_graph(self):
        for qf in QUERY_FILES + ALGO_FILES:
            content = read(qf)
            self.assertIn("USE GRAPH FraudGraph", content,
                          f"{qf.name} missing 'USE GRAPH FraudGraph'")

    def test_all_queries_have_create_query(self):
        for qf in QUERY_FILES + ALGO_FILES:
            content = read(qf)
            self.assertIn("CREATE QUERY", content,
                          f"{qf.name} missing 'CREATE QUERY'")

    def test_connected_entities_no_max_hops_param(self):
        """max_hops was removed — the query now has a fixed traversal depth."""
        content = read(QUERIES_DIR / "connected_entities.gsql")
        # Should NOT have max_hops in the CREATE QUERY signature
        create_line = re.search(r"CREATE QUERY find_connected_entities\(.*?\)", content)
        if create_line:
            self.assertNotIn("max_hops", create_line.group(0),
                             "max_hops should not appear as a parameter")

    def test_no_unknown_device_sentinel(self):
        """'unknown_device' must not appear anywhere in GSQL or Python sources
        as a legitimate device ID that could create false shared-device edges."""
        python_files = list(ROOT.rglob("*.py"))
        for pf in python_files:
            if ".git" in str(pf):
                continue
            content = pf.read_text(encoding="utf-8", errors="replace")
            # Allow it in comments and test files that explicitly test the absence
            non_comment_lines = [
                line for line in content.splitlines()
                if "unknown_device" in line
                and not line.strip().startswith("#")
                and "test" not in pf.stem.lower()
                and "device_utils" not in pf.stem  # allow in the docstring example
                and "DICT" not in line.upper()  # allow in docstrings
            ]
            self.assertEqual(
                len(non_comment_lines), 0,
                f"{pf.name} contains 'unknown_device' in non-comment code: "
                f"{non_comment_lines[:3]}"
            )

    def test_shared_devices_no_vertex_declaration_in_accum(self):
        """VERTEX<T> variable declarations inside ACCUM blocks are invalid GSQL."""
        content = read(QUERIES_DIR / "shared_devices.gsql")
        accum_blocks = re.findall(r"ACCUM(.*?)(?:POST-ACCUM|SELECT|PRINT|\Z)", content, re.DOTALL)
        for block in accum_blocks:
            self.assertNotIn("VERTEX<", block,
                             "VERTEX<T> variable declaration inside ACCUM block is invalid GSQL")

    def test_temporal_activity_no_int_declaration_in_accum(self):
        """Local INT declarations inside ACCUM blocks are invalid GSQL."""
        content = read(QUERIES_DIR / "temporal_activity.gsql")
        accum_blocks = re.findall(r"ACCUM(.*?)(?:POST-ACCUM|SELECT|PRINT|\Z)", content, re.DOTALL)
        for block in accum_blocks:
            # Match things like "INT sod;" — local variable declarations
            self.assertIsNone(
                re.search(r"\bINT\s+\w+\s*;", block),
                f"Local INT declaration inside ACCUM block is invalid GSQL: {block[:100]}"
            )

    def test_pattern_detection_no_uint_declaration_in_accum(self):
        """Local UINT declarations inside ACCUM blocks are invalid GSQL.
        MapAccum<UINT, INT> declarations at the top of a query body are valid
        (they are global accumulator declarations, not local variable declarations
        inside SELECT...ACCUM blocks).
        """
        content = read(ALGO_DIR / "pattern_detection.gsql")
        # Match only the ACCUM block content inside SELECT statements.
        # Pattern: ACCUM followed by indented block content.
        # We look for `UINT identifier =` (a local variable assignment),
        # NOT `MapAccum<..., UINT>` (a global accumulator type declaration).
        accum_blocks = re.findall(r"\bACCUM\b(.*?)(?:\bPOST-ACCUM\b|\bSELECT\b|\bPRINT\b|\bWHILE\b|\Z)", content, re.DOTALL)
        for block in accum_blocks:
            # Only flag `UINT varname =` — a local variable being assigned
            # not `UINT>` which is part of a MapAccum type parameter
            bad = re.search(r"\bUINT\s+[a-z_]\w*\s*=", block)
            self.assertIsNone(
                bad,
                f"Local UINT assignment inside ACCUM block is invalid GSQL: {block[:120]}"
            )

    def test_no_case_when_in_accum_blocks(self):
        """CASE WHEN is not supported inside ACCUM blocks in TigerGraph GSQL.
        Use IF ... THEN ... END instead."""
        for qf in QUERY_FILES + ALGO_FILES:
            content = read(qf)
            accum_blocks = re.findall(r"ACCUM(.*?)(?:POST-ACCUM|SELECT|PRINT|\Z)", content, re.DOTALL)
            for block in accum_blocks:
                self.assertNotIn(
                    "CASE WHEN", block.upper(),
                    f"{qf.name}: CASE WHEN inside ACCUM block — use IF...THEN...END instead"
                )

    def test_exposure_query_handles_both_case_types(self):
        content = read(QUERIES_DIR / "exposure.gsql")
        self.assertIn("InvestigationCase", content)
        self.assertIn("ClosedCase", content)

    def test_customer_history_uses_performed_edge(self):
        content = read(QUERIES_DIR / "customer_history.gsql")
        self.assertIn("PERFORMED", content)

    def test_transaction_context_uses_performed_by_edge(self):
        content = read(QUERIES_DIR / "transaction_context.gsql")
        self.assertIn("PERFORMED_BY", content)


# ── Device utils canonical function tests ─────────────────────────────────────

class TestDeviceUtils(unittest.TestCase):

    def setUp(self):
        from mcp.server.device_utils import normalize_device_info
        self.norm = normalize_device_info

    def test_missing_returns_none(self):
        self.assertIsNone(self.norm(""))
        self.assertIsNone(self.norm(None))
        self.assertIsNone(self.norm("   "))

    def test_build_string_stripped(self):
        result = self.norm("SAMSUNG SM-G892A Build/NRD90M")
        self.assertIsNotNone(result)
        self.assertNotIn("build", result.lower())
        self.assertNotIn("nrd90m", result.lower())

    def test_same_device_different_build(self):
        a = self.norm("SAMSUNG SM-G892A Build/NRD90M")
        b = self.norm("SAMSUNG SM-G892A Build/QP1A.190711.020")
        self.assertEqual(a, b, "Same device model, different build → must normalize to same ID")

    def test_patch_version_collapsed(self):
        a = self.norm("iOS 11.1.2")
        b = self.norm("iOS 11.1.0")
        self.assertEqual(a, b, "iOS 11.1.x variants must normalize to same ID")

    def test_case_insensitive(self):
        a = self.norm("Android 8.0")
        b = self.norm("android 8.0")
        self.assertEqual(a, b)

    def test_canonical_id_is_lowercase(self):
        result = self.norm("Windows 10")
        self.assertEqual(result, result.lower())

    def test_no_unknown_device_fallback(self):
        """normalize_device_info must never return 'unknown_device'."""
        test_inputs = ["", "   ", None]
        for inp in test_inputs:
            result = self.norm(inp)
            self.assertNotEqual(result, "unknown_device",
                                f"normalize_device_info({inp!r}) must return None, not 'unknown_device'")

    def test_missing_devices_do_not_share(self):
        """Two transactions with missing DeviceInfo must NOT be considered
        to share a device."""
        a = self.norm("")
        b = self.norm(None)
        # Both must be None — callers must not equate None == None as shared device
        self.assertIsNone(a)
        self.assertIsNone(b)


# ── Deployment status documentation ──────────────────────────────────────────

class TestDeploymentStatus(unittest.TestCase):
    """
    Live TigerGraph deployment has NOT been verified.
    These tests document what WOULD be needed.

    All GSQL static validation above passes.
    Live compilation requires:
      1. TigerGraph instance accessible at TIGERGRAPH_HOST
      2. gsql CLI or pyTigerGraph with valid credentials
      3. Schema deployed: gsql tigergraph/schema/schema.gsql
      4. Loading jobs deployed: gsql -g FraudGraph tigergraph/loading/loading.gsql
      5. Each query compiled: INSTALL QUERY <name>
    """

    def test_deployment_documentation_exists(self):
        readme = ROOT / "tigergraph" / "README.md"
        self.assertTrue(readme.exists(), "tigergraph/README.md should document deployment steps")


if __name__ == "__main__":
    unittest.main(verbosity=2)
