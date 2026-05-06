from __future__ import annotations

import shutil
from pathlib import Path
from typing import Any

import pytest
import yaml

from tokenbank.app.bootstrap import (
    backend_manifests_from_config,
    rebuild_capacity_projection_from_config_and_db,
    worker_manifests_from_config,
)
from tokenbank.backends.resolver import BackendResolutionError, BackendResolver
from tokenbank.capacity.discovery import discover_capacity_nodes
from tokenbank.capacity.registry import list_capacity_nodes, rebuild_capacity_nodes
from tokenbank.config_runtime.loader import load_config_dir
from tokenbank.config_runtime.validator import validate_config_dir
from tokenbank.db.bootstrap import initialize_database

REPO_ROOT = Path(__file__).resolve().parents[2]


def _resolver() -> BackendResolver:
    return BackendResolver.from_config(load_config_dir(REPO_ROOT / "config"))


def _copy_config(tmp_path: Path) -> Path:
    target = tmp_path / "config"
    shutil.copytree(REPO_ROOT / "config", target)
    return target


def _read_yaml(path: Path) -> dict[str, Any]:
    return yaml.safe_load(path.read_text(encoding="utf-8"))


def _write_yaml(path: Path, payload: dict[str, Any]) -> None:
    path.write_text(yaml.safe_dump(payload, sort_keys=False), encoding="utf-8")


def test_resolve_local_tool() -> None:
    resolution = _resolver().resolve(
        {
            "backend_class": "local_tool",
            "task_type": "url_check",
        }
    )

    assert resolution.backend_id == "backend:url_check:v0"
    assert resolution.capacity_node_id == "capnode:worker:wrk_demo_local"
    assert resolution.worker_id == "wrk_demo_local"


def test_resolve_browser_fetch() -> None:
    resolution = _resolver().resolve(
        {
            "backend_class": "browser_fetch",
            "task_type": "url_check",
        }
    )

    assert resolution.backend_id == "backend:browser_fetch:v0"
    assert resolution.capacity_node_id == "capnode:worker:wrk_demo_local"
    assert resolution.worker_id == "wrk_demo_local"


def test_resolve_api_gateway_pseudo_worker() -> None:
    resolution = _resolver().resolve(
        {
            "backend_id": "backend:api_model_gateway:l1_structured",
            "backend_class": "api_model_gateway",
            "task_type": "structured_summary",
        }
    )

    assert resolution.worker_id == "wrk_control_plane_gateway"
    assert resolution.capacity_node_id == "capnode:worker:wrk_control_plane_gateway"
    assert resolution.execution_location == "mac_control_plane"


def test_resolve_primary_gateway_pseudo_worker() -> None:
    resolution = _resolver().resolve(
        {
            "backend_class": "primary_model_gateway",
            "task_type": "structured_summary",
        }
    )

    assert resolution.backend_id == "backend:primary_model_gateway:v0"
    assert resolution.worker_id == "wrk_control_plane_gateway"
    assert resolution.capacity_node_id == "capnode:worker:wrk_control_plane_gateway"


def test_reject_worker_direct_api_model() -> None:
    with pytest.raises(BackendResolutionError, match="worker direct API model"):
        _resolver().resolve(
            {
                "backend_id": "backend:api_model_gateway:l1_structured",
                "backend_class": "api_model_gateway",
                "task_type": "structured_summary",
            },
            worker_id="wrk_demo_local",
        )


def test_reject_unknown_backend_id() -> None:
    with pytest.raises(BackendResolutionError, match="unknown backend_id"):
        _resolver().resolve({"backend_id": "backend:missing:v0"})


def test_reject_unknown_backend_class() -> None:
    with pytest.raises(BackendResolutionError, match="unknown backend_class"):
        _resolver().resolve(
            {
                "backend_class": "missing_class",
                "task_type": "url_check",
            }
        )


def test_reject_backend_policy_mismatch() -> None:
    config = load_config_dir(REPO_ROOT / "config")
    resolver = BackendResolver(
        backend_registry=BackendResolver.from_config(config).backend_registry,
        worker_manifests=worker_manifests_from_config(config),
        allowed_backend_ids={"backend:url_check:v0"},
        allowed_backend_classes={"local_tool"},
    )

    with pytest.raises(BackendResolutionError, match="backend_id is not allowed"):
        resolver.resolve(
            {
                "backend_class": "browser_fetch",
                "task_type": "url_check",
            }
        )


def test_capacity_registry_no_drift(tmp_path: Path) -> None:
    config_dir = _copy_config(tmp_path)

    assert validate_config_dir(config_dir).ok

    capacity_path = config_dir / "capacity_registry.yaml"
    capacity = _read_yaml(capacity_path)
    capacity["capacity_registry"]["capacity_nodes"] = (
        capacity["capacity_registry"]["capacity_nodes"][1:]
    )
    _write_yaml(capacity_path, capacity)

    issue_codes = {
        issue.code
        for issue in validate_config_dir(config_dir).issues
    }
    assert "capacity_node.projection_missing" in issue_codes


def test_capacity_node_rebuild_from_worker_and_backend_manifests(
    tmp_path: Path,
) -> None:
    config = load_config_dir(REPO_ROOT / "config")
    conn = initialize_database(tmp_path / "tokenbank.db")

    nodes = rebuild_capacity_nodes(
        conn,
        worker_manifests=worker_manifests_from_config(config),
        backend_manifests=backend_manifests_from_config(config),
    )

    node_ids = {node.capacity_node_id for node in nodes}
    assert "capnode:worker:wrk_demo_local" in node_ids
    assert "capnode:worker:wrk_control_plane_gateway" in node_ids
    assert "capnode:tool:browser_fetch:v0" in node_ids
    expected_count = len(worker_manifests_from_config(config)) + len(
        backend_manifests_from_config(config)
    )
    assert conn.execute("SELECT COUNT(*) FROM capacity_nodes").fetchone()[0] == (
        expected_count
    )


def test_capacity_health_summary_includes_worker_and_gateway(tmp_path: Path) -> None:
    config = load_config_dir(REPO_ROOT / "config")
    conn = initialize_database(tmp_path / "tokenbank.db")

    rebuild_capacity_projection_from_config_and_db(conn, config)
    discovered = discover_capacity_nodes(conn)
    by_id = {
        node["capacity_node_id"]: node
        for node in discovered
    }

    assert by_id["capnode:worker:wrk_demo_local"]["health"]["status"] == "healthy"
    assert by_id["capnode:worker:wrk_control_plane_gateway"]["health"]["status"] == (
        "healthy"
    )
    assert by_id["capnode:worker:wrk_control_plane_gateway"]["worker_id"] == (
        "wrk_control_plane_gateway"
    )
    expected_count = len(worker_manifests_from_config(config)) + len(
        backend_manifests_from_config(config)
    )
    assert len(list_capacity_nodes(conn)) == expected_count
