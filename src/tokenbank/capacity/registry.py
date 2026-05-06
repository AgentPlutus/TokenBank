"""Capacity node registry projection from manifests."""

from __future__ import annotations

import sqlite3
import uuid
from datetime import UTC, datetime
from typing import Any

from pydantic import Field

from tokenbank.capacity.validators import (
    API_GATEWAY_BACKEND_CLASSES,
    validate_backend_execution_location,
    validate_gateway_worker,
    validate_worker_local_backend,
)
from tokenbank.core.canonical import canonical_json_dumps, canonical_json_hash
from tokenbank.db.transactions import transaction
from tokenbank.models.backend import BackendManifest
from tokenbank.models.base import TokenBankModel, utc_now
from tokenbank.models.capacity_node import (
    CapacityNode,
    CapacityNodeHealth,
    ExecutionLocation,
    TrustLevel,
)
from tokenbank.models.common import (
    BackendClass,
    CostModel,
    HealthStatus,
    NonEmptyStr,
    PrivacyLevel,
)


class WorkerManifest(TokenBankModel):
    worker_id: NonEmptyStr
    identity: NonEmptyStr
    capabilities: list[NonEmptyStr] = Field(default_factory=list)
    allowed_task_types: list[NonEmptyStr] = Field(default_factory=list)
    allowed_data_labels: list[NonEmptyStr] = Field(default_factory=list)
    allowed_privacy_levels: list[PrivacyLevel] = Field(
        default_factory=lambda: ["private"]
    )
    execution_location: ExecutionLocation = "windows_worker"
    trust_level: TrustLevel = "trusted_private"
    backend_ids: list[NonEmptyStr] = Field(default_factory=list)
    backend_classes: list[BackendClass] = Field(default_factory=list)
    health_status: HealthStatus = "unknown"
    manifest_hash: str | None = None
    created_at: datetime = Field(default_factory=utc_now)
    updated_at: datetime = Field(default_factory=utc_now)


def _utc_now_text() -> str:
    return datetime.now(UTC).isoformat().replace("+00:00", "Z")


def _body_json(model: TokenBankModel) -> str:
    return canonical_json_dumps(model.model_dump(mode="json"))


def _manifest_hash(manifest: TokenBankModel, explicit_hash: str | None = None) -> str:
    if explicit_hash:
        return explicit_hash
    return canonical_json_hash(manifest.model_dump(mode="json"))


def project_worker_manifest(
    worker_manifest: WorkerManifest | dict[str, Any],
) -> CapacityNode:
    manifest = (
        worker_manifest
        if isinstance(worker_manifest, WorkerManifest)
        else WorkerManifest.model_validate(worker_manifest)
    )
    manifest_hash = _manifest_hash(manifest, manifest.manifest_hash)
    health = CapacityNodeHealth(
        capacity_node_id=f"capnode:worker:{manifest.worker_id}",
        status=manifest.health_status,
    )
    return CapacityNode(
        capacity_node_id=f"capnode:worker:{manifest.worker_id}",
        node_type="windows_worker",
        identity=manifest.identity,
        capabilities=manifest.capabilities,
        trust_level=manifest.trust_level,
        allowed_task_types=manifest.allowed_task_types,
        allowed_data_labels=manifest.allowed_data_labels,
        allowed_privacy_levels=manifest.allowed_privacy_levels,
        execution_location=manifest.execution_location,
        cost_model=CostModel(),
        health=health,
        policy_constraints={},
        backend_ids=manifest.backend_ids,
        backend_classes=manifest.backend_classes,
        worker_id=manifest.worker_id,
        manifest_hash=manifest_hash,
        created_at=manifest.created_at,
        updated_at=manifest.updated_at,
    )


def project_backend_manifest(
    backend_manifest: BackendManifest | dict[str, Any],
) -> CapacityNode:
    manifest = (
        backend_manifest
        if isinstance(backend_manifest, BackendManifest)
        else BackendManifest.model_validate(backend_manifest)
    )
    status: HealthStatus = "unknown"
    health_checked_at = utc_now()
    if manifest.health is not None:
        status = manifest.health.status
        health_checked_at = manifest.health.checked_at

    health = CapacityNodeHealth(
        capacity_node_id=manifest.capacity_node_id,
        status=status,
        checked_at=health_checked_at,
    )
    return CapacityNode(
        capacity_node_id=manifest.capacity_node_id,
        node_type=manifest.backend_class,
        identity=manifest.display_name,
        capabilities=manifest.supported_task_types,
        trust_level="trusted_private",
        allowed_task_types=manifest.supported_task_types,
        allowed_data_labels=[],
        allowed_privacy_levels=manifest.allowed_privacy_levels,
        execution_location=manifest.execution_location,  # type: ignore[arg-type]
        cost_model=manifest.cost_model,
        health=health,
        policy_constraints=manifest.policy_constraints,
        backend_ids=[manifest.backend_id],
        backend_classes=[manifest.backend_class],
        backend_id=manifest.backend_id,
        manifest_hash=manifest.manifest_hash,
    )


