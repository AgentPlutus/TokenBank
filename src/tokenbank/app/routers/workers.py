"""Worker-facing endpoint skeletons."""

from __future__ import annotations

import sqlite3
from typing import Annotated, Any

from fastapi import APIRouter, Depends

from tokenbank.app.bootstrap import (
    rebuild_capacity_projection_from_config_and_db,
    upsert_worker_manifest,
)
from tokenbank.app.deps import get_db, get_loaded_config, require_worker_token
from tokenbank.config_runtime.loader import LoadedConfig
from tokenbank.scheduler.scheduler import Scheduler

router = APIRouter(tags=["workers"], dependencies=[Depends(require_worker_token)])


@router.post("/v0/workers/register")
def register_worker(
    payload: dict[str, Any],
    db: Annotated[sqlite3.Connection, Depends(get_db)],
    config: Annotated[LoadedConfig, Depends(get_loaded_config)],
) -> dict[str, Any]:
    manifest = upsert_worker_manifest(db, payload)
    capacity_count = rebuild_capacity_projection_from_config_and_db(db, config)
    return {
        "status": "ok",
        "worker_id": manifest.worker_id,
        "manifest_hash": manifest.manifest_hash,
        "capacity_node_id": f"capnode:worker:{manifest.worker_id}",
        "capacity_node_count": capacity_count,
    }


@router.post("/v0/workers/{worker_id}/heartbeat")
def worker_heartbeat(
    worker_id: str,
    db: Annotated[sqlite3.Connection, Depends(get_db)],
) -> dict[str, str]:
    Scheduler(db).record_worker_heartbeat(worker_id)
    return {"status": "ok", "worker_id": worker_id}


@router.get("/v0/workers/{worker_id}/assignments/next")
def next_assignment(
    worker_id: str,
    db: Annotated[sqlite3.Connection, Depends(get_db)],
) -> dict:
    assignment = Scheduler(db).poll_next_assignment(worker_id)
    return {"status": "ok", "assignment": assignment}
