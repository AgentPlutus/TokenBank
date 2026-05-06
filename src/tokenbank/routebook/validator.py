"""Routebook validator."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from tokenbank.backends.registry import BackendRegistry
from tokenbank.config_runtime.loader import load_config_dir
from tokenbank.routebook.loader import LoadedRoutebook, load_routebook_dir


@dataclass(frozen=True)
class RoutebookValidationIssue:
    code: str
    message: str


@dataclass(frozen=True)
class RoutebookValidationResult:
    ok: bool
    issues: list[RoutebookValidationIssue]
    content_hashes: dict[str, str]


P0_TASK_TYPES = {
    "claim_extraction",
    "dedup",
    "topic_classification",
    "url_check",
    "webpage_extraction",
}


def _issue(
    issues: list[RoutebookValidationIssue],
    code: str,
    message: str,
) -> None:
    issues.append(RoutebookValidationIssue(code=code, message=message))


def validate_routebook(
    routebook: LoadedRoutebook | None = None,
    *,
    routebook_dir: str | Path = "routebook",
    config_dir: str | Path = "config",
) -> RoutebookValidationResult:
    loaded = routebook or load_routebook_dir(routebook_dir)
    config = load_config_dir(config_dir)
    backend_registry = BackendRegistry.from_config(config)
    issues: list[RoutebookValidationIssue] = []

    task_types = {
        str(entry.get("task_type"))
        for entry in loaded.task_types
    }
    missing_p0 = sorted(P0_TASK_TYPES - task_types)
    if missing_p0:
        _issue(issues, "routebook.p0_task_missing", f"missing P0 tasks: {missing_p0}")

    verifier_mapping = loaded.verifier_mapping
    recipe_task_types = {
        str(recipe.get("task_type"))
        for recipe in loaded.verifier_recipes
    }
    recipe_ids = {
        str(recipe.get("verifier_recipe_id"))
        for recipe in loaded.verifier_recipes
    }
    for task_type in sorted(P0_TASK_TYPES):
        verifier_recipe_id = verifier_mapping.get(task_type)
        if not verifier_recipe_id:
            _issue(
                issues,
                "routebook.verifier_missing",
                f"missing verifier mapping for task_type: {task_type}",
            )
        elif verifier_recipe_id not in recipe_ids:
            _issue(
                issues,
                "routebook.verifier_recipe_unknown",
                f"verifier recipe id is not declared: {verifier_recipe_id}",
            )
        if task_type not in recipe_task_types:
            _issue(
                issues,
                "routebook.verifier_task_missing",
                f"missing verifier recipe for task_type: {task_type}",
            )

    known_classes = backend_registry.backend_classes
    known_backend_ids = backend_registry.backend_ids
    task_levels = loaded.task_levels
    for rule in loaded.candidate_rules:
        rule_id = str(rule.get("rule_id", "<unknown>"))
        task_type = str(rule.get("task_type"))
        backend_class = str(rule.get("backend_class"))
        backend_id = str(rule.get("backend_id"))
        if task_type not in task_types:
            _issue(
                issues,
                "routebook.rule_task_unknown",
                f"rule {rule_id} task_type is unknown: {task_type}",
            )
        if backend_class not in known_classes:
            _issue(
                issues,
                "routebook.backend_class_unknown",
                f"rule {rule_id} backend_class is unknown: {backend_class}",
            )
        if backend_id not in known_backend_ids:
            _issue(
                issues,
                "routebook.backend_id_unknown",
                f"rule {rule_id} backend_id is unknown: {backend_id}",
            )

    for task_type, verifier_recipe_id in verifier_mapping.items():
        try:
            task_entry = loaded.task_type_entry(task_type)
        except KeyError:
            continue
        level = str(task_entry.get("default_task_level"))
        requires_verifier = task_levels.get(level, {}).get(
            "requires_verifier_recipe_id",
            level in {"L1", "L2", "L3"},
        )
        if requires_verifier and not verifier_recipe_id:
            _issue(
                issues,
                "routebook.level_requires_verifier",
                f"{level} task_type requires verifier_recipe_id: {task_type}",
            )

    return RoutebookValidationResult(
        ok=not issues,
        issues=issues,
        content_hashes=loaded.content_hashes,
    )

