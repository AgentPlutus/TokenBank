"""Read-only SQL helpers for observability reports."""

from __future__ import annotations

import json
import sqlite3
from typing import Any


def json_object(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return value
    if not isinstance(value, str) or not value:
        return {}
    try:
        loaded = json.loads(value)
    except json.JSONDecodeError:
        return {}
    return loaded if isinstance(loaded, dict) else {}


def work_unit_ids_for_run(conn: sqlite3.Connection, run_id: str) -> list[str]:
    return [
        row["work_unit_id"]
        for row in conn.execute(
            """
            SELECT work_unit_id
            FROM work_units
            WHERE run_id = ?
            ORDER BY created_at, work_unit_id
            """,
            (run_id,),
        ).fetchall()
    ]


def result_rows_for_run(
    conn: sqlite3.Connection,
    run_id: str,
) -> list[dict[str, Any]]:
    rows = conn.execute(
        """
        SELECT
          wu.run_id,
          wu.work_unit_id,
          wu.task_type,
          wu.task_level,
          wu.status AS work_unit_status,
          wu.body_json AS work_unit_body_json,
          a.assignment_id,
          a.attempt_id,
          a.worker_id,
          a.capacity_node_id,
          a.backend_id AS assignment_backend_id,
          a.status AS assignment_status,
          a.body_json AS assignment_body_json,
          a.effective_constraints_json,
          re.result_envelope_id,
          re.status AS result_status,
          re.output_hash,
          re.result_hash,
          re.body_json AS result_body_json,
          re.created_at AS result_created_at,
          vr.verifier_report_id,
          vr.status AS verifier_status,
          vr.recommendation,
          vr.body_json AS verifier_body_json,
          cn.backend_class AS capacity_backend_class,
          cn.node_type AS capacity_node_type,
          cn.status AS capacity_status,
          cn.body_json AS capacity_body_json
        FROM work_units wu
        LEFT JOIN assignments a
          ON a.work_unit_id = wu.work_unit_id
        LEFT JOIN result_envelopes re
          ON re.assignment_id = a.assignment_id
        LEFT JOIN verifier_reports vr
          ON vr.result_envelope_id = re.result_envelope_id
        LEFT JOIN capacity_nodes cn
          ON cn.capacity_node_id = a.capacity_node_id
        WHERE wu.run_id = ?
        ORDER BY wu.created_at, a.created_at, re.created_at
        """,
        (run_id,),
    ).fetchall()
    return [_decode_result_row(row) for row in rows]


def event_summary_for_run(conn: sqlite3.Connection, run_id: str) -> dict[str, Any]:
    work_unit_ids = work_unit_ids_for_run(conn, run_id)
    clauses = ["run_id = ?"]
    params: list[Any] = [run_id]
    if work_unit_ids:
        placeholders = ", ".join("?" for _ in work_unit_ids)
        clauses.append(f"work_unit_id IN ({placeholders})")
        params.extend(work_unit_ids)
    rows = conn.execute(
        f"""
        SELECT type, status, COUNT(*) AS count
        FROM event_outbox
        WHERE {" OR ".join(clauses)}
        GROUP BY type, status
        ORDER BY type, status
        """,
        params,
    ).fetchall()
    by_type: dict[str, int] = {}
    by_status: dict[str, int] = {}
    total = 0
    for row in rows:
        count = int(row["count"])
        by_type[row["type"]] = by_type.get(row["type"], 0) + count
        by_status[row["status"]] = by_status.get(row["status"], 0) + count
        total += count
    return {
        "event_count": total,
        "by_type": by_type,
        "by_status": by_status,
        "source": "event_outbox",
    }


def business_state_snapshot(conn: sqlite3.Connection, run_id: str) -> dict[str, Any]:
    work_unit_ids = work_unit_ids_for_run(conn, run_id)
    if not work_unit_ids:
        return {
            "work_units": [],
            "assignments": [],
            "verifier_reports": [],
        }
    placeholders = ", ".join("?" for _ in work_unit_ids)
    work_units = [
        dict(row)
        for row in conn.execute(
            f"""
            SELECT work_unit_id, status, updated_at
            FROM work_units
            WHERE work_unit_id IN ({placeholders})
            ORDER BY work_unit_id
            """,
            work_unit_ids,
        ).fetchall()
    ]
    assignments = [
        dict(row)
        for row in conn.execute(
            f"""
            SELECT assignment_id, status, updated_at
            FROM assignments
            WHERE work_unit_id IN ({placeholders})
            ORDER BY assignment_id
            """,
            work_unit_ids,
        ).fetchall()
    ]
    verifier_reports = [
        dict(row)
        for row in conn.execute(
            f"""
            SELECT verifier_report_id, status, recommendation, body_json
            FROM verifier_reports
            WHERE work_unit_id IN ({placeholders})
            ORDER BY verifier_report_id
            """,
            work_unit_ids,
        ).fetchall()
    ]
    return {
        "work_units": work_units,
        "assignments": assignments,
        "verifier_reports": verifier_reports,
    }


def _decode_result_row(row: sqlite3.Row) -> dict[str, Any]:
    item = dict(row)
    item["work_unit_body"] = json_object(item.pop("work_unit_body_json", None))
    item["assignment_body"] = json_object(item.pop("assignment_body_json", None))
    item["effective_constraints"] = json_object(
        item.pop("effective_constraints_json", None)
    )
    item["result_body"] = json_object(item.pop("result_body_json", None))
    item["verifier_body"] = json_object(item.pop("verifier_body_json", None))
    item["capacity_body"] = json_object(item.pop("capacity_body_json", None))
    return item
