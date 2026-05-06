"""Retry and fallback scheduling helpers."""

from __future__ import annotations

import sqlite3


def next_attempt_number(conn: sqlite3.Connection, work_unit_id: str) -> int:
    row = conn.execute(
        """
        SELECT COALESCE(MAX(attempt_number), 0) + 1
        FROM execution_attempts
        WHERE work_unit_id = ?
        """,
        (work_unit_id,),
    ).fetchone()
    return int(row[0])

