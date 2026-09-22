"""
test_mcp.py — MCP server and MockClient unit tests.

Tests:
  - Server startup and health endpoint
  - /tools endpoint
  - Valid tool requests
  - Invalid tool name
  - Missing required parameters
  - get_case
  - get_transaction_context
  - get_customer_history
  - find_shared_devices
  - find_prior_cases
  - calculate_exposure
  - detect_temporal_patterns

Run:
    python -m pytest tests/test_mcp.py -v
"""

import json
import sys
import threading
import time
import unittest
import urllib.request
import urllib.error
from http.server import HTTPServer
from pathlib import Path

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))

from mcp.server.mock_client import MockClient
from mcp.server.server import _make_handler, TOOL_SCHEMAS, _dispatch

DATA_DIR = ROOT


# ── Helpers ───────────────────────────────────────────────────────────────────

def _call(port: int, method: str, path: str, body: dict | None = None) -> tuple[int, dict]:
    url = f"http://localhost:{port}{path}"
    data = json.dumps(body).encode("utf-8") if body else None
    req = urllib.request.Request(url, data=data, method=method)
    if data:
        req.add_header("Content-Type", "application/json")
        req.add_header("Content-Length", str(len(data)))
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            return resp.status, json.loads(resp.read())
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read())


_PREWARMED_CLIENT: MockClient | None = None


def get_prewarmed_client() -> MockClient:
    global _PREWARMED_CLIENT
    if _PREWARMED_CLIENT is None:
        _PREWARMED_CLIENT = MockClient(data_dir=DATA_DIR)
        _PREWARMED_CLIENT._build_txn_indexes()  # warm up before server starts
    return _PREWARMED_CLIENT


def _start_server(port: int) -> HTTPServer:
    client = get_prewarmed_client()
    handler_cls = _make_handler(client)
    server = HTTPServer(("localhost", port), handler_cls)
    t = threading.Thread(target=server.serve_forever, daemon=True)
    t.start()
    # Wait for server to be ready
    for _ in range(20):
        try:
            _call(port, "GET", "/health")
            break
        except Exception:
            time.sleep(0.1)
    return server


# ── Server lifecycle tests ─────────────────────────────────────────────────────

class TestServerStartup(unittest.TestCase):
    PORT = 18765

    @classmethod
    def setUpClass(cls):
        cls.server = _start_server(cls.PORT)
        # Pre-resolve HHG-001 customer_id using the direct client (no HTTP round trip)
        client = get_prewarmed_client()
        case = client.get_case("HHG-001")
        cls.hgg001_customer_id = case["case"]["customer_id"]
        cls.hgg001_txn_id = case["case"]["flagged_txn_id"]

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()

    def test_health_returns_200(self):
        status, body = _call(self.PORT, "GET", "/health")
        self.assertEqual(status, 200)
        self.assertEqual(body["status"], "ok")

    def test_health_contains_client_name(self):
        _, body = _call(self.PORT, "GET", "/health")
        self.assertIn("client", body)
        self.assertEqual(body["client"], "MockClient")

    def test_health_lists_tools(self):
        _, body = _call(self.PORT, "GET", "/health")
        self.assertIn("tools", body)
        self.assertIsInstance(body["tools"], list)
        self.assertGreater(len(body["tools"]), 0)

    def test_tools_endpoint_returns_schemas(self):
        status, body = _call(self.PORT, "GET", "/tools")
        self.assertEqual(status, 200)
        self.assertIn("tools", body)
        tools = body["tools"]
        self.assertIn("get_case", tools)
        self.assertIn("get_transaction_context", tools)
        self.assertIn("get_customer_history", tools)

    def test_unknown_get_path_returns_404(self):
        status, _ = _call(self.PORT, "GET", "/nonexistent")
        self.assertEqual(status, 404)

    def test_post_to_wrong_path_returns_404(self):
        status, _ = _call(self.PORT, "POST", "/wrong", {"tool": "get_case", "params": {}})
        self.assertEqual(status, 404)

    def test_invalid_tool_name_returns_400(self):
        status, body = _call(
            self.PORT, "POST", "/tool",
            {"tool": "does_not_exist", "params": {}}
        )
        self.assertEqual(status, 400)
        self.assertIn("error", body)

    def test_missing_required_param_returns_400(self):
        # get_case requires case_id
        status, body = _call(self.PORT, "POST", "/tool", {"tool": "get_case", "params": {}})
        self.assertEqual(status, 400)
        self.assertIn("error", body)

    def test_empty_body_returns_400(self):
        req = urllib.request.Request(
            f"http://localhost:{self.PORT}/tool", data=b"", method="POST"
        )
        req.add_header("Content-Length", "0")
        try:
            with urllib.request.urlopen(req, timeout=5) as resp:
                status = resp.status
        except urllib.error.HTTPError as e:
            status = e.code
        self.assertEqual(status, 400)

    def test_missing_tool_field_returns_400(self):
        status, body = _call(self.PORT, "POST", "/tool", {"params": {}})
        self.assertEqual(status, 400)

    # ── Tool calls ─────────────────────────────────────────────────────────

    def test_get_case_hgg001(self):
        status, body = _call(
            self.PORT, "POST", "/tool",
            {"tool": "get_case", "params": {"case_id": "HHG-001"}}
        )
        self.assertEqual(status, 200)
        result = body["result"]
        self.assertTrue(result["found"], "HHG-001 should be found")
        self.assertEqual(result["case"]["case_id"], "HHG-001")
        self.assertIsNotNone(result.get("flagged_transaction"), "Should have flagged transaction")

    def test_get_case_not_found(self):
        status, body = _call(
            self.PORT, "POST", "/tool",
            {"tool": "get_case", "params": {"case_id": "HHG-999"}}
        )
        self.assertEqual(status, 200)
        result = body["result"]
        self.assertFalse(result["found"])

    def test_get_transaction_context(self):
        status, body = _call(
            self.PORT, "POST", "/tool",
            {"tool": "get_transaction_context", "params": {"txn_id": str(self.hgg001_txn_id)}}
        )
        self.assertEqual(status, 200)
        result = body["result"]
        self.assertTrue(result["found"], f"Transaction {self.hgg001_txn_id} should be found")
        txn = result["transaction"]
        self.assertIsNotNone(txn["TransactionAmt"])
        self.assertIn("channel", txn)

    def test_get_transaction_context_not_found(self):
        status, body = _call(
            self.PORT, "POST", "/tool",
            {"tool": "get_transaction_context", "params": {"txn_id": "9999999999"}}
        )
        self.assertEqual(status, 200)
        self.assertFalse(body["result"]["found"])

    def test_get_customer_history(self):
        status, body = _call(
            self.PORT, "POST", "/tool",
            {"tool": "get_customer_history", "params": {"customer_id": self.hgg001_customer_id}}
        )
        self.assertEqual(status, 200)
        result = body["result"]
        self.assertTrue(result["found"], f"Customer {self.hgg001_customer_id} should have transactions")
        self.assertGreater(result["transaction_count"], 0)
        self.assertIsInstance(result["recent_transactions"], list)

    def test_find_shared_devices(self):
        status, body = _call(
            self.PORT, "POST", "/tool",
            {"tool": "find_shared_devices", "params": {"customer_id": self.hgg001_customer_id}}
        )
        self.assertEqual(status, 200)
        result = body["result"]
        self.assertIn("customer_id", result)
        self.assertIn("devices_found", result)

    def test_find_prior_cases(self):
        status, body = _call(
            self.PORT, "POST", "/tool",
            {"tool": "find_prior_cases", "params": {"customer_id": self.hgg001_customer_id}}
        )
        self.assertEqual(status, 200)
        result = body["result"]
        self.assertIn("total_cases", result)
        self.assertIn("cases", result)

    def test_calculate_exposure(self):
        status, body = _call(
            self.PORT, "POST", "/tool",
            {"tool": "calculate_exposure", "params": {"customer_id": self.hgg001_customer_id}}
        )
        self.assertEqual(status, 200)
        result = body["result"]
        self.assertIn("total_confirmed_exposure_usd", result)
        self.assertIn("confirmed_fraud_cases", result)

    def test_detect_temporal_patterns(self):
        status, body = _call(
            self.PORT, "POST", "/tool",
            {"tool": "detect_temporal_patterns", "params": {"customer_id": self.hgg001_customer_id}}
        )
        self.assertEqual(status, 200)
        result = body["result"]
        self.assertIn("signals", result)
        self.assertIn("card_testing", result["signals"])


