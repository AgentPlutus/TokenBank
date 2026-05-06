from __future__ import annotations

from pathlib import Path

import pytest

from tokenbank.backends.registry import (
    BackendRegistry,
    BackendRegistryRepository,
    load_backend_manifests,
)
from tokenbank.capacity.validators import (
    CapacityRegistryValidationError,
    validate_backend_execution_location,
)
from tokenbank.config_runtime.loader import load_config_dir
from tokenbank.db.bootstrap import initialize_database

REPO_ROOT = Path(__file__).resolve().parents[2]


def test_backend_manifest_loader_reads_static_registry() -> None:
    config = load_config_dir(REPO_ROOT / "config")
    manifests = load_backend_manifests(config)

    by_id = {
        manifest.backend_id: manifest
        for manifest in manifests
    }
    assert {
        "backend:api_model_gateway:l1_structured",
        "backend:browser_fetch:v0",
        "backend:claim_extraction:api_gateway:v0",
        "backend:claim_extraction:primary_gateway:v0",
        "backend:dedup:local_script:v0",
        "backend:primary_model_gateway:v0",
        "backend:topic_classification:api_gateway:v0",
        "backend:url_check:v0",
        "backend:webpage_extraction:browser_fetch:v0",
    }.issubset(set(by_id))
    assert by_id["backend:browser_fetch:v0"].backend_class == "browser_fetch"
    assert by_id["backend:primary_model_gateway:v0"].execution_location == (
        "mac_control_plane"
    )


def test_backend_registry_repository_round_trips_manifests(tmp_path: Path) -> None:
    config = load_config_dir(REPO_ROOT / "config")
    manifests = load_backend_manifests(config)
    conn = initialize_database(tmp_path / "tokenbank.db")
    repository = BackendRegistryRepository(conn)

    repository.upsert_manifests(manifests)
    loaded = repository.list_manifests()

    assert [manifest.backend_id for manifest in loaded] == sorted(
        manifest.backend_id for manifest in manifests
    )
    assert conn.execute("SELECT COUNT(*) FROM backend_registry").fetchone()[0] == len(
        manifests
    )


def test_backend_registry_resolves_by_class_and_task_type() -> None:
    config = load_config_dir(REPO_ROOT / "config")
    registry = BackendRegistry.from_config(config)

    backend = registry.resolve_by_class(
        backend_class="browser_fetch",
        task_type="url_check",
    )

    assert backend.backend_id == "backend:browser_fetch:v0"


def test_backend_execution_location_validation_rejects_api_worker_location() -> None:
    config = load_config_dir(REPO_ROOT / "config")
    manifest = BackendRegistry.from_config(config).get(
        "backend:api_model_gateway:l1_structured"
    )
    bad_manifest = manifest.model_copy(update={"execution_location": "windows_worker"})

    with pytest.raises(CapacityRegistryValidationError):
        validate_backend_execution_location(bad_manifest)
