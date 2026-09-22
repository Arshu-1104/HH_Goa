# FraudGraph MCP — Architecture & Integration Guide

## What is deployed

### Current: Local Tool Gateway (Development Fallback)

The current server (`mcp/server/server.py`) is a **custom HTTP tool gateway**, NOT the
official TigerGraph MCP server.  It exposes:

```
POST /tool          — Execute a named tool
GET  /tools         — List tool schemas
GET  /health        — Health check
```

This is useful for local development, testing, and the MockClient (CSV-based) data path.
It is **not** the mechanism required for a production TigerGraph MCP integration.

---

## TigerGraph MCP — Correct Integration

TigerGraph provides an official MCP server package:
**`pyTigerGraph-mcp`** (or the TigerGraph MCP connector depending on version).

### Option A — pyTigerGraph MCP (Recommended)

The official TigerGraph MCP integration uses the **Model Context Protocol** (JSON-RPC 2.0
over stdio or HTTP) and exposes TigerGraph GSQL queries as MCP tools.

```
pip install pyTigerGraph-mcp
```

Configuration (`.env` or environment variables):
```
TIGERGRAPH_HOST=https://your-instance.i.tgcloud.io
TIGERGRAPH_USERNAME=tigergraph
TIGERGRAPH_PASSWORD=your_password
TIGERGRAPH_GRAPH_NAME=FraudGraph
TIGERGRAPH_SECRET=your_secret     # or omit to auto-create
```

Once the schema is deployed and queries are installed, the MCP server exposes each
installed GSQL query as an MCP tool that Part 2 agents can call via standard MCP protocol.

### Option B — TigerGraph REST++ via MCP wrapper

If pyTigerGraph-mcp is not available for your TigerGraph version, a wrapper can proxy
TigerGraph REST++ calls (`GET /restpp/query/{graph}/{query}`) through the MCP protocol.

---

## Deployment sequence (live TigerGraph)

1. Deploy schema:
   ```
   gsql tigergraph/schema/schema.gsql
   ```

2. Deploy loading jobs:
   ```
   gsql -g FraudGraph tigergraph/loading/loading.gsql
   ```

3. Generate normalized + graph load files:
   ```
   python scripts/normalize_dataset.py
   python scripts/generate_graph_load_files.py
   ```

4. Run loading jobs (replace paths as needed):
   ```
   gsql -g FraudGraph "RUN LOADING JOB load_customers USING f1='data/graph_load/customers_vertex.csv'"
   # ... repeat for all vertex and edge loading jobs
   ```

5. Install GSQL queries:
   ```
   gsql -g FraudGraph "INSTALL QUERY ALL"
   ```

6. Start TigerGraph MCP server:
   ```
   python -m pyTigerGraph_mcp --host $TIGERGRAPH_HOST --graph FraudGraph
   ```

---

## Current Server — Development Fallback

Keep the current HTTP server running for:
- Testing without a live TigerGraph instance
- MockClient (CSV-based) development
- Integration tests that don't require GSQL

To start:
```
python mcp/server/server.py
# Listens on http://localhost:8765
```

The server automatically falls back to MockClient if TigerGraph is unavailable.

---

## Known limitations

| Item | Status |
|---|---|
| Live TigerGraph deployment | NOT VERIFIED — no live instance available |
| GSQL static validation | COMPLETE — all syntax issues fixed |
| GSQL live compilation | PENDING — requires live TigerGraph |
| pyTigerGraph-mcp integration | ARCHITECTURE DOCUMENTED — not yet wired |
| MockClient tool coverage | COMPLETE — all 8 tools functional |

The current local gateway must NOT be renamed "TigerGraph MCP" or presented as the
official MCP integration.  It is a development fallback only.
