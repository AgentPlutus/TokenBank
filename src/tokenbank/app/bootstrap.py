"""Control-plane bootstrap helpers for WP4."""

from __future__ import annotations

import sqlite3
from datetime import UTC, datetime
from typing import Any

from tokenbank.backends.registry import load_backend_manifests
from tokenbank.capacity.registry import WorkerManifest, rebuild_capacity_nodes
from tokenbank.config_runtime.loader import LoadedConfig
from tokenbank.core.canonical import canonical_json_dumps, canonical_json_hash
from tokenbank.models.backend import BackendManifest


def _utc_now_text() -> str:
    return datetime.now(UTC).isoformat().replace("+00:00", "Z")


def backend_manifests_from_config(config: LoadedConfig) -> list[BackendManifest]:
    return load_backend_manifests(config)


def worker_manifests_from_config(config: LoadedConfig) -> list[WorkerManifest]:
    workers = config.documents["capacity_registry"].get("capacity_registry", {}).get(
        "worker_manifests",
        [],
    )
    return [
        WorkerManifest(
            worker_id=worker["worker_id"],
            identity=worker.get("identity", worker["worker_id"]),
            capabilities=worker.get("allowed_task_types", []),
            allowed_task_types=worker.get("allowed_task_types", []),
            allowed_data_labels=worker.get("allowed_data_labels", ["public_url"]),
            allowed_privacy_levels=worker.get("allowed_privacy_levels", ["private"]),
            execution_location=worker.get("execution_location", "windows_worker"),
            trust_level=worker.get("trust_level", "trusted_private"),
            backend_ids=worker.get("backend_ids", []),
            backend_classes=worker.get("backend_classes", ["local_tool"]),
            health_status=worker.get("health_status", "healthy"),
            manifest_hash=worker.get("manifest_hash"),
        )
        for worker in workers
    ]


def stored_worker_manifests(conn: sqlite3.Connection) -> list[WorkerManifest]:
    rows = conn.execute(
        "SELECT body_json FROM worker_manifests ORDER BY worker_id"
    ).fetchall()
    return [
        WorkerManifest.model_validate_json(row["body_json"])
        for row in rows
    ]


def upsert_worker_manifest(
    conn: sqlite3.Connection,
    payload: dict[str, Any],
) -> WorkerManifest:
    manifest_payload = {
        "worker_id": payload["worker_id"],
        "identity": payload.get("identity", payload["worker_id"]),
        "capabilities": payload.get(
            "capabilities",
            payload.get("allowed_task_types", []),
        ),
        "allowed_task_types": payload.get("allowed_task_types", []),
        "allowed_data_labels": payload.get("allowed_data_labels", ["public_url"]),
        "allowed_privacy_levels": payload.get("allowed_privacy_levels", ["private"]),
        "execution_location": payload.get("execution_location", "windows_worker"),
        "trust_level": payload.get("trust_level", "trusted_private"),
        "backend_ids": payload.get("backend_ids", []),
        "backend_classes": payload.get("backend_classes", ["local_tool"]),
        "health_status": payload.get("health_status", "healthy"),
    }
    manifest_hash = canonical_json_hash(manifest_payload)
    manifest = WorkerManifest(
        **manifest_payload,
        manifest_hash=manifest_hash,
    )
    now = _utc_now_text()
    conn.execute(
        """
        INSERT INTO worker_manifests (
          worker_id,
          manifest_hash,
          body_json,
          created_at,
          updated_at
        )
        VALUES (?, ?, ?, ?, ?)
        ON CONFLICT(worker_id) DO UPDATE SET
          manifest_hash = excluded.manifest_hash,
          body_json = excluded.body_json,
          updated_at = excluded.updated_at
        """,
        (
            manifest.worker_id,
            manifest_hash,
            canonical_json_dumps(manifest.model_dump(mode="json")),
            now,
            now,
        ),
    )
    conn.commit()
    return manifest


def rebuild_capacity_projection_from_config_and_db(
    conn: sqlite3.Connection,
    config: LoadedConfig,
) -> int:
    workers_by_id = {
        worker.worker_id: worker
        for worker in worker_manifests_from_config(config)
    }
    for worker in stored_worker_manifests(conn):
        workers_by_id[worker.worker_id] = worker

    nodes = rebuild_capacity_nodes(
        conn,
        worker_manifests=list(workers_by_id.values()),
        backend_manifests=backend_manifests_from_config(config),
    )
    return len(nodes)
