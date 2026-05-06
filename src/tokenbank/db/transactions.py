"""Transaction helpers for atomic business changes and event outbox writes."""

from __future__ import annotations

import sqlite3
from collections.abc import Callable
from contextlib import contextmanager
from typing import TypeVar

from tokenbank.events.outbox import OutboxEventInput, enqueue_event

T = TypeVar("T")


@contextmanager
def transaction(conn: sqlite3.Connection):
    """Run a SQLite transaction using an immediate write lock."""
    conn.execute("BEGIN IMMEDIATE")
    try:
        yield conn
    except Exception:
        conn.rollback()
        raise
    else:
        conn.commit()


def write_business_change_with_event(
    conn: sqlite3.Connection,
    business_writer: Callable[[sqlite3.Connection], T],
    event: OutboxEventInput,
) -> tuple[T, str]:
    """Write a business change and its event_outbox row in one transaction."""
    with transaction(conn) as tx:
        result = business_writer(tx)
        event_id = enqueue_event(tx, event)
    return result, event_id

