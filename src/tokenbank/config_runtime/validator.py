"""Cross-registry validator for WP3 static config."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from tokenbank.capacity.validators import (
    API_GATEWAY_BACKEND_CLASSES,
    CONTROL_PLANE_GATEWAY_WORKER_ID,
    CapacityRegistryValidationError,
    validate_backend_execution_location,
)
from tokenbank.config_runtime.loader import LoadedConfig, load_config_dir
from tokenbank.config_runtime.runtime_mode import RuntimeMode
from tokenbank.models.backend import BackendHealth, BackendManifest
from tokenbank.models.common import CostModel
from tokenbank.policy.extensions import lint_extension_keys


@dataclass(frozen=True)
class ValidationIssue:
    code: str
    message: str


@dataclass(frozen=True)
class ValidationResult:
    ok: bool
    issues: list[ValidationIssue]
    content_hashes: dict[str, str]


def _issue(issues: list[ValidationIssue], code: str, message: str) -> None:
    issues.append(ValidationIssue(code=code, message=message))


def _backend_registry(config: LoadedConfig) -> list[dict[str, Any]]:
    document = config.documents["backend_registry"].get("backend_registry", {})
    return list(document.get("backends", []))


def _backend_policy(config: LoadedConfig) -> dict[str, Any]:
    return dict(config.documents["backend_policy"].get("backend_policy", {}))


def _runtime(config: LoadedConfig) -> dict[str, Any]:
    return dict(config.documents["runtime"].get("runtime", {}))


def _routebook(config: LoadedConfig) -> dict[str, Any]:
    return dict(config.documents["runtime"].get("routebook", {}))


def _verifier_recipes(config: LoadedConfig) -> list[dict[str, Any]]:
    return list(config.documents["runtime"].get("verifier_recipes", []))


def _capacity_registry(config: LoadedConfig) -> dict[str, Any]:
    return dict(config.documents["capacity_registry"].get("capacity_registry", {}))


def _pricing_backend_ids(config: LoadedConfig) -> set[str]:
    backend_ids: set[str] = set()
    for document in config.documents["pricing"].get("documents", []):
        pricing = document.get("pricing", {})
        for price in pricing.get("backend_prices", []):
            backend_ids.add(str(price.get("backend_id", "")))
    return backend_ids


def _backend_manifest_for_validation(payload: dict[str, Any]) -> BackendManifest:
    backend_id = str(payload["backend_id"])
    cost_model = payload.get("cost_model", {})
    return BackendManifest(
        backend_id=backend_id,
        backend_class=payload["backend_class"],
        capacity_node_id=payload["capacity_node_id"],
        display_name=payload.get("display_name", backend_id),
        version=payload.get("version", "v0"),
        supported_task_types=payload.get("supported_task_types", []),
        allowed_privacy_levels=payload.get("allowed_privacy_levels", ["private"]),
        execution_location=payload["execution_location"],
        manifest_hash=payload["manifest_hash"],
        health=BackendHealth(
            backend_id=backend_id,
            status=payload.get("health_status", "healthy"),
        ),
        cost_model=CostModel(
            estimated_cost_micros=int(cost_model.get("estimated_cost_micros", 0)),
            cost_source=cost_model.get("cost_source", "policy_default"),
        ),
        policy_constraints=payload.get("policy_constraints", {}),
    )


def _validate_runtime_mode(config: LoadedConfig, issues: list[ValidationIssue]) -> None:
    runtime_mode = _runtime(config).get("runtime_mode")
    try:
        RuntimeMode(runtime_mode)
    except ValueError:
        _issue(
            issues,
            "runtime_mode.invalid",
            f"runtime_mode must be demo, internal_secure, or alpha: {runtime_mode}",
        )


def _validate_routebook_and_backend_registry(
    config: LoadedConfig,
    issues: list[ValidationIssue],
) -> None:
    backends = _backend_registry(config)
    backend_ids = {str(backend.get("backend_id")) for backend in backends}
    backend_classes = {str(backend.get("backend_class")) for backend in backends}
    policy = _backend_policy(config)
    allowed_backend_ids = set(policy.get("allowed_backend_ids", []))
    forbidden_backend_classes = set(policy.get("forbidden_backend_classes", []))
    api_backend_classes = set(policy.get("api_backend_classes", []))
    routebook = _routebook(config)
    routebook_classes = set(routebook.get("backend_classes", []))
    candidate_rules = list(routebook.get("candidate_rules", []))
    verifier_recipe_ids = {
        str(recipe.get("verifier_recipe_id")) for recipe in _verifier_recipes(config)
    }
    task_types = set(routebook.get("task_types", []))
    pricing_backend_ids = _pricing_backend_ids(config)

    missing_routebook_classes = sorted(routebook_classes - backend_classes)
    if missing_routebook_classes:
        _issue(
            issues,
            "routebook.backend_class_missing",
            "routebook backend_classes missing from backend_registry: "
            f"{missing_routebook_classes}",
        )

    for rule in candidate_rules:
        rule_id = rule.get("rule_id", "<unknown>")
        backend_class = str(rule.get("backend_class"))
        backend_id = str(rule.get("backend_id"))
        verifier_recipe_id = str(rule.get("verifier_recipe_id"))
        if backend_class not in backend_classes:
            _issue(
                issues,
                "routebook.rule_backend_class_missing",
                f"candidate rule {rule_id} backend_class is not registered: "
                f"{backend_class}",
            )
        if backend_class in forbidden_backend_classes:
            _issue(
                issues,
                "routebook.forbidden_backend_class",
                f"candidate rule {rule_id} uses forbidden backend_class: "
                f"{backend_class}",
            )
        if backend_id not in backend_ids:
            _issue(
                issues,
                "routebook.rule_backend_id_missing",
                f"candidate rule {rule_id} backend_id is not registered: {backend_id}",
            )
        if verifier_recipe_id not in verifier_recipe_ids:
            _issue(
                issues,
                "routebook.verifier_recipe_missing",
                f"candidate rule {rule_id} verifier_recipe_id is missing: "
                f"{verifier_recipe_id}",
            )

    for backend in backends:
        backend_id = str(backend.get("backend_id"))
        backend_class = str(backend.get("backend_class"))
        try:
            validate_backend_execution_location(
                _backend_manifest_for_validation(backend)
            )
        except (CapacityRegistryValidationError, ValueError) as exc:
            _issue(
                issues,
                "backend_registry.execution_location_invalid",
                f"backend {backend_id} execution_location invalid: {exc}",
            )
        if allowed_backend_ids and backend_id not in allowed_backend_ids:
            _issue(
                issues,
                "backend_policy.backend_id_not_allowed",
                "backend_registry backend_id not allowed by backend_policy: "
                f"{backend_id}",
            )
        pricing_missing = backend_id not in pricing_backend_ids
        if backend_class in api_backend_classes and pricing_missing:
            _issue(
                issues,
                "pricing.api_backend_missing",
                f"pricing table must cover API backend: {backend_id}",
            )

    for allowed_backend_id in sorted(allowed_backend_ids):
        if allowed_backend_id not in backend_ids:
            _issue(
                issues,
                "backend_policy.allowed_backend_missing",
                "allowed_backend_id missing from backend_registry: "
                f"{allowed_backend_id}",
            )

    for recipe in _verifier_recipes(config):
        recipe_id = recipe.get("verifier_recipe_id")
        task_type = recipe.get("task_type")
        if task_type not in task_types:
            _issue(
                issues,
                "verifier_recipe.task_type_unknown",
                f"verifier recipe {recipe_id} maps to unknown task_type: {task_type}",
            )


def _validate_capacity_registry(
    config: LoadedConfig,
    issues: list[ValidationIssue],
) -> None:
    backends = _backend_registry(config)
    backend_by_id = {str(backend.get("backend_id")): backend for backend in backends}
    capacity = _capacity_registry(config)
    worker_manifests = list(capacity.get("worker_manifests", []))
    workers_by_id = {
        str(worker.get("worker_id")): worker
        for worker in worker_manifests
    }
    expected_node_ids = {
        f"capnode:worker:{worker_id}"
        for worker_id in workers_by_id
    }
    expected_node_ids.update(
        str(backend.get("capacity_node_id"))
        for backend in backends
    )
    declared_node_ids = {
        str(node.get("capacity_node_id"))
        for node in capacity.get("capacity_nodes", [])
    }

    missing_nodes = sorted(expected_node_ids - declared_node_ids)
    if missing_nodes:
        _issue(
            issues,
            "capacity_node.projection_missing",
            "capacity registry is missing projected capacity nodes: "
            f"{missing_nodes}",
        )

    extra_nodes = sorted(declared_node_ids - expected_node_ids)
    if extra_nodes:
        _issue(
            issues,
            "capacity_node.projection_extra",
            "capacity registry declares nodes outside worker/backend manifests: "
            f"{extra_nodes}",
        )

    for worker in worker_manifests:
        worker_id = str(worker.get("worker_id"))
        for backend_id in worker.get("backend_ids", []):
            if backend_id not in backend_by_id:
                _issue(
                    issues,
                    "worker_manifest.backend_id_missing",
                    f"worker {worker_id} references unknown backend_id: {backend_id}",
                )
                continue
            backend_class = str(backend_by_id[backend_id].get("backend_class"))
            if (
                backend_class in API_GATEWAY_BACKEND_CLASSES
                and worker_id != CONTROL_PLANE_GATEWAY_WORKER_ID
            ):
                _issue(
                    issues,
                    "worker_manifest.api_backend_direct_denied",
                    "worker direct API model backend path is denied: "
                    f"{worker_id} -> {backend_id}",
                )

    for node in capacity.get("capacity_nodes", []):
        source = node.get("source")
        if source == "worker_manifest":
            worker_id = str(node.get("worker_id"))
            worker = workers_by_id.get(worker_id)
            if worker is None:
                _issue(
                    issues,
                    "capacity_node.worker_missing",
                    f"capacity node references unknown worker_id: {worker_id}",
                )
                continue
            if node.get("manifest_hash") != worker.get("manifest_hash"):
                _issue(
                    issues,
                    "capacity_node.worker_manifest_hash_mismatch",
                    f"capacity node worker manifest_hash drift: {worker_id}",
                )
        elif source == "backend_manifest":
            backend_id = str(node.get("backend_id"))
            backend = backend_by_id.get(backend_id)
            if backend is None:
                _issue(
                    issues,
                    "capacity_node.backend_missing",
                    f"capacity node references unknown backend_id: {backend_id}",
                )
                continue
            if node.get("manifest_hash") != backend.get("manifest_hash"):
                _issue(
                    issues,
                    "capacity_node.backend_manifest_hash_mismatch",
                    f"capacity node backend manifest_hash drift: {backend_id}",
                )
        else:
            _issue(
                issues,
                "capacity_node.source_unknown",
                "capacity node source must be worker_manifest or backend_manifest: "
                f"{source}",
            )


def _validate_policy_shape(config: LoadedConfig, issues: list[ValidationIssue]) -> None:
    lint_targets = {
        "runtime": config.documents["runtime"],
        "backend_registry": config.documents["backend_registry"],
        "capacity_registry": config.documents["capacity_registry"],
    }
    for name, document in lint_targets.items():
        for lint_issue in lint_extension_keys(document, f"$.{name}"):
            _issue(
                issues,
                "extensions.forbidden_key",
                f"{lint_issue.path}: {lint_issue.reason}",
            )

    backend_policy = _backend_policy(config)
    for key in ("allowed_backend_ids", "allowed_backend_classes"):
        values = backend_policy.get(key, [])
        if not isinstance(values, list):
            _issue(
                issues,
                "backend_policy.invalid_shape",
                f"backend_policy.{key} must be a list",
            )


def validate_loaded_config(config: LoadedConfig) -> ValidationResult:
    issues: list[ValidationIssue] = []
    _validate_runtime_mode(config, issues)
    _validate_routebook_and_backend_registry(config, issues)
    _validate_capacity_registry(config, issues)
    _validate_policy_shape(config, issues)
    return ValidationResult(
        ok=not issues,
        issues=issues,
        content_hashes=config.content_hashes,
    )


def validate_config_dir(config_dir: str | Path = "config") -> ValidationResult:
    return validate_loaded_config(load_config_dir(config_dir))
