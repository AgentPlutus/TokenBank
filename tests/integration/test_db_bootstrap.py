from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from tokenbank.db.bootstrap import initialize_database


def test_sqlite_wal_enabled(tmp_path: Path) -> None:
    conn = initialize_database(tmp_path / "tokenbank.db")

    journal_mode = conn.execute("PRAGMA journal_mode").fetchone()[0]
    foreign_keys = conn.execute("PRAGMA foreign_keys").fetchone()[0]
    busy_timeout = conn.execute("PRAGMA busy_timeout").fetchone()[0]

    assert journal_mode == "wal"
    assert foreign_keys == 1
    assert busy_timeout == 5000


def test_core_wp2_tables_are_created(tmp_path: Path) -> None:
    conn = initialize_database(tmp_path / "tokenbank.db")
    rows = conn.execute(
        """
        SELECT name
        FROM sqlite_master
        WHERE type = 'table'
        """
    ).fetchall()
    table_names = {row["name"] for row in rows}

    assert {
        "runs",
        "work_units",
        "worker_manifests",
        "backend_manifests",
        "capacity_nodes",
        "capacity_node_health_snapshots",
        "event_outbox",
    }.issubset(table_names)


def test_foreign_keys_are_enforced(tmp_path: Path) -> None:
    conn = initialize_database(tmp_path / "tokenbank.db")

    with pytest.raises(sqlite3.IntegrityError):
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
            VALUES (
              'wu_missing_run',
              'run_missing',
              'submitted',
              'url_check',
              'L1',
              '{}',
              '2026-05-04T00:00:00Z',
              '2026-05-04T00:00:00Z'
            )
            """
        )

