"""Internal router endpoint skeleton."""

from __future__ import annotations

import sqlite3
from typing import Annotated, Any

from fastapi import APIRouter, Body, Depends, HTTPException, status

from tokenbank.app.deps import get_db, get_loaded_config, require_internal_token
from tokenbank.config_runtime.loader import LoadedConfig
from tokenbank.router.service import RouterService
from tokenbank.scheduler.sweeper import sweep_expired_leases

router = APIRouter(tags=["internal"], dependencies=[Depends(require_internal_token)])
OPTIONAL_ROUTER_PLAN_PAYLOAD = Body(default=None)


@router.post("/internal/router/plan")
def router_plan(
    db: Annotated[sqlite3.Connection, Depends(get_db)],
    config: Annotated[LoadedConfig, Depends(get_loaded_config)],
    payload: dict[str, Any] | None = OPTIONAL_ROUTER_PLAN_PAYLOAD,
) -> dict[str, Any]:
    if payload is None:
        return {
            "status": "ok",
            "route_plan": None,
            "message": "work_unit payload required",
        }
    routebook_dir = config.root.parent / "routebook"
    try:
        route_plan = RouterService.from_dirs(
            config_dir=config.root,
            routebook_dir=routebook_dir,
        ).plan_route(payload["work_unit"], persist_conn=db)
    except (KeyError, ValueError) as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"error": str(exc)},
        ) from exc
    return {
        "status": "ok",
        "route_plan": route_plan.model_dump(mode="json"),
    }


@router.post("/internal/scheduler/tick")
def scheduler_tick(
    db: Annotated[sqlite3.Connection, Depends(get_db)],
) -> dict[str, int | str]:
    expired = sweep_expired_leases(db)
    return {"status": "ok", "expired_assignments": expired}
