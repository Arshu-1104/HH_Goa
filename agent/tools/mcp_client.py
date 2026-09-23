"""
agent/tools/mcp_client.py — HTTP client for the Part 1 MCP server.

This is the ONLY place in Part 2 that makes HTTP calls to the MCP server.
It does not modify the MCP server in any way — it only calls the existing
POST /tool endpoint exactly as documented.

For tests that bypass the HTTP server, MCPDirectClient wraps MockClient directly.
"""

from __future__ import annotations

import json
import logging
import os
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

log = logging.getLogger(__name__)

# Default MCP server address from environment
_MCP_HOST = os.environ.get("MCP_HOST", "localhost")
_MCP_PORT = int(os.environ.get("MCP_PORT", "8765"))
_MCP_TIMEOUT = int(os.environ.get("MCP_TIMEOUT", "30"))


class MCPCallError(Exception):
    """Raised when an MCP tool call fails (network, timeout, or tool error)."""

    def __init__(self, tool: str, message: str, status_code: int = 0) -> None:
        self.tool = tool
        self.status_code = status_code
        super().__init__(f"MCP tool '{tool}' failed (HTTP {status_code}): {message}")


class MCPClient:
    """
    HTTP client for the Part 1 MCP server.

    Calls POST http://{host}:{port}/tool with body:
        {"tool": "<name>", "params": {...}}

    Returns the parsed JSON result dict from the "result" field.
    Raises MCPCallError on any failure.
    """

    def __init__(
        self,
        host: str | None = None,
        port: int | None = None,
        timeout: int | None = None,
    ) -> None:
        self._host = host or _MCP_HOST
        self._port = port or _MCP_PORT
        self._timeout = timeout or _MCP_TIMEOUT
        self._base_url = f"http://{self._host}:{self._port}"

    def call(self, tool: str, params: dict[str, Any]) -> dict[str, Any]:
        """
        Call a single MCP tool and return its result.

        Parameters
        ----------
        tool : str
            The tool name, e.g. "get_case"
        params : dict
            Parameters to pass to the tool

        Returns
        -------
        dict
            The "result" field from the MCP server response

        Raises
        ------
        MCPCallError
            On any failure: network, timeout, validation, or tool error
        """
        t0 = time.monotonic()
        url = f"{self._base_url}/tool"
        body = json.dumps({"tool": tool, "params": params}).encode("utf-8")

        req = urllib.request.Request(
            url, data=body, method="POST"
        )
        req.add_header("Content-Type", "application/json")
        req.add_header("Content-Length", str(len(body)))

        log.debug(f"MCP call: {tool} params={params}")

        try:
            with urllib.request.urlopen(req, timeout=self._timeout) as resp:
                raw = resp.read()
                data = json.loads(raw)
                latency_ms = (time.monotonic() - t0) * 1000
                log.info(f"MCP {tool} → OK ({latency_ms:.0f}ms)")
                return data.get("result", {})

        except urllib.error.HTTPError as e:
            latency_ms = (time.monotonic() - t0) * 1000
            try:
                error_body = json.loads(e.read())
                msg = error_body.get("error", str(e))
            except Exception:
                msg = str(e)
            log.error(f"MCP {tool} → HTTP {e.code}: {msg} ({latency_ms:.0f}ms)")
            raise MCPCallError(tool, msg, e.code) from e

        except urllib.error.URLError as e:
            latency_ms = (time.monotonic() - t0) * 1000
            log.error(f"MCP {tool} → URL error: {e.reason} ({latency_ms:.0f}ms)")
            raise MCPCallError(tool, f"URL error: {e.reason}") from e

        except TimeoutError as e:
            log.error(f"MCP {tool} → timeout after {self._timeout}s")
            raise MCPCallError(tool, f"Timeout after {self._timeout}s") from e

        except json.JSONDecodeError as e:
            log.error(f"MCP {tool} → malformed JSON response: {e}")
            raise MCPCallError(tool, f"Malformed JSON: {e}") from e

    def health_check(self) -> bool:
        """Return True if MCP server is reachable."""
        try:
            url = f"{self._base_url}/health"
            req = urllib.request.Request(url, method="GET")
            with urllib.request.urlopen(req, timeout=5) as resp:
                data = json.loads(resp.read())
                return data.get("status") == "ok"
        except Exception:
            return False

    # ── Convenience wrappers (exact param names from server.py) ──────────

    def get_case(self, case_id: str) -> dict[str, Any]:
        return self.call("get_case", {"case_id": case_id})

    def get_customer_history(
        self, customer_id: str, limit: int = 20
    ) -> dict[str, Any]:
        return self.call("get_customer_history", {
            "customer_id": customer_id, "limit": limit
        })

    def find_connected_entities(
        self, entity_id: str, entity_type: str = "customer"
    ) -> dict[str, Any]:
        return self.call("find_connected_entities", {
            "entity_id": entity_id, "entity_type": entity_type
        })

    def find_prior_cases(
        self,
        customer_id: str | None = None,
        card_id: str | None = None,
    ) -> dict[str, Any]:
        params: dict[str, Any] = {}
        if customer_id:
            params["customer_id"] = customer_id
        if card_id:
            params["card_id"] = card_id
        return self.call("find_prior_cases", params)

    def detect_temporal_patterns(
        self, customer_id: str, window_hours: int = 24
    ) -> dict[str, Any]:
        return self.call("detect_temporal_patterns", {
            "customer_id": customer_id, "window_hours": window_hours
        })

    def calculate_exposure(
        self,
        customer_id: str | None = None,
        card_id: str | None = None,
    ) -> dict[str, Any]:
        params: dict[str, Any] = {}
        if customer_id:
            params["customer_id"] = customer_id
        if card_id:
            params["card_id"] = card_id
        return self.call("calculate_exposure", params)

    def find_shared_devices(self, customer_id: str) -> dict[str, Any]:
        return self.call("find_shared_devices", {"customer_id": customer_id})

    def get_transaction_context(self, txn_id: str) -> dict[str, Any]:
        return self.call("get_transaction_context", {"txn_id": txn_id})


