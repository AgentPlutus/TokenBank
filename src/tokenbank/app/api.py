"""FastAPI application factory."""

from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI

from tokenbank import PHASE_0_NAME, PRODUCT_NAME
from tokenbank.app.lifespan import lifespan
from tokenbank.app.routers import (
    assignments,
    capacity,
    dashboard,
    host,
    internal_policy,
    internal_router,
    internal_verifier,
    workers,
)


def create_app(
    *,
    config_dir: str | Path = "config",
    db_path: str | Path = ".tokenbank/tokenbank.db",
) -> FastAPI:
    app = FastAPI(
        title=f"{PRODUCT_NAME} Control Plane",
        description=f"{PRODUCT_NAME} Phase 0 {PHASE_0_NAME} control plane.",
        version="0.1.0",
        lifespan=lifespan,
        docs_url=None,
        redoc_url=None,
        openapi_url=None,
    )
    app.state.config_dir = Path(config_dir)
    app.state.db_path = Path(db_path)

    @app.get("/health", tags=["health"])
    def health() -> dict[str, str]:
        return {
            "status": "ok",
            "product": PRODUCT_NAME,
            "phase": PHASE_0_NAME,
        }

    app.include_router(host.router)
    app.include_router(capacity.router)
    app.include_router(dashboard.router)
    app.include_router(workers.router)
    app.include_router(assignments.router)
    app.include_router(internal_router.router)
    app.include_router(internal_policy.router)
    app.include_router(internal_verifier.router)
    return app


app = create_app()
