from __future__ import annotations

import json
from pathlib import Path

import pytest

from tokenbank.core.canonical import canonical_json_dumps
from tokenbank.db.bootstrap import initialize_database
from tokenbank.db.transactions import write_business_change_with_event
from tokenbank.events.flusher import flush_pending_events
from tokenbank.events.outbox import OutboxEventInput


def _insert_run_and_work_unit(conn) -> str:
    now = "2026-05-04T00:00:00Z"
    run_body = {"run_id": "run_001", "status": "created"}
    work_body = {
        "work_unit_id": "wu_001",
        "run_id": "run_001",
        "status": "submitted",
        "task_type": "url_check",
        "task_level": "L1",
    }
    conn.execute(
        """
        INSERT INTO runs (run_id, status, body_json, created_at, updated_at)
        VALUES (?, ?, ?, ?, ?)
        """,
        ("run_001", "created", canonical_json_dumps(run_body), now, now),
    )
    conn.execute(
        """
        INSERT INTO work_units (
          work_unit_id,
          run_id,
          status,
          task_type,
          task_level,
          body_json,
          created_at,
          updated_at
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            "wu_001",
            "run_001",
            "submitted",
            "url_check",
            "L1",
            canonical_json_dumps(work_body),
            now,
            now,
        ),
    )
    return "wu_001"


def test_business_change_and_event_outbox_are_atomic(tmp_path: Path) -> None:
    conn = initialize_database(tmp_path / "tokenbank.db")
    event = OutboxEventInput(
        source="tokenbank.tests",
        type="work_unit.created",
        subject="work_units/wu_001",
        run_id="run_001",
        work_unit_id="wu_001",
        trace_id="trace_001",
        body={"work_unit_id": "wu_001"},
    )

    work_unit_id, event_id = write_business_change_with_event(
        conn,
        _insert_run_and_work_unit,
        event,
    )

    assert work_unit_id == "wu_001"
    assert event_id
    assert conn.execute("SELECT COUNT(*) FROM work_units").fetchone()[0] == 1
    assert conn.execute("SELECT COUNT(*) FROM event_outbox").fetchone()[0] == 1


def test_business_change_rolls_back_when_event_insert_fails(tmp_path: Path) -> None:
    conn = initialize_database(tmp_path / "tokenbank.db")
    bad_event = OutboxEventInput(
        source="tokenbank.tests",
        type="work_unit.created",
        subject="work_units/wu_001",
        trace_id="trace_001",
        body={"work_unit_id": "wu_001"},
    )
    conn.execute("DROP TABLE event_outbox")
    conn.commit()

    with pytest.raises(Exception):  # noqa: B017 - exact sqlite error varies by version.
        write_business_change_with_event(conn, _insert_run_and_work_unit, bad_event)

    assert conn.execute("SELECT COUNT(*) FROM work_units").fetchone()[0] == 0


def test_pending_events_flush_to_jsonl_and_mark_written(tmp_path: Path) -> None:
    conn = initialize_database(tmp_path / "tokenbank.db")
    event = OutboxEventInput(
        source="tokenbank.tests",
        type="work_unit.created",
        subject="work_units/wu_001",
        run_id="run_001",
        work_unit_id="wu_001",
        trace_id="trace_001",
        body={"work_unit_id": "wu_001"},
    )
    write_business_change_with_event(conn, _insert_run_and_work_unit, event)

    result = flush_pending_events(conn, tmp_path / "events" / "tokenbank.jsonl")

    assert result.written == 1
    assert result.failed == 0
    row = conn.execute("SELECT status, written_at FROM event_outbox").fetchone()
    assert row["status"] == "written"
    assert row["written_at"] is not None

    line = (tmp_path / "events" / "tokenbank.jsonl").read_text(encoding="utf-8")
    document = json.loads(line)
    assert document["type"] == "work_unit.created"
    assert document["body"] == {"work_unit_id": "wu_001"}


def test_failed_jsonl_write_marks_event_failed(tmp_path: Path) -> None:
    conn = initialize_database(tmp_path / "tokenbank.db")
    event = OutboxEventInput(
        source="tokenbank.tests",
        type="work_unit.created",
        subject="work_units/wu_001",
        run_id="run_001",
        work_unit_id="wu_001",
        trace_id="trace_001",
        body={"work_unit_id": "wu_001"},
    )
    write_business_change_with_event(conn, _insert_run_and_work_unit, event)
    directory_path = tmp_path / "events_dir"
    directory_path.mkdir()

    result = flush_pending_events(conn, directory_path)

    assert result.written == 0
    assert result.failed == 1
    row = conn.execute(
        "SELECT status, failure_count, last_error FROM event_outbox"
    ).fetchone()
    assert row["status"] == "failed"
    assert row["failure_count"] == 1
    assert row["last_error"]