# ── Tool schema completeness ──────────────────────────────────────────────────

class TestToolSchemas(unittest.TestCase):

    EXPECTED_TOOLS = [
        "get_case",
        "get_customer_history",
        "find_connected_entities",
        "find_prior_cases",
        "detect_temporal_patterns",
        "calculate_exposure",
        "find_shared_devices",
        "get_transaction_context",
    ]

    def test_all_expected_tools_present(self):
        for tool in self.EXPECTED_TOOLS:
            self.assertIn(tool, TOOL_SCHEMAS, f"Missing tool schema: {tool}")

    def test_each_tool_has_description(self):
        for tool, schema in TOOL_SCHEMAS.items():
            self.assertIn("description", schema, f"Tool {tool} missing description")
            self.assertTrue(schema["description"], f"Tool {tool} has empty description")

    def test_each_tool_has_params(self):
        for tool, schema in TOOL_SCHEMAS.items():
            self.assertIn("params", schema, f"Tool {tool} missing params")


# ── MockClient dispatch tests (no HTTP) ───────────────────────────────────────

class TestMockClientDirect(unittest.TestCase):
    """Test the MockClient directly without HTTP overhead."""

    @classmethod
    def setUpClass(cls):
        cls.client = MockClient(data_dir=DATA_DIR)

    def test_is_connected(self):
        self.assertTrue(self.client.is_connected())

    def test_get_case_returns_structure(self):
        result = self.client.get_case("HHG-001")
        self.assertIn("found", result)
        self.assertIn("case_id", result)

    def test_missing_device_does_not_create_relationship(self):
        """
        Customers with no identity rows should return devices_found=0.
        Missing DeviceInfo must NOT produce shared-device relationships.
        """
        # Use a customer whose transactions have no identity row
        # by finding a customer_id not in identity.csv
        import csv
        identity_txn_ids: set[str] = set()
        id_path = DATA_DIR / "identity.csv"
        if id_path.exists():
            with open(id_path, encoding="utf-8", errors="replace") as f:
                reader = csv.DictReader(f)
                for row in reader:
                    identity_txn_ids.add(row.get("TransactionID", "").strip())

        # Find a customer whose transactions are all absent from identity
        cust_idx = self.client._get_customer_txn_idx()
        no_device_cid = None
        for cid, tids in cust_idx.items():
            if not any(tid in identity_txn_ids for tid in tids):
                no_device_cid = cid
                break

        if no_device_cid is None:
            self.skipTest("Could not find a customer with no identity records")

        result = self.client.find_shared_devices(no_device_cid)
        self.assertEqual(result["devices_found"], 0,
                         "Missing DeviceInfo must not create device relationships")
        self.assertIn("message", result)


if __name__ == "__main__":
    unittest.main(verbosity=2)
