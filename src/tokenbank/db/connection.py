"""SQLite connection helpers."""

from __future__ import annotations

import sqlite3
from pathlib import Path

DEFAULT_BUSY_TIMEOUT_MS = 5_000


def apply_pragmas(conn: sqlite3.Connection) -> None:
    """Apply required SQLite pragmas for the control-plane database."""
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute(f"PRAGMA busy_timeout = {DEFAULT_BUSY_TIMEOUT_MS}")
    conn.execute("PRAGMA journal_mode = WAL")


def connect(db_path: str | Path) -> sqlite3.Connection:
    """Open a SQLite connection configured for TokenBank WP2."""
    path = Path(db_path)
    if path != Path(":memory:"):
        path.parent.mkdir(parents=True, exist_ok=True)

    conn = sqlite3.connect(path, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    apply_pragmas(conn)
    return conn
