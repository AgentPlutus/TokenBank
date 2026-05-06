"""Backend manifest loading and repository helpers."""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from tokenbank.config_runtime.loader import LoadedConfig, load_config_dir
from tokenbank.core.canonical import canonical_json_dumps
from tokenbank.db.transactions import transaction
from tokenbank.models.backend import BackendHealth, BackendManifest
from tokenbank.models.common import CostModel


def _utc_now_text() -> str:
    return datetime.now(UTC).isoformat().replace("+00:00", "Z")


def backend_manifest_from_config(payload: dict[str, Any]) -> BackendManifest:
    backend_id = str(payload["backend_id"])
    cost_model = payload.get("cost_model", {})
    health_payload = payload.get("health", {})
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
            status=health_payload.get(
                "status",
                payload.get("health_status", "healthy"),
            ),
            latency_ms=health_payload.get("latency_ms"),
            message=health_payload.get("message"),
        ),
        cost_model=CostModel(
            estimated_cost_micros=int(cost_model.get("estimated_cost_micros", 0)),
            cost_source=cost_model.get("cost_source", "policy_default"),
        ),
        policy_constraints=payload.get("policy_constraints", {}),
    )


def load_backend_manifests(config: LoadedConfig) -> list[BackendManifest]:
    backends = config.documents["backend_registry"].get("backend_registry", {}).get(
        "backends",
        [],
    )
    return [backend_manifest_from_config(backend) for backend in backends]


def load_backend_manifests_from_config_dir(
    config_dir: str = "config",
) -> list[BackendManifest]:
    return load_backend_manifests(load_config_dir(config_dir))


@dataclass(frozen=True)
class BackendRegistry:
    manifests: tuple[BackendManifest, ...]

    @classmethod
    def from_config(cls, config: LoadedConfig) -> BackendRegistry:
        return cls(tuple(load_backend_manifests(config)))

    @classmethod
    def from_manifests(
        cls,
        manifests: list[BackendManifest] | tuple[BackendManifest, ...],
    ) -> BackendRegistry:
        return cls(tuple(manifests))

    def get(self, backend_id: str) -> BackendManifest:
        for manifest in self.manifests:
            if manifest.backend_id == backend_id:
                return manifest
        raise KeyError(f"unknown backend_id: {backend_id}")

    def by_class(self, backend_class: str) -> list[BackendManifest]:
        return [
            manifest
            for manifest in self.manifests
            if manifest.backend_class == backend_class
        ]

    def resolve_by_class(
        self,
        *,
        backend_class: str,
        task_type: str | None = None,
    ) -> BackendManifest:
        matches = self.by_class(backend_class)
        if task_type is not None:
            matches = [
                manifest
                for manifest in matches
                if task_type in manifest.supported_task_types
            ]
        if not matches:
            raise KeyError(f"unknown backend_class: {backend_class}")
        return sorted(matches, key=lambda manifest: manifest.backend_id)[0]

    @property
    def backend_ids(self) -> set[str]:
        return {manifest.backend_id for manifest in self.manifests}

    @property
    def backend_classes(self) -> set[str]:
        return {manifest.backend_class for manifest in self.manifests}


class BackendRegistryRepository:
    """SQLite persistence for backend registry manifests."""

    def __init__(self, conn: sqlite3.Connection):
        self.conn = conn

    def upsert_manifests(self, manifests: list[BackendManifest]) -> None:
        now = _utc_now_text()
        with transaction(self.conn):
            for manifest in manifests:
                body_json = canonical_json_dumps(manifest.model_dump(mode="json"))
                self.conn.execute(
                    """
                    INSERT INTO backend_registry (
                      backend_id,
                      backend_class,
                      status,
                      body_json,
                      created_at,
                      updated_at
                    )
                    VALUES (?, ?, ?, ?, ?, ?)
                    ON CONFLICT(backend_id) DO UPDATE SET
                      backend_class = excluded.backend_class,
                      status = excluded.status,
                      body_json = excluded.body_json,
                      updated_at = excluded.updated_at
                    """,
                    (
                        manifest.backend_id,
                        manifest.backend_class,
                        manifest.health.status if manifest.health else "unknown",
                        body_json,
                        now,
                        now,
                    ),
                )
                self.conn.execute(
                    """
                    INSERT INTO backend_manifests (
                      backend_id,
                      backend_class,
                      capacity_node_id,
                      manifest_hash,
                      body_json,
                      created_at,
                      updated_at
                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(backend_id) DO UPDATE SET
                      backend_class = excluded.backend_class,
                      capacity_node_id = excluded.capacity_node_id,
                      manifest_hash = excluded.manifest_hash,
                      body_json = excluded.body_json,
                      updated_at = excluded.updated_at
                    """,
                    (
                        manifest.backend_id,
                        manifest.backend_class,
                        manifest.capacity_node_id,
                        manifest.manifest_hash,
                        body_json,
                        now,
                        now,
                    ),
                )

    def list_manifests(self) -> list[BackendManifest]:
        rows = self.conn.execute(
            "SELECT body_json FROM backend_manifests ORDER BY backend_id"
        ).fetchall()
        return [
            BackendManifest.model_validate_json(row["body_json"])
            for row in rows
        ]
