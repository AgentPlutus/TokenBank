from __future__ import annotations

import sqlite3
from pathlib import Path

from typer.testing import CliRunner

from tokenbank.cli.main import app
from tokenbank.db.bootstrap import initialize_database


def test_account_snapshot_rejects_raw_secret_ref_and_does_not_persist(
    tmp_path: Path,
) -> None:
    db_path = tmp_path / "tokenbank.db"
    raw_secret = "sk-testsecret1234567890"
    result = CliRunner().invoke(
        app,
        [
            "accounts",
            "snapshot",
            "--provider",
            "openai",
            "--account-label",
            "bad",
            "--secret-ref",
            f"keychain:tokenbank/{raw_secret}",
            "--db-path",
            str(db_path),
            "--json",
        ],
    )

    assert result.exit_code != 0
    assert raw_secret not in result.output

    conn = initialize_database(db_path)
    try:
        serialized = _dump_tables(
            conn,
            [
                "account_snapshots",
                "usage_ledger_entries",
                "audit_receipts",
                "event_outbox",
            ],
        )
    finally:
        conn.close()
    assert raw_secret not in serialized


def _dump_tables(conn: sqlite3.Connection, tables: list[str]) -> str:
    chunks: list[str] = []
    for table in tables:
        rows = conn.execute(f"SELECT * FROM {table}").fetchall()
        chunks.extend(str(dict(row)) for row in rows)
    return "\n".join(chunks)
