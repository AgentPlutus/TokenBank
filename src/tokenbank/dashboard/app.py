"""Local dashboard FastAPI app."""

from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import HTMLResponse

from tokenbank import PHASE_0_NAME, PRODUCT_NAME
from tokenbank.app.lifespan import lifespan
from tokenbank.dashboard.views import (
    dashboard_export,
    dashboard_snapshot,
    render_dashboard_html,
)


def create_dashboard_app(
    *,
    config_dir: str | Path = "config",
    db_path: str | Path = ".tokenbank/tokenbank.db",
) -> FastAPI:
    """Create a localhost-oriented read-only dashboard app."""
    app = FastAPI(
        title=f"{PRODUCT_NAME} Local Dashboard",
        description=f"{PRODUCT_NAME} Phase 0 {PHASE_0_NAME} local dashboard.",
        version="0.1.0",
        lifespan=lifespan,
        docs_url=None,
        redoc_url=None,
        openapi_url=None,
    )
    app.state.config_dir = Path(config_dir)
    app.state.db_path = Path(db_path)

    @app.get("/", response_class=HTMLResponse)
    def index() -> HTMLResponse:
        snapshot = dashboard_snapshot(app.state.db)
        return HTMLResponse(render_dashboard_html(snapshot))

    @app.get("/summary.json")
    def summary() -> dict:
        return dashboard_snapshot(app.state.db)

    @app.get("/export.json")
    def export() -> dict:
        return dashboard_export(app.state.db)

    return app
