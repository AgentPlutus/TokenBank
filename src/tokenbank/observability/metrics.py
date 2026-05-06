"""Derived cost and quality metrics."""

from __future__ import annotations

from collections import defaultdict
from typing import Any

from tokenbank.observability.cost_accounting import effective_cost_micros


def summarize_totals(rows: list[dict[str, Any]]) -> dict[str, Any]:
    return _summary_for_rows(rows)


def summarize_by_key(
    rows: list[dict[str, Any]],
    key: str,
    output_key: str,
) -> list[dict[str, Any]]:
    groups: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        groups[_group_value(row, key)].append(row)
    return [
        {output_key: group_key, **_summary_for_rows(group_rows)}
        for group_key, group_rows in sorted(groups.items())
    ]


def capacity_node_summaries(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    groups: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        groups[
            (
                str(row.get("capacity_node_id") or "unknown_capacity_node"),
                backend_class(row),
            )
        ].append(row)
    return [
        {
            "capacity_node_id": capacity_node_id,
            "backend_class": backend_cls,
            **_summary_for_rows(group_rows),
        }
        for (capacity_node_id, backend_cls), group_rows in sorted(groups.items())
    ]


def backend_task_worker_summaries(rows: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "by_task_type": summarize_by_key(rows, "task_type", "task_type"),
        "by_backend_class": summarize_by_key(
            rows,
            "backend_class",
            "backend_class",
        ),
        "by_worker": summarize_by_key(rows, "worker_id", "worker_id"),
        "by_capacity_node": capacity_node_summaries(rows),
    }


def backend_class(row: dict[str, Any]) -> str:
    result_body = row.get("result_body") or {}
    assignment_body = row.get("assignment_body") or {}
    capacity_body = row.get("capacity_body") or {}
    return str(
        result_body.get("backend_class")
        or assignment_body.get("backend_class")
        or row.get("capacity_backend_class")
        or _first_backend_class(capacity_body)
        or "unknown_backend_class"
    )


def _summary_for_rows(rows: list[dict[str, Any]]) -> dict[str, Any]:
    work_unit_ids = {
        row["work_unit_id"]
        for row in rows
        if row.get("work_unit_id")
    }
    return {
        "work_unit_count": len(work_unit_ids),
        "success_count": sum(1 for row in rows if _bucket(row) == "success"),
        "warning_count": sum(1 for row in rows if _bucket(row) == "warning"),
        "failure_count": sum(1 for row in rows if _bucket(row) == "failure"),
        "quarantine_count": sum(1 for row in rows if _bucket(row) == "quarantine"),
        "backend_failure_count": sum(1 for row in rows if _backend_failed(row)),
        "verifier_failure_count": sum(1 for row in rows if _verifier_failed(row)),
        "duration_ms": sum(_duration_ms(row) for row in rows),
        "cost_micros": sum(effective_cost_micros(row["result_body"]) for row in rows),
        "estimated_cost_micros": sum(
            _non_negative_int(row["result_body"].get("cost_estimate_micros"))
            for row in rows
        ),
        "actual_cost_micros": sum(
            _non_negative_int(row["result_body"].get("actual_cost_micros"))
            for row in rows
        ),
    }


def _bucket(row: dict[str, Any]) -> str:
    result_body = row["result_body"]
    verifier_body = row["verifier_body"]
    recommendation = str(
        row.get("recommendation") or verifier_body.get("recommendation") or ""
    )
    verifier_status = str(row.get("verifier_status") or verifier_body.get("status"))
    if result_body.get("status") == "quarantined" or recommendation == "quarantine":
        return "quarantine"
    if result_body.get("status") == "failed":
        return "failure"
    if recommendation == "accept_with_warning" or verifier_status == "needs_review":
        return "warning"
    if recommendation == "accept" and verifier_status == "passed":
        return "success"
    return "failure"


def _backend_failed(row: dict[str, Any]) -> bool:
    result_body = row["result_body"]
    errors = result_body.get("errors")
    return result_body.get("status") == "failed" or bool(errors)


def _verifier_failed(row: dict[str, Any]) -> bool:
    verifier_body = row["verifier_body"]
    recommendation = str(
        row.get("recommendation") or verifier_body.get("recommendation") or ""
    )
    if recommendation == "quarantine":
        return False
    return str(row.get("verifier_status") or verifier_body.get("status")) == "failed"


def _duration_ms(row: dict[str, Any]) -> int:
    return _non_negative_int(row["result_body"].get("duration_ms"))


def _group_value(row: dict[str, Any], key: str) -> str:
    if key == "backend_class":
        return backend_class(row)
    value = row.get(key)
    if value is None and key == "worker_id":
        value = row["result_body"].get("worker_id")
    return str(value or f"unknown_{key}")


def _first_backend_class(capacity_body: dict[str, Any]) -> str | None:
    backend_classes = capacity_body.get("backend_classes")
    if isinstance(backend_classes, list) and backend_classes:
        value = backend_classes[0]
        return value if isinstance(value, str) else None
    return None


def _non_negative_int(value: Any) -> int:
    if isinstance(value, bool):
        return 0
    if isinstance(value, int) and value >= 0:
        return value
    return 0
