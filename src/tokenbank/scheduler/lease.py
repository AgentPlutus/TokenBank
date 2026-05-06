"""Lease token and conditional update helpers."""

from __future__ import annotations

import secrets
import sqlite3
from datetime import UTC, datetime, timedelta

from tokenbank.core.tokens import assignment_lease_token_hash


class LeaseConflictError(RuntimeError):
    """Raised when a lease conditional update fails."""


def utc_now() -> datetime:
    return datetime.now(UTC)


def utc_text(value: datetime | None = None) -> str:
    return (value or utc_now()).isoformat().replace("+00:00", "Z")


def parse_utc(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def new_lease_token() -> str:
    return f"tbk_l_{secrets.token_urlsafe(24)}"


def lease_token_hash(raw_token: str) -> str:
    return assignment_lease_token_hash(raw_token)


def lease_token_prefix(raw_token: str) -> str:
    return raw_token[:16]


def lease_expiry(milliseconds: int) -> str:
    return utc_text(utc_now() + timedelta(milliseconds=milliseconds))


def verify_lease_token(stored_hash: str | None, raw_token: str | None) -> None:
    if not stored_hash or not raw_token or lease_token_hash(raw_token) != stored_hash:
        raise PermissionError("invalid assignment lease token")


def verify_lease_token_hash(
    stored_hash: str | None,
    provided_hash: str | None,
) -> None:
    if not stored_hash or not provided_hash or provided_hash != stored_hash:
        raise PermissionError("invalid assignment lease token hash")


def conditional_assignment_update(
    conn: sqlite3.Connection,
    *,
    assignment_id: str,
    expected_lease_version: int,
    status: str,
    lease_expires_at: str | None,
    lease_token_hash_value: str | None = None,
    lease_token_prefix_value: str | None = None,
    accepted_at: str | None = None,
    completed_at: str | None = None,
) -> sqlite3.Row:
    current = conn.execute(
        "SELECT * FROM assignments WHERE assignment_id = ?",
        (assignment_id,),
    ).fetchone()
    if current is None:
        raise KeyError(f"assignment not found: {assignment_id}")
    next_version = int(current["lease_version"]) + 1
    cursor = conn.execute(
        """
        UPDATE assignments
        SET status = ?,
            lease_version = ?,
            lease_expires_at = ?,
            lease_token_hash = COALESCE(?, lease_token_hash),
            lease_token_prefix = COALESCE(?, lease_token_prefix),
            accepted_at = COALESCE(?, accepted_at),
            completed_at = COALESCE(?, completed_at),
            updated_at = ?
        WHERE assignment_id = ?
          AND lease_version = ?
        """,
        (
            status,
            next_version,
            lease_expires_at,
            lease_token_hash_value,
            lease_token_prefix_value,
            accepted_at,
            completed_at,
            utc_text(),
            assignment_id,
            expected_lease_version,
        ),
    )
    if cursor.rowcount == 0:
        raise LeaseConflictError("assignment lease_version conflict")
    return conn.execute(
        "SELECT * FROM assignments WHERE assignment_id = ?",
        (assignment_id,),
    ).fetchone()
