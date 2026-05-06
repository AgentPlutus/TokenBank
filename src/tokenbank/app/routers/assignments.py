"""Assignment endpoint skeletons."""

from __future__ import annotations

import sqlite3
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, status

from tokenbank.app.deps import get_db, require_worker_token
from tokenbank.host.url_check import finalize_url_check_result
from tokenbank.scheduler.lease import LeaseConflictError
from tokenbank.scheduler.scheduler import Scheduler

router = APIRouter(tags=["assignments"], dependencies=[Depends(require_worker_token)])


@router.post("/v0/assignments/{assignment_id}/accept")
def accept_assignment(
    assignment_id: str,
    payload: dict[str, Any],
    db: Annotated[sqlite3.Connection, Depends(get_db)],
) -> dict[str, Any]:
    try:
        return Scheduler(db).accept_assignment(
            assignment_id=assignment_id,
            worker_id=payload["worker_id"],
            expected_lease_version=int(payload.get("expected_lease_version", 0)),
        )
    except (KeyError, PermissionError, LeaseConflictError) as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={"error": str(exc)},
        ) from exc


@router.post("/v0/assignments/{assignment_id}/reject")
def reject_assignment(
    assignment_id: str,
    payload: dict[str, Any],
    db: Annotated[sqlite3.Connection, Depends(get_db)],
) -> dict[str, Any]:
    try:
        return Scheduler(db).reject_assignment(
            assignment_id=assignment_id,
            worker_id=payload["worker_id"],
        )
    except (KeyError, PermissionError) as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={"error": str(exc)},
        ) from exc


@router.post("/v0/assignments/{assignment_id}/progress")
def assignment_progress(
    assignment_id: str,
    payload: dict[str, Any],
    db: Annotated[sqlite3.Connection, Depends(get_db)],
) -> dict[str, Any]:
    try:
        return Scheduler(db).progress_assignment(
            assignment_id=assignment_id,
            worker_id=payload["worker_id"],
            lease_token=payload["lease_token"],
            expected_lease_version=int(payload["expected_lease_version"]),
        )
    except (KeyError, PermissionError, LeaseConflictError) as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={"error": str(exc)},
        ) from exc


@router.post("/v0/assignments/{assignment_id}/result")
def assignment_result(
    assignment_id: str,
    payload: dict[str, Any],
    db: Annotated[sqlite3.Connection, Depends(get_db)],
) -> dict[str, Any]:
    try:
        result = Scheduler(db).submit_result(
            assignment_id=assignment_id,
            worker_id=payload["worker_id"],
            lease_token=payload.get("lease_token"),
            lease_token_hash_value=payload.get("lease_token_hash"),
            output=payload.get("output", {}),
            result_envelope=payload.get("result_envelope"),
        )
        finalized = finalize_url_check_result(
            db,
            result_envelope_id=result["result_envelope_id"],
        )
        if finalized is not None:
            result["verifier_report"] = finalized["verifier_report"]
            result["host_result_summary"] = finalized["host_result_summary"]
        return result
    except (KeyError, PermissionError, ValueError) as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={"error": str(exc)},
        ) from exc
