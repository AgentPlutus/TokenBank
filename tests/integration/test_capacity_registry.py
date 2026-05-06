from __future__ import annotations

from pathlib import Path

from tokenbank.capacity.discovery import discover_capacity_nodes
from tokenbank.capacity.registry import list_capacity_nodes, rebuild_capacity_nodes
from tokenbank.core.canonical import canonical_json_hash
from tokenbank.db.bootstrap import initialize_database


def _worker_manifest() -> dict:
    return {
        "schema_version": "p0.v1",
        "worker_id": "wrk_win_01",
        "identity": "Windows worker 01",
        "capabilities": ["url_check"],
        "allowed_task_types": ["url_check"],
        "allowed_data_labels": ["public_url"],
        "allowed_privacy_levels": ["private"],
        "execution_location": "windows_worker",
        "trust_level": "trusted_private",
        "backend_ids": ["backend:url_check:v0"],
        "backend_classes": ["local_tool"],
        "health_status": "healthy",
        "manifest_hash": "worker_manifest_hash",
        "created_at": "2026-05-04T00:00:00Z",
        "updated_at": "2026-05-04T00:00:00Z",
    }


def _backend_manifest() -> dict:
    return {
        "schema_version": "p0.v1",
        "backend_id": "backend:url_check:v0",
        "backend_class": "local_tool",
        "capacity_node_id": "capnode:tool:url_check:v0",
        "display_name": "URL Check Tool",
        "version": "v0",
        "supported_task_types": ["url_check"],
        "allowed_privacy_levels": ["private"],
        "execution_location": "local_machine",
        "manifest_hash": canonical_json_hash({"backend": "url_check", "version": "v0"}),
        "health": {
            "schema_version": "p0.v1",
            "backend_id": "backend:url_check:v0",
            "status": "healthy",
            "checked_at": "2026-05-04T00:00:00Z",
            "latency_ms": 10,
            "message": None,
        },
        "cost_model": {
            "schema_version": "p0.v1",
            "unit": "work_unit",
            "estimated_cost_micros": 0,
            "cost_source": "policy_default",
        },
        "policy_constraints": {"allowed_domains": ["example.com"]},
    }


def test_capacity_nodes_rebuild_from_worker_and_backend_manifests(
    tmp_path: Path,
) -> None:
    conn = initialize_database(tmp_path / "tokenbank.db")

    nodes = rebuild_capacity_nodes(
        conn,
        worker_manifests=[_worker_manifest()],
        backend_manifests=[_backend_manifest()],
    )

    assert {node.capacity_node_id for node in nodes} == {
        "capnode:worker:wrk_win_01",
        "capnode:tool:url_check:v0",
    }
    assert conn.execute("SELECT COUNT(*) FROM capacity_nodes").fetchone()[0] == 2
    health_count = conn.execute(
        "SELECT COUNT(*) FROM capacity_node_health_snapshots"
    ).fetchone()[0]
    assert health_count == 2


def test_capacity_nodes_are_projection_and_rebuild_removes_stale_nodes(
    tmp_path: Path,
) -> None:
    conn = initialize_database(tmp_path / "tokenbank.db")
    rebuild_capacity_nodes(
        conn,
        worker_manifests=[_worker_manifest()],
        backend_manifests=[_backend_manifest()],
    )

    rebuild_capacity_nodes(
        conn,
        worker_manifests=[_worker_manifest()],
        backend_manifests=[],
    )

    nodes = list_capacity_nodes(conn)
    assert [node.capacity_node_id for node in nodes] == ["capnode:worker:wrk_win_01"]


def test_capacity_discovery_returns_host_safe_projection(tmp_path: Path) -> None:
    conn = initialize_database(tmp_path / "tokenbank.db")
    rebuild_capacity_nodes(
        conn,
        worker_manifests=[_worker_manifest()],
        backend_manifests=[_backend_manifest()],
    )

    discovery = discover_capacity_nodes(conn)

    backend_node = next(node for node in discovery if node["backend_id"] is not None)
    assert backend_node["status"] == "healthy"
    assert backend_node["task_types"] == ["url_check"]
    assert backend_node["backend_classes"] == ["local_tool"]
    assert "body_json" not in backend_node
