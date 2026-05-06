"""JSONL writer for outbox events."""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Any

from tokenbank.core.canonical import canonical_json_dumps


def event_row_to_document(row: sqlite3.Row) -> dict[str, Any]:
    return {
        "event_id": row["event_id"],
        "source": row["source"],
        "type": row["type"],
        "subject": row["subject"],
        "run_id": row["run_id"],
        "work_unit_id": row["work_unit_id"],
        "attempt_id": row["attempt_id"],
        "assignment_id": row["assignment_id"],
        "trace_id": row["trace_id"],
        "span_id": row["span_id"],
        "sequence": row["sequence"],
        "body": json.loads(row["body_json"]),
        "created_at": row["created_at"],
    }


def append_event_jsonl(path: str | Path, row: sqlite3.Row) -> None:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    with target.open("a", encoding="utf-8") as handle:
        handle.write(canonical_json_dumps(event_row_to_document(row)))
        handle.write("\n")

