from __future__ import annotations

import shutil
from pathlib import Path
from typing import Any

import yaml

from tokenbank.routebook.loader import load_routebook_dir
from tokenbank.routebook.validator import P0_TASK_TYPES, validate_routebook
from tokenbank.router.service import RouterService

REPO_ROOT = Path(__file__).resolve().parents[2]


def _service() -> RouterService:
    return RouterService.from_dirs(
        config_dir=REPO_ROOT / "config",
        routebook_dir=REPO_ROOT / "routebook",
    )


def _work_unit(task_type: str) -> dict[str, Any]:
    return {
        "work_unit_id": f"wu_{task_type}",
        "run_id": "run_routebook",
        "task_type": task_type,
        "privacy_level": "private",
        "data_labels": ["public_url"],
        "inline_input": {"url": "https://example.com"},
    }


def _copy_routebook(tmp_path: Path) -> Path:
    target = tmp_path / "routebook"
    shutil.copytree(REPO_ROOT / "routebook", target)
    return target


def _read_yaml(path: Path) -> dict[str, Any]:
    return yaml.safe_load(path.read_text(encoding="utf-8"))


def _write_yaml(path: Path, payload: dict[str, Any]) -> None:
    path.write_text(yaml.safe_dump(payload, sort_keys=False), encoding="utf-8")


def test_routebook_loader_reads_required_files() -> None:
    routebook = load_routebook_dir(REPO_ROOT / "routebook")

    assert set(routebook.content_hashes) == {
        "backend_classes.yaml",
        "fallback_rules.yaml",
        "forbidden_routes.yaml",
        "policy_hints.yaml",
        "task_levels.yaml",
        "task_types.yaml",
        "verifier_mapping.yaml",
    }
    assert {entry["task_type"] for entry in routebook.task_types} == P0_TASK_TYPES


def test_route_url_check_local_tool() -> None:
    route_plan = _service().plan_route(_work_unit("url_check"))

    selected = route_plan.candidates[0]
    assert route_plan.task_level == "L1"
    assert selected.backend_class == "local_tool"
    assert selected.backend_id == "backend:url_check:v0"
    assert selected.worker_selector["worker_id"] == "wrk_demo_local"


def test_route_dedup_local_script() -> None:
    route_plan = _service().plan_route(_work_unit("dedup"))

    selected = route_plan.candidates[0]
    assert selected.backend_class == "local_script"
    assert selected.backend_id == "backend:dedup:local_script:v0"
    assert selected.worker_selector["worker_id"] == "wrk_demo_local"


def test_route_topic_model_gateway() -> None:
    route_plan = _service().plan_route(_work_unit("topic_classification"))

    selected = route_plan.candidates[0]
    assert route_plan.task_level == "L1"
    assert selected.backend_class == "api_model_gateway"
    assert selected.worker_selector["worker_id"] == "wrk_control_plane_gateway"


def test_route_claim_fallback_primary() -> None:
    route_plan = _service().plan_route(_work_unit("claim_extraction"))

    backend_ids = [candidate.backend_id for candidate in route_plan.candidates]
    assert backend_ids == [
        "backend:claim_extraction:api_gateway:v0",
        "backend:claim_extraction:primary_gateway:v0",
    ]
    assert route_plan.candidates[1].backend_class == "primary_model_gateway"
    assert route_plan.candidates[1].worker_selector["worker_id"] == (
        "wrk_control_plane_gateway"
    )


def test_route_webpage_browser_fetch() -> None:
    route_plan = _service().plan_route(_work_unit("webpage_extraction"))

    selected = route_plan.candidates[0]
    assert selected.backend_class == "browser_fetch"
    assert selected.backend_id == "backend:webpage_extraction:browser_fetch:v0"
    assert selected.worker_selector["worker_id"] == "wrk_demo_local"


def test_routebook_backend_classes_exist_in_backend_registry(tmp_path: Path) -> None:
    routebook_dir = _copy_routebook(tmp_path)
    path = routebook_dir / "backend_classes.yaml"
    backend_classes = _read_yaml(path)
    backend_classes["candidate_rules"][0]["backend_class"] = "missing_class"
    _write_yaml(path, backend_classes)

    result = validate_routebook(
        routebook_dir=routebook_dir,
        config_dir=REPO_ROOT / "config",
    )
    assert "routebook.backend_class_unknown" in {
        issue.code
        for issue in result.issues
    }


def test_routebook_verifier_recipes_exist_for_p0_task_types() -> None:
    result = validate_routebook(
        routebook_dir=REPO_ROOT / "routebook",
        config_dir=REPO_ROOT / "config",
    )

    assert result.ok
