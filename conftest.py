"""
conftest.py — Root pytest configuration.

CRITICAL FIX 1 — mcp package conflict:
  The system has `mcp==1.26.0` installed (the official Model Context Protocol
  SDK). This shadows the local `mcp/` directory in pytest runs because pytest
  doesn't automatically prepend the project root to sys.path when there is no
  package setup file.

  This conftest.py ensures the project root is FIRST on sys.path so that
  `from mcp.server.mock_client import MockClient` resolves to the local
  mcp/server/mock_client.py, not the installed SDK.

CRITICAL FIX 2 — langgraph import broken:
  langgraph 1.2.6 + langgraph_sdk 0.4.2 requires
  langchain_core.language_models.chat_model_stream which does not exist in
  langchain_core 0.3.86. A local shim at langgraph/graph/message.py provides
  the add_messages function that agent/state/state.py needs, without triggering
  the broken import chain.

SKIP GUARD — transactions.csv missing:
  Several tests require transactions.csv at the project root. When the file is
  absent the tests would fail with misleading assertion errors. This conftest
  exposes a pytest fixture `require_transactions_csv` that skips cleanly.
"""

import sys
import pytest
from pathlib import Path

# ── 1. Fix sys.path so local mcp/ wins over installed mcp package ─────────────
ROOT = Path(__file__).parent
root_str = str(ROOT)
if root_str not in sys.path:
    sys.path.insert(0, root_str)

# Remove the site-packages mcp from sys.modules if it was already loaded.
if "mcp" in sys.modules:
    mcp_mod = sys.modules["mcp"]
    mcp_file = getattr(mcp_mod, "__file__", "") or ""
    if "site-packages" in mcp_file:
        to_remove = [k for k in sys.modules if k == "mcp" or k.startswith("mcp.")]
        for k in to_remove:
            del sys.modules[k]


# ── 2. Shared skip marker for tests that require transactions.csv ──────────────
TRANSACTIONS_CSV = ROOT / "transactions.csv"
_TRANSACTIONS_MISSING = not TRANSACTIONS_CSV.exists()

skip_if_no_transactions = pytest.mark.skipif(
    _TRANSACTIONS_MISSING,
    reason=(
        "transactions.csv not found at project root. "
        "Place the 590k-row dataset file at "
        f"{TRANSACTIONS_CSV} to run these tests."
    ),
)

