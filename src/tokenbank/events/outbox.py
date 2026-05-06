"""Event outbox repository helpers."""

from __future__ import annotations

import sqlite3
import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

from tokenbank.core.canonical import canonical_json_dumps
from tokenbank.core.redaction import redact_sensitive_value


def _utc_now_text() -> str:
    return datetime.now(UTC).isoformat().replace("+00:00", "Z")


@dataclass(frozen=True)
class OutboxEventInput:
    source: str
    type: str
    subject: str
    body: dict[str, Any]
    run_id: str | None = None
    work_unit_id: str | None = None
    attempt_id: str | None = None
    assignment_id: str | None = None
    trace_id: str = field(default_factory=lambda: uuid.uuid4().hex)
    span_id: str | None = None
    event_id: str = field(default_factory=lambda: f"evt_{uuid.uuid4().hex}")


def _next_sequence(conn: sqlite3.Connection) -> int:
    row = conn.execute(
        "SELECT COALESCE(MAX(sequence), 0) + 1 FROM event_outbox"
    ).fetchone()
    return int(row[0])


def enqueue_event(conn: sqlite3.Connection, event: OutboxEventInput) -> str:
    """Insert a pending event_outbox row."""
    conn.execute(
        """
        INSERT INTO event_outbox (
          event_id,
          source,
          type,
          subject,
          run_id,
          work_unit_id,
          attempt_id,
          assignment_id,
          trace_id,
          span_id,
          status,
          sequence,
          body_json,
          created_at
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'pending', ?, ?, ?)
        """,
        (
            event.event_id,
            event.source,
            event.type,
            event.subject,
            event.run_id,
            event.work_unit_id,
            event.attempt_id,
            event.assignment_id,
            event.trace_id,
            event.span_id,
            _next_sequence(conn),
            canonical_json_dumps(redact_sensitive_value(event.body)),
            _utc_now_text(),
        ),
    )
    return event.event_id


def pending_events(conn: sqlite3.Connection, limit: int = 100) -> list[sqlite3.Row]:
    return list(
        conn.execute(
            """
            SELECT *
            FROM event_outbox
            WHERE status = 'pending'
            ORDER BY sequence
            LIMIT ?
            """,
            (limit,),
        )
    )


def mark_written(conn: sqlite3.Connection, event_id: str) -> None:
    conn.execute(
        """
        UPDATE event_outbox
        SET status = 'written',
            written_at = ?,
            last_error = NULL
        WHERE event_id = ?
        """,
        (_utc_now_text(), event_id),
    )
    conn.commit()


def mark_failed(conn: sqlite3.Connection, event_id: str, error: str) -> None:
    conn.execute(
        """
        UPDATE event_outbox
        SET status = 'failed',
            failure_count = failure_count + 1,
            last_error = ?
        WHERE event_id = ?
        """,
        (error, event_id),
    )
    conn.commit()
