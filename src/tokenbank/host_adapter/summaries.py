"""Host-facing response helpers for WP12 ingress."""

from __future__ import annotations

from typing import Any

from tokenbank.models.host_summary import HostResultSummary
from tokenbank.routebook.loader import LoadedRoutebook


def host_result_response(
    *,
    work_unit_id: str,
    summary: HostResultSummary | None,
    work_unit_exists: bool,
) -> dict[str, Any]:
    """Return a stable host-safe result response."""
    if not work_unit_exists:
        return {
            "status": "not_found",
            "work_unit_id": work_unit_id,
            "host_result_summary": None,
        }
    if summary is None:
        return {
            "status": "pending",
            "work_unit_id": work_unit_id,
            "host_result_summary": None,
        }
    return {
        "status": "ok",
        "work_unit_id": work_unit_id,
        "host_result_summary": summary.model_dump(mode="json"),
    }


def routebook_excerpt(
    routebook: LoadedRoutebook,
    *,
    task_type: str | None = None,
) -> dict[str, Any]:
    """Return a bounded routebook excerpt without exposing workspace files."""
    if task_type is None:
        return {
            "status": "ok",
            "task_types": routebook.task_types,
            "verifier_mapping": routebook.verifier_mapping,
            "policy_hints": routebook.policy_hints,
            "content_hashes": routebook.content_hashes,
        }

    task_entry = routebook.task_type_entry(task_type)
    return {
        "status": "ok",
        "task_type": task_type,
        "task_type_entry": task_entry,
        "candidate_rules": [
            rule
            for rule in routebook.candidate_rules
            if rule.get("task_type") == task_type
        ],
        "fallback_rules": [
            rule
            for rule in routebook.fallback_rules
            if rule.get("task_type") == task_type
        ],
        "policy_hints": routebook.policy_hints.get(task_type, []),
        "verifier_recipe_id": routebook.verifier_mapping.get(task_type),
        "content_hashes": routebook.content_hashes,
    }
