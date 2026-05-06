"""Routebook-backed task level classifier."""

from __future__ import annotations

from typing import Any

from tokenbank.routebook.loader import LoadedRoutebook


def classify_task_level(
    work_unit: dict[str, Any],
    routebook: LoadedRoutebook,
) -> str:
    explicit_level = work_unit.get("task_level")
    if explicit_level:
        return str(explicit_level)
    task_type = str(work_unit["task_type"])
    return str(routebook.task_type_entry(task_type)["default_task_level"])

