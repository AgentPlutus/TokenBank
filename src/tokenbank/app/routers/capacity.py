"""Capacity discovery endpoints."""

from __future__ import annotations

import json
import sqlite3
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status

from tokenbank.app.bootstrap import rebuild_capacity_projection_from_config_and_db
from tokenbank.app.deps import (
    get_db,
    get_loaded_config,
    require_host_token,
    require_internal_token,
)
from tokenbank.capacity.discovery import discover_capacity_nodes
from tokenbank.config_runtime.loader import LoadedConfig

router = APIRouter(tags=["capacity"])


@router.get(
    "/v0/capacity/nodes",
    dependencies=[Depends(require_host_token)],
)
def list_capacity_nodes(db: Annotated[sqlite3.Connection, Depends(get_db)]) -> dict:
    nodes = discover_capacity_nodes(db)
    return {"status": "ok", "nodes": nodes}


@router.get(
    "/v0/capacity/health",
    dependencies=[Depends(require_host_token)],
)
def capacity_health(db: Annotated[sqlite3.Connection, Depends(get_db)]) -> dict:
    rows = db.execute(
        """
        SELECT status, COUNT(*) AS count
        FROM capacity_nodes
        GROUP BY status
        ORDER BY status
        """
    ).fetchall()
    return {
        "status": "ok",
        "counts": {row["status"]: row["count"] for row in rows},
    }


@router.get(
    "/v0/capacity/nodes/{capacity_node_id}",
    dependencies=[Depends(require_host_token)],
)
def inspect_capacity_node(
    capacity_node_id: str,
    db: Annotated[sqlite3.Connection, Depends(get_db)],
) -> dict:
    row = db.execute(
        """
        SELECT body_json
        FROM capacity_nodes
        WHERE capacity_node_id = ?
        """,
        (capacity_node_id,),
    ).fetchone()
    if row is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"error": "capacity_node_not_found"},
        )
    return {"status": "ok", "node": json.loads(row["body_json"])}


@router.post(
    "/internal/capacity/rebuild-registry",
    dependencies=[Depends(require_internal_token)],
)
def rebuild_capacity_registry(
    db: Annotated[sqlite3.Connection, Depends(get_db)],
    config: Annotated[LoadedConfig, Depends(get_loaded_config)],
) -> dict[str, int | str]:
    count = rebuild_capacity_projection_from_config_and_db(db, config)
    return {"status": "ok", "capacity_node_count": count}
