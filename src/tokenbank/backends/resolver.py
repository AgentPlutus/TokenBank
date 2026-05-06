"""Backend intent to capacity-node resolver."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from tokenbank.backends.registry import BackendRegistry
from tokenbank.capacity.registry import WorkerManifest
from tokenbank.capacity.validators import (
    API_GATEWAY_BACKEND_CLASSES,
    CONTROL_PLANE_GATEWAY_WORKER_ID,
    WORKER_LOCAL_BACKEND_CLASSES,
    validate_gateway_worker,
    validate_worker_local_backend,
)
from tokenbank.config_runtime.loader import LoadedConfig
from tokenbank.models.backend import BackendManifest


class BackendResolutionError(ValueError):
    """Raised when backend intent cannot resolve to executable capacity."""


@dataclass(frozen=True)
class BackendResolution:
    backend_id: str
    backend_class: str
    capacity_node_id: str
    worker_id: str | None
    execution_location: str
    supported_task_types: tuple[str, ...]
    manifest_hash: str


class BackendResolver:
    """Map route candidate backend intent to executable capacity metadata."""

    def __init__(
        self,
        *,
        backend_registry: BackendRegistry,
        worker_manifests: list[WorkerManifest],
        allowed_backend_ids: set[str] | None = None,
        allowed_backend_classes: set[str] | None = None,
    ):
        self.backend_registry = backend_registry
        self.workers_by_id = {
            worker.worker_id: worker
            for worker in worker_manifests
        }
        self.allowed_backend_ids = allowed_backend_ids or set()
        self.allowed_backend_classes = allowed_backend_classes or set()

    @classmethod
    def from_config(cls, config: LoadedConfig) -> BackendResolver:
        from tokenbank.app.bootstrap import worker_manifests_from_config

        policy = config.documents["backend_policy"].get("backend_policy", {})
        return cls(
            backend_registry=BackendRegistry.from_config(config),
            worker_manifests=worker_manifests_from_config(config),
            allowed_backend_ids=set(policy.get("allowed_backend_ids", [])),
            allowed_backend_classes=set(policy.get("allowed_backend_classes", [])),
        )

    def resolve(
        self,
        route_candidate: dict[str, Any],
        *,
        worker_id: str | None = None,
    ) -> BackendResolution:
        backend = self._resolve_backend_manifest(route_candidate)
        self._enforce_policy(backend)
        if backend.backend_class in API_GATEWAY_BACKEND_CLASSES:
            if worker_id not in {None, CONTROL_PLANE_GATEWAY_WORKER_ID}:
                raise BackendResolutionError("worker direct API model path is denied")
            return self._resolve_gateway(backend)
        if backend.backend_class in WORKER_LOCAL_BACKEND_CLASSES:
            return self._resolve_worker_local(backend, route_candidate, worker_id)
        raise BackendResolutionError(
            f"unknown backend_class for resolver: {backend.backend_class}"
        )

    def _resolve_backend_manifest(
        self,
        route_candidate: dict[str, Any],
    ) -> BackendManifest:
        backend_id = route_candidate.get("backend_id")
        backend_class = route_candidate.get("backend_class")
        task_type = route_candidate.get("task_type")

        if backend_id:
            try:
                backend = self.backend_registry.get(str(backend_id))
            except KeyError as exc:
                raise BackendResolutionError(str(exc)) from exc
            if backend_class and backend.backend_class != str(backend_class):
                raise BackendResolutionError(
                    "route candidate backend_class does not match backend_id"
                )
            return backend

        if not backend_class:
            raise BackendResolutionError(
                "route candidate must include backend_id or class"
            )

        try:
            return self.backend_registry.resolve_by_class(
                backend_class=str(backend_class),
                task_type=str(task_type) if task_type is not None else None,
            )
        except KeyError as exc:
            raise BackendResolutionError(str(exc)) from exc

    def _resolve_worker_local(
        self,
        backend: BackendManifest,
        route_candidate: dict[str, Any],
        worker_id: str | None,
    ) -> BackendResolution:
        target_worker = worker_id or route_candidate.get("worker_id")
        worker = (
            self._worker(str(target_worker))
            if target_worker
            else self._first_worker_for_backend(backend)
        )
        validate_worker_local_backend(worker=worker, backend=backend)
        return BackendResolution(
            backend_id=backend.backend_id,
            backend_class=backend.backend_class,
            capacity_node_id=f"capnode:worker:{worker.worker_id}",
            worker_id=worker.worker_id,
            execution_location=worker.execution_location,
            supported_task_types=tuple(backend.supported_task_types),
            manifest_hash=backend.manifest_hash,
        )

    def _resolve_gateway(self, backend: BackendManifest) -> BackendResolution:
        worker = self._worker(CONTROL_PLANE_GATEWAY_WORKER_ID)
        validate_gateway_worker(worker=worker, backend=backend)
        return BackendResolution(
            backend_id=backend.backend_id,
            backend_class=backend.backend_class,
            capacity_node_id=f"capnode:worker:{worker.worker_id}",
            worker_id=worker.worker_id,
            execution_location=worker.execution_location,
            supported_task_types=tuple(backend.supported_task_types),
            manifest_hash=backend.manifest_hash,
        )

    def _worker(self, worker_id: str) -> WorkerManifest:
        worker = self.workers_by_id.get(worker_id)
        if worker is None:
            raise BackendResolutionError(f"unknown worker_id: {worker_id}")
        return worker

    def _first_worker_for_backend(self, backend: BackendManifest) -> WorkerManifest:
        for worker in sorted(
            self.workers_by_id.values(),
            key=lambda worker: worker.worker_id,
        ):
            if worker.worker_id == CONTROL_PLANE_GATEWAY_WORKER_ID:
                continue
            if (
                backend.backend_id in worker.backend_ids
                and backend.backend_class in worker.backend_classes
            ):
                return worker
        raise BackendResolutionError(
            f"no worker manifest supports backend_id: {backend.backend_id}"
        )

    def _enforce_policy(self, backend: BackendManifest) -> None:
        if (
            self.allowed_backend_ids
            and backend.backend_id not in self.allowed_backend_ids
        ):
            raise BackendResolutionError(
                f"backend_id is not allowed by backend_policy: {backend.backend_id}"
            )
        if (
            self.allowed_backend_classes
            and backend.backend_class not in self.allowed_backend_classes
        ):
            raise BackendResolutionError(
                "backend_class is not allowed by backend_policy: "
                f"{backend.backend_class}"
            )
