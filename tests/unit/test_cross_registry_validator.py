from __future__ import annotations

import shutil
from pathlib import Path
from typing import Any

import yaml
from typer.testing import CliRunner

from tokenbank.cli.main import app
from tokenbank.config_runtime.validator import validate_config_dir

REPO_ROOT = Path(__file__).resolve().parents[2]


def _copy_config(tmp_path: Path) -> Path:
    target = tmp_path / "config"
    shutil.copytree(REPO_ROOT / "config", target)
    return target


def _read_yaml(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as handle:
        return yaml.safe_load(handle)


def _write_yaml(path: Path, payload: dict[str, Any]) -> None:
    with path.open("w", encoding="utf-8") as handle:
        yaml.safe_dump(payload, handle, sort_keys=False)


def _issue_codes(config_dir: Path) -> set[str]:
    return {issue.code for issue in validate_config_dir(config_dir).issues}


def test_default_config_validates() -> None:
    result = validate_config_dir(REPO_ROOT / "config")

    assert result.ok
    assert result.content_hashes


def test_config_validate_cli_passes() -> None:
    result = CliRunner().invoke(app, ["config", "validate"])

    assert result.exit_code == 0
    assert "Config valid" in result.output


def test_routebook_backend_classes_exist(tmp_path: Path) -> None:
    config_dir = _copy_config(tmp_path)
    runtime_path = config_dir / "runtime.yaml"
    runtime = _read_yaml(runtime_path)
    runtime["routebook"]["backend_classes"].append("unregistered_backend_class")
    _write_yaml(runtime_path, runtime)

    assert "routebook.backend_class_missing" in _issue_codes(config_dir)


def test_routebook_verifier_recipe_exists(tmp_path: Path) -> None:
    config_dir = _copy_config(tmp_path)
    runtime_path = config_dir / "runtime.yaml"
    runtime = _read_yaml(runtime_path)
    runtime["routebook"]["candidate_rules"][0]["verifier_recipe_id"] = "missing_v0"
    _write_yaml(runtime_path, runtime)

    assert "routebook.verifier_recipe_missing" in _issue_codes(config_dir)


def test_backend_registry_allowed_by_policy(tmp_path: Path) -> None:
    config_dir = _copy_config(tmp_path)
    backend_registry_path = config_dir / "backend_registry.yaml"
    registry = _read_yaml(backend_registry_path)
    registry["backend_registry"]["backends"][0]["backend_id"] = "backend:unlisted:v0"
    _write_yaml(backend_registry_path, registry)

    assert "backend_policy.backend_id_not_allowed" in _issue_codes(config_dir)


def test_policy_allowed_backend_ids_exist(tmp_path: Path) -> None:
    config_dir = _copy_config(tmp_path)
    backend_policy_path = config_dir / "backend_policy.yaml"
    policy = _read_yaml(backend_policy_path)
    policy["backend_policy"]["allowed_backend_ids"].append("backend:missing:v0")
    _write_yaml(backend_policy_path, policy)

    assert "backend_policy.allowed_backend_missing" in _issue_codes(config_dir)


def test_worker_manifest_backend_ids_exist(tmp_path: Path) -> None:
    config_dir = _copy_config(tmp_path)
    capacity_path = config_dir / "capacity_registry.yaml"
    capacity = _read_yaml(capacity_path)
    capacity["capacity_registry"]["worker_manifests"][0]["backend_ids"].append(
        "backend:missing:v0"
    )
    _write_yaml(capacity_path, capacity)

    assert "worker_manifest.backend_id_missing" in _issue_codes(config_dir)


def test_verifier_recipes_map_to_known_task_types(tmp_path: Path) -> None:
    config_dir = _copy_config(tmp_path)
    runtime_path = config_dir / "runtime.yaml"
    runtime = _read_yaml(runtime_path)
    runtime["verifier_recipes"][0]["task_type"] = "unknown_task"
    _write_yaml(runtime_path, runtime)

    assert "verifier_recipe.task_type_unknown" in _issue_codes(config_dir)


def test_pricing_table_covers_api_backends(tmp_path: Path) -> None:
    config_dir = _copy_config(tmp_path)
    pricing_path = config_dir / "pricing" / "pricing_2026_05_03.yaml"
    pricing = _read_yaml(pricing_path)
    pricing["pricing"]["backend_prices"] = []
    _write_yaml(pricing_path, pricing)

    assert "pricing.api_backend_missing" in _issue_codes(config_dir)


def test_forbidden_backend_classes_do_not_appear_in_routebook(tmp_path: Path) -> None:
    config_dir = _copy_config(tmp_path)
    runtime_path = config_dir / "runtime.yaml"
    runtime = _read_yaml(runtime_path)
    runtime["routebook"]["candidate_rules"][0]["backend_class"] = "account_pool"
    _write_yaml(runtime_path, runtime)

    assert "routebook.forbidden_backend_class" in _issue_codes(config_dir)


def test_capacity_nodes_map_to_worker_backend_manifests(tmp_path: Path) -> None:
    config_dir = _copy_config(tmp_path)
    capacity_path = config_dir / "capacity_registry.yaml"
    capacity = _read_yaml(capacity_path)
    capacity["capacity_registry"]["capacity_nodes"][0]["manifest_hash"] = "drift"
    _write_yaml(capacity_path, capacity)

    assert "capacity_node.worker_manifest_hash_mismatch" in _issue_codes(config_dir)
