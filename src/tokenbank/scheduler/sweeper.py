"""Lease sweeper."""

from __future__ import annotations

import sqlite3

from tokenbank.events.outbox import OutboxEventInput, enqueue_event
from tokenbank.scheduler.lease import utc_text


def sweep_expired_leases(conn: sqlite3.Connection) -> int:
    rows = conn.execute(
        """
        SELECT assignment_id, attempt_id, work_unit_id
        FROM assignments
        WHERE status IN ('accepted', 'running')
          AND lease_expires_at IS NOT NULL
          AND lease_expires_at < ?
        """,
        (utc_text(),),
    ).fetchall()
    for row in rows:
        conn.execute(
            """
            UPDATE assignments
            SET status = 'expired',
                updated_at = ?
            WHERE assignment_id = ?
            """,
            (utc_text(), row["assignment_id"]),
        )
        enqueue_event(
            conn,
            OutboxEventInput(
                source="tokenbank.scheduler.sweeper",
                type="assignment.expired",
                subject=f"assignments/{row['assignment_id']}",
                work_unit_id=row["work_unit_id"],
                attempt_id=row["attempt_id"],
                assignment_id=row["assignment_id"],
                body={"assignment_id": row["assignment_id"], "status": "expired"},
            ),
        )
    conn.commit()
    return len(rows)