def _upsert_capacity_node(conn: sqlite3.Connection, node: CapacityNode) -> None:
    body_json = _body_json(node)
    health_json = _body_json(node.health)
    conn.execute(
        """
        INSERT INTO capacity_nodes (
          capacity_node_id,
          node_type,
          status,
          worker_id,
          backend_id,
          backend_class,
          execution_location,
          trust_level,
          allowed_task_types_json,
          allowed_privacy_levels_json,
          allowed_data_labels_json,
          backend_ids_json,
          manifest_hash,
          health_summary_json,
          body_json,
          created_at,
          updated_at
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(capacity_node_id) DO UPDATE SET
          node_type = excluded.node_type,
          status = excluded.status,
          worker_id = excluded.worker_id,
          backend_id = excluded.backend_id,
          backend_class = excluded.backend_class,
          execution_location = excluded.execution_location,
          trust_level = excluded.trust_level,
          allowed_task_types_json = excluded.allowed_task_types_json,
          allowed_privacy_levels_json = excluded.allowed_privacy_levels_json,
          allowed_data_labels_json = excluded.allowed_data_labels_json,
          backend_ids_json = excluded.backend_ids_json,
          manifest_hash = excluded.manifest_hash,
          health_summary_json = excluded.health_summary_json,
          body_json = excluded.body_json,
          updated_at = excluded.updated_at
        """,
        (
            node.capacity_node_id,
            node.node_type,
            node.health.status,
            node.worker_id,
            node.backend_ids[0] if len(node.backend_ids) == 1 else None,
            node.backend_classes[0] if len(node.backend_classes) == 1 else None,
            node.execution_location,
            node.trust_level,
            canonical_json_dumps(node.allowed_task_types),
            canonical_json_dumps(node.allowed_privacy_levels),
            canonical_json_dumps(node.allowed_data_labels),
            canonical_json_dumps(node.backend_ids),
            node.manifest_hash,
            health_json,
            body_json,
            node.created_at.isoformat().replace("+00:00", "Z"),
            node.updated_at.isoformat().replace("+00:00", "Z"),
        ),
    )


def _insert_health_snapshot(conn: sqlite3.Connection, node: CapacityNode) -> None:
    body_json = _body_json(node.health)
    conn.execute(
        """
        INSERT INTO capacity_node_health_snapshots (
          snapshot_id,
          capacity_node_id,
          worker_id,
          backend_id,
          status,
          health_json,
          captured_at,
          body_json
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            f"caphealth_{uuid.uuid4().hex}",
            node.capacity_node_id,
            node.worker_id,
            node.backend_ids[0] if len(node.backend_ids) == 1 else None,
            node.health.status,
            body_json,
            _utc_now_text(),
            body_json,
        ),
    )


def rebuild_capacity_nodes(
    conn: sqlite3.Connection,
    worker_manifests: list[WorkerManifest | dict[str, Any]],
    backend_manifests: list[BackendManifest | dict[str, Any]],
) -> list[CapacityNode]:
    """Rebuild capacity_nodes as a projection over worker/backend manifests."""
    workers = [
        manifest
        if isinstance(manifest, WorkerManifest)
        else WorkerManifest.model_validate(manifest)
        for manifest in worker_manifests
    ]
    backends = [
        manifest
        if isinstance(manifest, BackendManifest)
        else BackendManifest.model_validate(manifest)
        for manifest in backend_manifests
    ]
    _validate_registry_pairing(workers, backends)
    nodes = [
        *(project_worker_manifest(manifest) for manifest in workers),
        *(project_backend_manifest(manifest) for manifest in backends),
    ]
    node_ids = {node.capacity_node_id for node in nodes}

    with transaction(conn):
        if node_ids:
            placeholders = ", ".join("?" for _ in node_ids)
            conn.execute(
                f"""
                DELETE FROM capacity_nodes
                WHERE capacity_node_id NOT IN ({placeholders})
                """,
                tuple(sorted(node_ids)),
            )
        else:
            conn.execute("DELETE FROM capacity_nodes")

        for node in nodes:
            _upsert_capacity_node(conn, node)
            _insert_health_snapshot(conn, node)

    return nodes


def _validate_registry_pairing(
    worker_manifests: list[WorkerManifest],
    backend_manifests: list[BackendManifest],
) -> None:
    backends_by_id = {
        backend.backend_id: backend
        for backend in backend_manifests
    }
    for backend in backend_manifests:
        validate_backend_execution_location(backend)
    if not backends_by_id:
        return
    for worker in worker_manifests:
        for backend_id in worker.backend_ids:
            backend = backends_by_id.get(backend_id)
            if backend is None:
                raise ValueError(
                    f"worker {worker.worker_id} references unknown backend_id: "
                    f"{backend_id}"
                )
            if backend.backend_class in API_GATEWAY_BACKEND_CLASSES:
                validate_gateway_worker(worker=worker, backend=backend)
            else:
                validate_worker_local_backend(worker=worker, backend=backend)


def list_capacity_nodes(conn: sqlite3.Connection) -> list[CapacityNode]:
    rows = conn.execute(
        "SELECT body_json FROM capacity_nodes ORDER BY capacity_node_id"
    ).fetchall()
    return [
        CapacityNode.model_validate_json(row["body_json"])
        for row in rows
    ]
