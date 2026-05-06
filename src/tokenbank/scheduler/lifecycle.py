"""WorkUnit aggregate lifecycle ownership helpers."""

from __future__ import annotations

import sqlite3

from tokenbank.events.outbox import OutboxEventInput, enqueue_event
from tokenbank.scheduler.lease import utc_text

WORK_UNIT_STATUS_WRITERS = frozenset({"scheduler", "verifier_consumer"})


def update_work_unit_status(
    conn: sqlite3.Connection,
    *,
    work_unit_id: str,
    status: str,
    actor: str = "scheduler",
    event_type: str | None = None,
) -> None:
    if actor not in WORK_UNIT_STATUS_WRITERS:
        raise PermissionError("worker/backend/host cannot update WorkUnit directly")
    row = conn.execute(
        "SELECT body_json FROM work_units WHERE work_unit_id = ?",
        (work_unit_id,),
    ).fetchone()
    if row is None:
        raise KeyError(f"work_unit not found: {work_unit_id}")
    conn.execute(
        """
        UPDATE work_units
        SET status = ?,
            updated_at = ?
        WHERE work_unit_id = ?
        """,
        (status, utc_text(), work_unit_id),
    )
    enqueue_event(
        conn,
        OutboxEventInput(
            source="tokenbank.scheduler.lifecycle",
            type=event_type or f"work_unit.{status}",
            subject=f"work_units/{work_unit_id}",
            work_unit_id=work_unit_id,
            body={"work_unit_id": work_unit_id, "status": status, "actor": actor},
        ),
    )


def verifier_mutate_assignment_forbidden() -> None:
    raise PermissionError("VerifierReport writer cannot mutate Assignment")


def scheduler_mutate_verifier_report_forbidden() -> None:
    raise PermissionError("Scheduler cannot mutate VerifierReport")
