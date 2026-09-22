"""
server.py — FraudGraph MCP Server

JSON-RPC HTTP server exposing fraud investigation tools.
Listens on http://localhost:{MCP_PORT} (default: 8765).

Automatically falls back to MockClient (CSV-based) if TigerGraph
is unavailable or pyTigerGraph is not installed.

Available tools:
  get_case                  — Full details for an open investigation case
  get_customer_history      — Transaction + case history for a customer
  find_connected_entities   — Entities connected via shared device/email/region (1-hop MockClient; 2-hop TigerGraph)
  find_prior_cases          — Historical closed cases for customer/card
  detect_temporal_patterns  — Burst activity and card-testing detection
  calculate_exposure        — Fraud exposure totals for customer/card
  find_shared_devices       — Customers sharing devices
  get_transaction_context   — Full context for a single transaction

Usage:
    python mcp/server/server.py
    # or with custom port:
    $env:MCP_PORT=9000; python mcp/server/server.py
"""

import json
import logging
import os
import sys
import traceback
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from typing import Any

# ── Path setup ────────────────────────────────────────────────────────────────

# Ensure project root is on sys.path so imports resolve correctly
_ROOT = Path(__file__).parent.parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

# ── Logging ───────────────────────────────────────────────────────────────────

LOG_LEVEL = os.environ.get("LOG_LEVEL", "INFO").upper()
logging.basicConfig(
    level=getattr(logging, LOG_LEVEL, logging.INFO),
    format="%(asctime)s  %(levelname)-8s  %(name)s  %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger("mcp.server")

# ── Client selection ──────────────────────────────────────────────────────────

def _build_client() -> Any:
    """
    Try to build a TigerGraphClient. Fall back to MockClient on any failure.
    Returns a client object with the same public interface.
    """
    from mcp.server.mock_client import MockClient  # always importable

    try:
        from mcp.server.tigergraph_client import TigerGraphClient
        client = TigerGraphClient()
        if client.connect():
            log.info("Using TigerGraphClient (live connection)")
            return client
        else:
            log.warning("TigerGraph connection failed — falling back to MockClient")
            return MockClient()
    except ImportError:
        log.warning("pyTigerGraph not installed — using MockClient")
        return MockClient()
    except Exception as exc:
        log.warning(f"TigerGraph setup error ({exc}) — using MockClient")
        return MockClient()


# ── Tool registry ─────────────────────────────────────────────────────────────

TOOL_SCHEMAS: dict[str, dict[str, Any]] = {
    "get_case": {
        "description": "Return full details for an open investigation case including the flagged transaction.",
        "params": {
            "case_id": {"type": "string", "required": True, "description": "Case ID, e.g. HHG-001"},
        },
    },
    "get_customer_history": {
        "description": "Return recent transactions and closed case history for a customer.",
        "params": {
            "customer_id": {"type": "string", "required": True, "description": "Customer ID, e.g. C12382"},
            "limit": {"type": "integer", "required": False, "default": 20, "description": "Max transactions to return"},
        },
    },
    "find_connected_entities": {
        "description": "Find entities connected to a customer or card via shared attributes (device, email domain, region). MockClient: 1-hop shared-attribute matching. TigerGraph: 2-hop graph traversal via Transaction→attribute→Transaction.",
        "params": {
            "entity_id": {"type": "string", "required": True, "description": "Customer or card ID"},
            "entity_type": {"type": "string", "required": False, "default": "customer", "description": "customer or card"},
        },
    },
    "find_prior_cases": {
        "description": "Find prior closed cases for a customer or card from the historical case database.",
        "params": {
            "customer_id": {"type": "string", "required": False, "description": "Customer ID"},
            "card_id": {"type": "string", "required": False, "description": "Card ID, e.g. C12382-K1"},
        },
    },
    "detect_temporal_patterns": {
        "description": "Detect burst activity and card-testing patterns for a customer.",
        "params": {
            "customer_id": {"type": "string", "required": True, "description": "Customer ID"},
            "window_hours": {"type": "integer", "required": False, "default": 24, "description": "Time window in hours for burst detection"},
        },
    },
    "calculate_exposure": {
        "description": "Calculate total confirmed and pending fraud exposure for a customer or card.",
        "params": {
            "customer_id": {"type": "string", "required": False, "description": "Customer ID"},
            "card_id": {"type": "string", "required": False, "description": "Card ID"},
        },
    },
    "find_shared_devices": {
        "description": "Find other customers who share devices with the given customer.",
        "params": {
            "customer_id": {"type": "string", "required": True, "description": "Customer ID"},
        },
    },
    "get_transaction_context": {
        "description": "Return full context for a single transaction including identity, device, and customer history.",
        "params": {
            "txn_id": {"type": "string", "required": True, "description": "Transaction ID"},
        },
    },
}


def _dispatch(client: Any, tool: str, params: dict[str, Any]) -> dict[str, Any]:
    """Route a tool call to the appropriate client method."""
    if tool == "get_case":
        return client.get_case(case_id=params["case_id"])

    elif tool == "get_customer_history":
        return client.get_customer_history(
            customer_id=params["customer_id"],
            limit=int(params.get("limit", 20)),
        )

    elif tool == "find_connected_entities":
        return client.find_connected_entities(
            entity_id=params["entity_id"],
            entity_type=str(params.get("entity_type", "customer")),
        )

    elif tool == "find_prior_cases":
        return client.find_prior_cases(
            customer_id=params.get("customer_id"),
            card_id=params.get("card_id"),
        )

    elif tool == "detect_temporal_patterns":
        return client.detect_temporal_patterns(
            customer_id=params["customer_id"],
            window_hours=int(params.get("window_hours", 24)),
        )

    elif tool == "calculate_exposure":
        return client.calculate_exposure(
            customer_id=params.get("customer_id"),
            card_id=params.get("card_id"),
        )

    elif tool == "find_shared_devices":
        return client.find_shared_devices(customer_id=params["customer_id"])

    elif tool == "get_transaction_context":
        return client.get_transaction_context(txn_id=params["txn_id"])

    else:
        raise ValueError(f"Unknown tool: {tool!r}")


# ── HTTP handler ──────────────────────────────────────────────────────────────

class MCPHandler(BaseHTTPRequestHandler):
    """
    HTTP handler for the MCP server.

    Routes:
      POST /tool        — Execute a tool call
      GET  /tools       — List available tools and their schemas
      GET  /health      — Health check
    """

    client: Any  # set on the class by the server factory

    def log_message(self, format: str, *args: Any) -> None:  # noqa: A002
        log.info(f"{self.address_string()} — {format % args}")

    def _send_json(self, status: int, data: Any) -> None:
        body = json.dumps(data, indent=2).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _read_body(self) -> bytes:
        length = int(self.headers.get("Content-Length", 0))
        return self.rfile.read(length) if length > 0 else b""

    def do_GET(self) -> None:  # noqa: N802
        if self.path == "/health":
            self._send_json(200, {
                "status": "ok",
                "client": type(self.client).__name__,
                "tools": list(TOOL_SCHEMAS.keys()),
            })
        elif self.path == "/tools":
            self._send_json(200, {"tools": TOOL_SCHEMAS})
        else:
            self._send_json(404, {"error": f"Unknown path: {self.path}"})

    def do_POST(self) -> None:  # noqa: N802
        if self.path != "/tool":
            self._send_json(404, {"error": f"Unknown path: {self.path}. Use POST /tool"})
            return

        raw = self._read_body()
        if not raw:
            self._send_json(400, {"error": "Empty request body"})
            return

        try:
            payload = json.loads(raw.decode("utf-8"))
        except json.JSONDecodeError as exc:
            self._send_json(400, {"error": f"Invalid JSON: {exc}"})
            return

        tool = payload.get("tool", "").strip()
        params = payload.get("params", {})

        if not tool:
            self._send_json(400, {"error": "Missing required field: tool"})
            return

        if tool not in TOOL_SCHEMAS:
            self._send_json(400, {
                "error": f"Unknown tool: {tool!r}",
                "available_tools": list(TOOL_SCHEMAS.keys()),
            })
            return

        # Validate required params
        schema = TOOL_SCHEMAS[tool]
        missing = [
            k for k, v in schema["params"].items()
            if v.get("required") and k not in params
        ]
        if missing:
            self._send_json(400, {
                "error": f"Missing required parameters: {missing}",
                "tool": tool,
                "schema": schema,
            })
            return

        try:
            result = _dispatch(self.client, tool, params)
            self._send_json(200, {"tool": tool, "params": params, "result": result})
        except Exception as exc:
            log.error(f"Tool {tool!r} raised: {exc}\n{traceback.format_exc()}")
            self._send_json(500, {
                "error": f"Tool execution failed: {exc}",
                "tool": tool,
            })


def _make_handler(client: Any) -> type:
    """Create an MCPHandler subclass with the client bound."""
    return type("BoundMCPHandler", (MCPHandler,), {"client": client})


# ── Server entrypoint ─────────────────────────────────────────────────────────

def run_server(host: str = "localhost", port: int | None = None) -> None:
    port = port or int(os.environ.get("MCP_PORT", 8765))
    client = _build_client()
    handler_cls = _make_handler(client)

    server = HTTPServer((host, port), handler_cls)
    log.info("=" * 60)
    log.info("FraudGraph MCP Server")
    log.info(f"  Listening on: http://{host}:{port}")
    log.info(f"  Client:       {type(client).__name__}")
    log.info(f"  Tools:        {', '.join(TOOL_SCHEMAS.keys())}")
    log.info("")
    log.info("  POST /tool    — execute a tool")
    log.info("  GET  /tools   — list tool schemas")
    log.info("  GET  /health  — health check")
    log.info("=" * 60)

    try:
        server.serve_forever()
    except KeyboardInterrupt:
        log.info("Server stopped by user")
    finally:
        server.server_close()


if __name__ == "__main__":
    run_server()
