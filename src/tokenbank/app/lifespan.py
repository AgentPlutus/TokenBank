"""FastAPI lifespan for config validation and DB bootstrap."""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI

from tokenbank.app.bootstrap import rebuild_capacity_projection_from_config_and_db
from tokenbank.config_runtime.loader import load_config_dir
from tokenbank.config_runtime.validator import validate_loaded_config
from tokenbank.db.bootstrap import initialize_database


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    config_dir = Path(getattr(app.state, "config_dir", "config"))
    db_path = Path(getattr(app.state, "db_path", ".tokenbank/tokenbank.db"))
    loaded_config = load_config_dir(config_dir)
    validation = validate_loaded_config(loaded_config)
    if not validation.ok:
        messages = "; ".join(
            f"{issue.code}: {issue.message}" for issue in validation.issues
        )
        raise RuntimeError(f"TokenBank config validation failed: {messages}")

    app.state.loaded_config = loaded_config
    app.state.config_validation = validation
    app.state.db = initialize_database(db_path)
    app.state.capacity_node_count = rebuild_capacity_projection_from_config_and_db(
        app.state.db,
        loaded_config,
    )
    try:
        yield
    finally:
        app.state.db.close()
