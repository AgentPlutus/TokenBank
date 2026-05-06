"""Capacity discovery projection readers."""

from __future__ import annotations

import json
import sqlite3
from typing import Any


def discover_capacity_nodes(conn: sqlite3.Connection) -> list[dict[str, Any]]:
    """Return host-safe capacity discovery summaries."""
    rows = conn.execute(
        """
        SELECT
          capacity_node_id,
          node_type,
          status,
          worker_id,
          backend_id,
          backend_class,
          allowed_task_types_json,
          health_summary_json,
          manifest_hash
        FROM capacity_nodes
        ORDER BY capacity_node_id
        """
    ).fetchall()

    return [
        {
            "capacity_node_id": row["capacity_node_id"],
            "node_type": row["node_type"],
            "status": row["status"],
            "task_types": json.loads(row["allowed_task_types_json"]),
            "backend_classes": (
                [] if row["backend_class"] is None else [row["backend_class"]]
            ),
            "health": json.loads(row["health_summary_json"]),
            "worker_id": row["worker_id"],
            "backend_id": row["backend_id"],
            "manifest_hash": row["manifest_hash"],
        }
        for row in rows
    ]

