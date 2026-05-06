from __future__ import annotations

import shutil
from pathlib import Path

import pytest
import yaml
from fastapi.testclient import TestClient

from tests.integration.test_scheduler_assignment import seed_work_unit
from tokenbank.app.api import create_app
from tokenbank.scheduler.scheduler import Scheduler

REPO_ROOT = Path(__file__).resolve().parents[2]
HOST_HEADERS = {"Authorization": "Bearer tbk_h_testhost"}
WORKER_HEADERS = {"Authorization": "Bearer tbk_w_testworker"}


def _client(tmp_path: Path) -> TestClient:
    app = create_app(
        config_dir=REPO_ROOT / "config",
        db_path=tmp_path / "tokenbank.db",
    )
    return TestClient(app)


def test_daemon_start_validates_config(tmp_path: Path) -> None:
    bad_config = tmp_path / "bad_config"
    shutil.copytree(REPO_ROOT / "config", bad_config)
    runtime_path = bad_config / "runtime.yaml"
    payload = yaml.safe_load(runtime_path.read_text(encoding="utf-8"))
    payload["runtime"]["runtime_mode"] = "invalid_mode"
    runtime_path.write_text(yaml.safe_dump(payload), encoding="utf-8")

    app = create_app(
        config_dir=bad_config,
        db_path=tmp_path / "bad.db",
    )
    with pytest.raises(RuntimeError, match="config validation failed"), TestClient(app):
        pass


def test_health_endpoint_starts_app(tmp_path: Path) -> None:
    with _client(tmp_path) as client:
        response = client.get("/health")

    assert response.status_code == 200
    assert response.json()["status"] == "ok"


def test_capacity_list_endpoint(tmp_path: Path) -> None:
    with _client(tmp_path) as client:
        response = client.get("/v0/capacity/nodes", headers=HOST_HEADERS)

    assert response.status_code == 200
    node_ids = {
        node["capacity_node_id"]
        for node in response.json()["nodes"]
    }
    assert "capnode:tool:url_check:v0" in node_ids


def test_worker_register_creates_capacity_node(tmp_path: Path) -> None:
    with _client(tmp_path) as client:
        register_response = client.post(
            "/v0/workers/register",
            headers=WORKER_HEADERS,
            json={
                "worker_id": "wrk_api_test",
                "identity": "API test worker",
                "capabilities": ["url_check"],
                "allowed_task_types": ["url_check"],
                "allowed_data_labels": ["public_url"],
                "allowed_privacy_levels": ["private"],
                "backend_ids": ["backend:url_check:v0"],
                "backend_classes": ["local_tool"],
                "health_status": "healthy",
            },
        )
        capacity_response = client.get("/v0/capacity/nodes", headers=HOST_HEADERS)

    assert register_response.status_code == 200
    assert register_response.json()["capacity_node_id"] == "capnode:worker:wrk_api_test"
    node_ids = {
        node["capacity_node_id"]
        for node in capacity_response.json()["nodes"]
    }
    assert "capnode:worker:wrk_api_test" in node_ids


def test_endpoint_skeletons_return_not_implemented_after_auth(tmp_path: Path) -> None:
    with _client(tmp_path) as client:
        response = client.post(
            "/v0/host/work-units",
            headers=HOST_HEADERS,
            json={"task_type": "not_yet_supported"},
        )

    assert response.status_code == 200
    assert response.json()["status"] == "not_implemented"


def test_worker_assignment_endpoints_use_scheduler_state_machine(
    tmp_path: Path,
) -> None:
    app = create_app(
        config_dir=REPO_ROOT / "config",
        db_path=tmp_path / "tokenbank.db",
    )
    with TestClient(app) as client:
        seed_work_unit(app.state.db)
        scheduler = Scheduler(app.state.db)
        attempt_id = scheduler.create_attempt(
            work_unit_id="wu_001",
            route_plan_id="rp_001",
            policy_decision_id="pd_001",
        )
        assignment_id = scheduler.create_assignment(
            attempt_id=attempt_id,
            worker_id="wrk_1",
            capacity_node_id="capnode:worker:wrk_1",
            backend_id="backend:url_check:v0",
        )

        next_response = client.get(
            "/v0/workers/wrk_1/assignments/next",
            headers=WORKER_HEADERS,
        )
        accept_response = client.post(
            f"/v0/assignments/{assignment_id}/accept",
            headers=WORKER_HEADERS,
            json={"worker_id": "wrk_1"},
        )
        lease = accept_response.json()
        progress_response = client.post(
            f"/v0/assignments/{assignment_id}/progress",
            headers=WORKER_HEADERS,
            json={
                "worker_id": "wrk_1",
                "lease_token": lease["lease_token"],
                "expected_lease_version": lease["lease_version"],
            },
        )
        result_response = client.post(
            f"/v0/assignments/{assignment_id}/result",
            headers=WORKER_HEADERS,
            json={
                "worker_id": "wrk_1",
                "lease_token": lease["lease_token"],
                "output": {"reachable": True},
            },
        )

    assert next_response.status_code == 200
    assert next_response.json()["assignment"]["assignment_id"] == assignment_id
    assert accept_response.status_code == 200
    assert progress_response.status_code == 200
    assert result_response.status_code == 200
    assert result_response.json()["status"] == "succeeded"
