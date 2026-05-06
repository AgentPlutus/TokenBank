"""Flush pending event_outbox rows to JSONL."""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from pathlib import Path

from tokenbank.events.jsonl import append_event_jsonl
from tokenbank.events.outbox import mark_failed, mark_written, pending_events


@dataclass(frozen=True)
class FlushResult:
    written: int = 0
    failed: int = 0


def flush_pending_events(
    conn: sqlite3.Connection,
    jsonl_path: str | Path,
    limit: int = 100,
) -> FlushResult:
    """Flush pending outbox rows to JSONL, updating each row after write."""
    written = 0
    failed = 0

    for row in pending_events(conn, limit=limit):
        event_id = row["event_id"]
        try:
            append_event_jsonl(jsonl_path, row)
        except OSError as exc:
            mark_failed(conn, event_id, str(exc))
            failed += 1
            continue

        mark_written(conn, event_id)
        written += 1

    return FlushResult(written=written, failed=failed)

