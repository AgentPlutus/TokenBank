"""Capacity/backend registry validation helpers."""

from __future__ import annotations

from typing import Any

from tokenbank.models.backend import BackendManifest

CONTROL_PLANE_GATEWAY_WORKER_ID = "wrk_control_plane_gateway"
API_GATEWAY_BACKEND_CLASSES = {"api_model_gateway", "primary_model_gateway"}
WORKER_LOCAL_BACKEND_CLASSES = {"browser_fetch", "local_script", "local_tool"}


class CapacityRegistryValidationError(ValueError):
    """Raised when backend and capacity manifests cannot be paired."""


def validate_backend_execution_location(manifest: BackendManifest) -> None:
    if (
        manifest.backend_class in API_GATEWAY_BACKEND_CLASSES
        and manifest.execution_location != "mac_control_plane"
    ):
        raise CapacityRegistryValidationError(
            "API gateway backends must execute on mac_control_plane"
        )
    if (
        manifest.backend_class in WORKER_LOCAL_BACKEND_CLASSES
        and manifest.execution_location not in {"local_machine", "windows_worker"}
    ):
        raise CapacityRegistryValidationError(
            "worker-local backends must execute on local_machine or windows_worker"
        )


def validate_worker_local_backend(
    *,
    worker: Any,
    backend: BackendManifest,
) -> None:
    validate_backend_execution_location(backend)
    if backend.backend_class in API_GATEWAY_BACKEND_CLASSES:
        if worker.worker_id != CONTROL_PLANE_GATEWAY_WORKER_ID:
            raise CapacityRegistryValidationError(
                "worker direct API model path is denied"
            )
        return
    if backend.backend_class not in WORKER_LOCAL_BACKEND_CLASSES:
        raise CapacityRegistryValidationError(
            f"unsupported worker-local backend_class: {backend.backend_class}"
        )
    if backend.backend_id not in worker.backend_ids:
        raise CapacityRegistryValidationError(
            f"worker {worker.worker_id} does not allow backend_id {backend.backend_id}"
        )
    if backend.backend_class not in worker.backend_classes:
        raise CapacityRegistryValidationError(
            "worker manifest does not allow backend_class "
            f"{backend.backend_class}"
        )


def validate_gateway_worker(
    *,
    worker: Any,
    backend: BackendManifest,
) -> None:
    validate_backend_execution_location(backend)
    if worker.worker_id != CONTROL_PLANE_GATEWAY_WORKER_ID:
        raise CapacityRegistryValidationError(
            "API model gateway must resolve to wrk_control_plane_gateway"
        )
    if backend.backend_id not in worker.backend_ids:
        raise CapacityRegistryValidationError(
            "control-plane gateway worker manifest is missing backend_id "
            f"{backend.backend_id}"
        )
    if backend.backend_class not in worker.backend_classes:
        raise CapacityRegistryValidationError(
            "control-plane gateway worker manifest is missing backend_class "
            f"{backend.backend_class}"
        )
