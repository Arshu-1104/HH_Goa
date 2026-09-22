"""
tigergraph_client.py — TigerGraph client wrapper for FraudGraph.

Uses pyTigerGraph if available.
Wraps all GSQL query calls and returns structured dicts.
Raises ImportError with helpful message if pyTigerGraph is not installed.
"""

import os
import logging
from typing import Any

log = logging.getLogger(__name__)


class TigerGraphClient:
    """
    Wraps pyTigerGraph connection and query execution.
    Returns structured dicts — never raw TigerGraph objects.
    """

    def __init__(
        self,
        host: str | None = None,
        username: str | None = None,
        password: str | None = None,
        graph_name: str | None = None,
        secret: str | None = None,
    ) -> None:
        try:
            import pyTigerGraph as tg  # type: ignore[import]
            self._tg = tg
        except ImportError:
            raise ImportError(
                "pyTigerGraph is not installed. "
                "Install it with: pip install pyTigerGraph\n"
                "Or use MockClient for local development without TigerGraph."
            )

        self._host = host or os.environ.get("TIGERGRAPH_HOST", "")
        self._username = username or os.environ.get("TIGERGRAPH_USERNAME", "tigergraph")
        self._password = password or os.environ.get("TIGERGRAPH_PASSWORD", "")
        self._graph_name = graph_name or os.environ.get("TIGERGRAPH_GRAPH_NAME", "FraudGraph")
        self._secret = secret or os.environ.get("TIGERGRAPH_SECRET", "")
        self._conn: Any | None = None
        self._connected = False

    def connect(self) -> bool:
        """Establish connection to TigerGraph and obtain an API token."""
        if self._connected and self._conn is not None:
            return True
        try:
            self._conn = self._tg.TigerGraphConnection(
                host=self._host,
                username=self._username,
                password=self._password,
                graphname=self._graph_name,
            )
            if self._secret:
                token = self._conn.getToken(self._secret)
                self._conn.apiToken = token[0] if isinstance(token, (list, tuple)) else token
            else:
                # Try to create a secret if none provided
                try:
                    self._secret = self._conn.createSecret()
                    token = self._conn.getToken(self._secret)
                    self._conn.apiToken = token[0] if isinstance(token, (list, tuple)) else token
                except Exception:
                    log.warning("Could not create TigerGraph secret — proceeding without token")

            self._connected = True
            log.info(f"Connected to TigerGraph at {self._host}, graph: {self._graph_name}")
            return True
        except Exception as exc:
            log.error(f"TigerGraph connection failed: {exc}")
            self._connected = False
            return False

    def is_connected(self) -> bool:
        """Check if TigerGraph connection is active."""
        if not self._connected or self._conn is None:
            return False
        try:
            # Lightweight ping: get vertex count for a small type
            self._conn.getVertexCount("FraudPattern")
            return True
        except Exception:
            self._connected = False
            return False

    def run_query(
        self,
        query_name: str,
        params: dict[str, Any] | None = None,
        timeout: int = 30_000,
    ) -> dict[str, Any]:
        """
        Run an installed GSQL query by name.

        Returns:
          {
            "success": bool,
            "query": str,
            "results": list[dict],
            "error": str | None,
          }
        """
        if not self._connected:
            success = self.connect()
            if not success:
                return {
                    "success": False,
                    "query": query_name,
                    "results": [],
                    "error": "Not connected to TigerGraph",
                }

        try:
            raw = self._conn.runInstalledQuery(
                query_name,
                params=params or {},
                timeout=timeout,
            )
            # pyTigerGraph returns a list of result dicts
            results = raw if isinstance(raw, list) else [raw]
            return {
                "success": True,
                "query": query_name,
                "results": results,
                "error": None,
            }
        except Exception as exc:
            log.error(f"Query {query_name!r} failed: {exc}")
            return {
                "success": False,
                "query": query_name,
                "results": [],
                "error": str(exc),
            }

    def get_vertex(
        self,
        vertex_type: str,
        vertex_id: str,
    ) -> dict[str, Any] | None:
        """Fetch a single vertex by type and ID."""
        if not self._connected:
            self.connect()
        try:
            result = self._conn.getVerticesById(vertex_type, vertex_id)
            if result:
                return result[0] if isinstance(result, list) else result
            return None
        except Exception as exc:
            log.error(f"getVertex({vertex_type}, {vertex_id}) failed: {exc}")
            return None

    def get_vertex_count(self, vertex_type: str = "*") -> int:
        """Get vertex count for a given type, or all types."""
        if not self._connected:
            self.connect()
        try:
            return int(self._conn.getVertexCount(vertex_type))
        except Exception:
            return -1

    def upsert_vertex(
        self,
        vertex_type: str,
        vertex_id: str,
        attributes: dict[str, Any],
    ) -> bool:
        """Upsert a vertex. Returns True on success."""
        if not self._connected:
            self.connect()
        try:
            self._conn.upsertVertex(vertex_type, vertex_id, attributes)
            return True
        except Exception as exc:
            log.error(f"upsertVertex({vertex_type}, {vertex_id}) failed: {exc}")
            return False

    def upsert_edge(
        self,
        src_type: str,
        src_id: str,
        edge_type: str,
        tgt_type: str,
        tgt_id: str,
        attributes: dict[str, Any] | None = None,
    ) -> bool:
        """Upsert an edge. Returns True on success."""
        if not self._connected:
            self.connect()
        try:
            self._conn.upsertEdge(
                src_type, src_id, edge_type, tgt_type, tgt_id, attributes or {}
            )
            return True
        except Exception as exc:
            log.error(f"upsertEdge({src_type}-{edge_type}-{tgt_type}) failed: {exc}")
            return False
