"""Database migration bootstrap."""

from __future__ import annotations

import sqlite3
from pathlib import Path

from tokenbank.db.connection import connect

MIGRATIONS_DIR = Path(__file__).parent / "migrations"


def _ensure_migration_table(conn: sqlite3.Connection) -> None:
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS schema_migrations (
          version TEXT PRIMARY KEY,
          applied_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now'))
        )
        """
    )
    conn.commit()


def migration_files(migrations_dir: Path = MIGRATIONS_DIR) -> list[Path]:
    return sorted(migrations_dir.glob("*.sql"))


def apply_migrations(
    conn: sqlite3.Connection,
    migrations_dir: Path = MIGRATIONS_DIR,
) -> list[str]:
    """Apply unapplied raw SQL migrations and return applied versions."""
    _ensure_migration_table(conn)
    applied: list[str] = []

    existing = {
        row["version"]
        for row in conn.execute("SELECT version FROM schema_migrations").fetchall()
    }
    for migration in migration_files(migrations_dir):
        version = migration.stem
        if version in existing:
            continue

        sql = migration.read_text(encoding="utf-8")
        conn.executescript(sql)
        conn.execute(
            "INSERT INTO schema_migrations (version) VALUES (?)",
            (version,),
        )
        conn.commit()
        applied.append(version)

    return applied


def initialize_database(db_path: str | Path) -> sqlite3.Connection:
    """Open and migrate the SQLite control-plane database."""
    conn = connect(db_path)
    apply_migrations(conn)
    return conn

