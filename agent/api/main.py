"""
agent/api/main.py — Part 3 FastAPI application entrypoint.

Mounts the existing Part 2 API (routes.py — unchanged) alongside the
new Part 3 routes (part3_routes.py) and the static UI.

Usage:
    uvicorn agent.api.main:app --host 0.0.0.0 --port 8000 --reload

The existing Part 2 API is imported AS-IS from agent.api.routes.
Nothing in routes.py or schemas.py is modified.
"""

from __future__ import annotations

import logging
import os
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, HTMLResponse
from fastapi.staticfiles import StaticFiles

# ── Project path fix (same as conftest.py) ───────────────────────────────────
import sys
ROOT = Path(__file__).parent.parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

# ── Import Part 2 app (unchanged) ─────────────────────────────────────────────
# We import the existing Part 2 app directly and mount Part 3 routes on top.
# The Part 2 app itself is never modified.
from agent.api.routes import app as _part2_app  # noqa: E402

# ── Import Part 3 router ──────────────────────────────────────────────────────
from agent.api.part3_routes import router as _part3_router  # noqa: E402

# ── Create the combined application ──────────────────────────────────────────
# We re-use the Part 2 FastAPI instance directly and attach Part 3 routes.
# This preserves all Part 2 routes, their schemas, and their behaviour.
app = _part2_app

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# Mount Part 3 API routes
app.include_router(_part3_router)

# Mount static UI files
UI_DIR = ROOT / "ui"
if UI_DIR.exists():
    app.mount("/static", StaticFiles(directory=str(UI_DIR / "static")), name="static")


@app.get("/ui", response_class=HTMLResponse, include_in_schema=False,
         response_model=None)
@app.get("/ui/", response_class=HTMLResponse, include_in_schema=False,
         response_model=None)
def serve_ui():
    """Serve the investigation dashboard."""
    index_path = UI_DIR / "index.html"
    if not index_path.exists():
        return HTMLResponse(
            content="<h1>UI not found</h1><p>UI files are missing from ui/</p>",
            status_code=404,
        )
    return FileResponse(str(index_path))


@app.get("/", include_in_schema=False, response_model=None)
def root_redirect():
    """Redirect root to the UI."""
    from fastapi.responses import RedirectResponse
    return RedirectResponse(url="/ui")


log = logging.getLogger(__name__)
log.info("FraudGraph Investigator — Part 3 app loaded")
log.info(f"  Part 2 routes: /health, /cases, /investigate/{{case_id}}, /investigate/batch")
log.info(f"  Part 3 routes: /api/v3/report/{{case_id}}, /api/v3/benchmark, /api/v3/cases/meta, /api/v3/run/{{case_id}}")
log.info(f"  UI:            /ui")
