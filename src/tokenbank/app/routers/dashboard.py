"""Authenticated dashboard JSON endpoints."""

from __future__ import annotations

import sqlite3
from typing import Annotated

from fastapi import APIRouter, Depends

from tokenbank.app.deps import get_db, require_host_token
from tokenbank.dashboard.views import dashboard_export, dashboard_snapshot

router = APIRouter(
    prefix="/v0/dashboard",
    tags=["dashboard"],
    dependencies=[Depends(require_host_token)],
)


@router.get("/summary")
def dashboard_summary(
    db: Annotated[sqlite3.Connection, Depends(get_db)],
    limit: int = 50,
) -> dict:
    """Return a redacted local dashboard snapshot."""
    return dashboard_snapshot(db, limit=limit)


@router.get("/export")
def dashboard_redacted_export(
    db: Annotated[sqlite3.Connection, Depends(get_db)],
    limit: int = 50,
) -> dict:
    """Return a user-controlled redacted dashboard export."""
    return dashboard_export(db, limit=limit)