class MCPDirectClient:
    """
    Direct client that bypasses HTTP and calls MockClient methods directly.
    Used in tests and when MCP server is not running.

    Has the exact same interface as MCPClient.
    """

    def __init__(self, data_dir: Path | None = None) -> None:
        from mcp.server.mock_client import MockClient
        self._client = MockClient(data_dir=data_dir)
        log.info("MCPDirectClient: using MockClient (no HTTP server required)")

    def call(self, tool: str, params: dict[str, Any]) -> dict[str, Any]:
        """Dispatch to the appropriate MockClient method."""
        t0 = time.monotonic()
        try:
            if tool == "get_case":
                result = self._client.get_case(case_id=params["case_id"])
            elif tool == "get_customer_history":
                result = self._client.get_customer_history(
                    customer_id=params["customer_id"],
                    limit=int(params.get("limit", 20)),
                )
            elif tool == "find_connected_entities":
                result = self._client.find_connected_entities(
                    entity_id=params["entity_id"],
                    entity_type=params.get("entity_type", "customer"),
                )
            elif tool == "find_prior_cases":
                result = self._client.find_prior_cases(
                    customer_id=params.get("customer_id"),
                    card_id=params.get("card_id"),
                )
            elif tool == "detect_temporal_patterns":
                result = self._client.detect_temporal_patterns(
                    customer_id=params["customer_id"],
                    window_hours=int(params.get("window_hours", 24)),
                )
            elif tool == "calculate_exposure":
                result = self._client.calculate_exposure(
                    customer_id=params.get("customer_id"),
                    card_id=params.get("card_id"),
                )
            elif tool == "find_shared_devices":
                result = self._client.find_shared_devices(
                    customer_id=params["customer_id"]
                )
            elif tool == "get_transaction_context":
                result = self._client.get_transaction_context(
                    txn_id=params["txn_id"]
                )
            else:
                raise MCPCallError(tool, f"Unknown tool: {tool!r}")

            latency_ms = (time.monotonic() - t0) * 1000
            log.debug(f"MCPDirect {tool} → OK ({latency_ms:.0f}ms)")
            return result

        except MCPCallError:
            raise
        except Exception as exc:
            raise MCPCallError(tool, str(exc)) from exc

    def health_check(self) -> bool:
        return True

    # ── Same convenience wrappers ─────────────────────────────────────────

    def get_case(self, case_id: str) -> dict[str, Any]:
        return self.call("get_case", {"case_id": case_id})

    def get_customer_history(
        self, customer_id: str, limit: int = 20
    ) -> dict[str, Any]:
        return self.call("get_customer_history", {
            "customer_id": customer_id, "limit": limit
        })

    def find_connected_entities(
        self, entity_id: str, entity_type: str = "customer"
    ) -> dict[str, Any]:
        return self.call("find_connected_entities", {
            "entity_id": entity_id, "entity_type": entity_type
        })

    def find_prior_cases(
        self,
        customer_id: str | None = None,
        card_id: str | None = None,
    ) -> dict[str, Any]:
        params: dict[str, Any] = {}
        if customer_id:
            params["customer_id"] = customer_id
        if card_id:
            params["card_id"] = card_id
        return self.call("find_prior_cases", params)

    def detect_temporal_patterns(
        self, customer_id: str, window_hours: int = 24
    ) -> dict[str, Any]:
        return self.call("detect_temporal_patterns", {
            "customer_id": customer_id, "window_hours": window_hours
        })

    def calculate_exposure(
        self,
        customer_id: str | None = None,
        card_id: str | None = None,
    ) -> dict[str, Any]:
        params: dict[str, Any] = {}
        if customer_id:
            params["customer_id"] = customer_id
        if card_id:
            params["card_id"] = card_id
        return self.call("calculate_exposure", params)

    def find_shared_devices(self, customer_id: str) -> dict[str, Any]:
        return self.call("find_shared_devices", {"customer_id": customer_id})

    def get_transaction_context(self, txn_id: str) -> dict[str, Any]:
        return self.call("get_transaction_context", {"txn_id": txn_id})


def build_mcp_client(
    use_direct: bool = False,
    data_dir: Path | None = None,
) -> MCPClient | MCPDirectClient:
    """
    Build the appropriate MCP client.

    Parameters
    ----------
    use_direct : bool
        If True, use MCPDirectClient (bypasses HTTP, uses MockClient).
        If False, try MCPClient (HTTP); fall back to MCPDirectClient on failure.
    data_dir : Path | None
        Data directory for MCPDirectClient.
    """
    if use_direct:
        return MCPDirectClient(data_dir=data_dir)

    client = MCPClient()
    if client.health_check():
        log.info("MCPClient: MCP server is reachable, using HTTP client")
        return client

    log.warning(
        f"MCP server not reachable at {client._base_url} — "
        "falling back to MCPDirectClient"
    )
    return MCPDirectClient(data_dir=data_dir)
