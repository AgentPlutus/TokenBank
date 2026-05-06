from __future__ import annotations

import json
from contextlib import suppress
from pathlib import Path
from typing import Any

from fastapi.testclient import TestClient

from tests.integration.test_scheduler_assignment import seed_work_unit
from tokenbank.app.api import create_app
from tokenbank.scheduler.scheduler import Scheduler
from tokenbank.worker.config import WorkerConfig, load_worker_config
from tokenbank.worker.daemon import WorkerDaemon
from tokenbank.worker.poller import ControlPlaneClient, ControlPlaneRequestError

REPO_ROOT = Path(__file__).resolve().parents[2]
HOST_HEADERS = {"Authorization": "Bearer tbk_h_worker_poll_host"}
WORKER_TOKEN = "tbk_w_worker_poll_runtime"


class FailingSubmitClient(ControlPlaneClient):
    def submit_result(self, **kwargs: Any) -> dict[str, Any]:
        raise ControlPlaneRequestError("submit temporarily unavailable")


def worker_config(tmp_path: Path, *, worker_id: str = "wrk_win_01") -> WorkerConfig:
    return WorkerConfig(
        worker_id=worker_id,
        worker_token=WORKER_TOKEN,
        sandbox_root=tmp_path / "sandbox",
        spool_dir=tmp_path / "spool",
        heartbeat_interval_seconds=0.01,
        poll_interval_seconds=0.01,
    )


def control_client(api_client: TestClient) -> ControlPlaneClient:
    return ControlPlaneClient(
        base_url="http://testserver",
        worker_token=WORKER_TOKEN,
        client=api_client,
    )


def prepare_assignment(
    app_db,
    *,
    worker_id: str = "wrk_win_01",
    url: str = "https://example.com/status",
) -> str:
    if app_db.execute(
        "SELECT 1 FROM work_units WHERE work_unit_id = ?",
        ("wu_001",),
    ).fetchone() is None:
        seed_work_unit(app_db)
    scheduler = Scheduler(app_db)
    attempt_id = scheduler.create_attempt(
        work_unit_id="wu_001",
        route_plan_id="rp_001",
        policy_decision_id="pd_001",
    )
    return scheduler.create_assignment(
        attempt_id=attempt_id,
        worker_id=worker_id,
        capacity_node_id=f"capnode:worker:{worker_id}",
        backend_id="backend:url_check:v0",
        effective_constraints={"input": {"url": url}},
    )


def build_app(tmp_path: Path):
    return create_app(
        config_dir=REPO_ROOT / "config",
        db_path=tmp_path / "tokenbank.db",
    )


def test_worker_register_capacity_node(tmp_path: Path) -> None:
    app = build_app(tmp_path)
    with TestClient(app) as api_client:
        daemon = WorkerDaemon(
            worker_config(tmp_path),
            client=control_client(api_client),
        )

        response = daemon.register()
        daemon.heartbeat_once()
        capacity_response = api_client.get("/v0/capacity/nodes", headers=HOST_HEADERS)
        health_row = app.state.db.execute(
            """
            SELECT worker_id, status
            FROM worker_health_snapshots
            WHERE worker_id = ?
            """,
            ("wrk_win_01",),
        ).fetchone()

    assert response["capacity_node_id"] == "capnode:worker:wrk_win_01"
    node_ids = {node["capacity_node_id"] for node in capacity_response.json()["nodes"]}
    assert "capnode:worker:wrk_win_01" in node_ids
    assert health_row["status"] == "healthy"


def test_worker_poll_own_assignment(tmp_path: Path) -> None:
    app = build_app(tmp_path)
    with TestClient(app) as api_client:
        daemon = WorkerDaemon(
            worker_config(tmp_path),
            client=control_client(api_client),
        )
        daemon.register()
        prepare_assignment(app.state.db, worker_id="wrk_other")
        own_assignment_id = prepare_assignment(app.state.db, worker_id="wrk_win_01")

        assignment = daemon.poll_assignment()

    assert assignment is not None
    assert assignment["assignment_id"] == own_assignment_id
    assert assignment["worker_id"] == "wrk_win_01"


def test_worker_accept_assignment(tmp_path: Path) -> None:
    app = build_app(tmp_path)
    with TestClient(app) as api_client:
        daemon = WorkerDaemon(
            worker_config(tmp_path),
            client=control_client(api_client),
        )
        daemon.register()
        assignment_id = prepare_assignment(app.state.db)
        assignment = daemon.poll_assignment()

        accepted = daemon.client.accept_assignment(
            assignment["assignment_id"],
            daemon.config.worker_id,
        )
        row = app.state.db.execute(
            """
            SELECT status, lease_token_hash, lease_token_prefix
            FROM assignments
            WHERE assignment_id = ?
            """,
            (assignment_id,),
        ).fetchone()

    assert accepted["assignment_id"] == assignment_id
    assert row["status"] == "accepted"
    assert accepted["lease_token"] not in row["lease_token_hash"]
    assert accepted["lease_token"] not in row["lease_token_prefix"]


def test_worker_progress_refresh(tmp_path: Path) -> None:
    app = build_app(tmp_path)
    with TestClient(app) as api_client:
        daemon = WorkerDaemon(
            worker_config(tmp_path),
            client=control_client(api_client),
        )
        daemon.register()
        assignment_id = prepare_assignment(app.state.db)
        assignment = daemon.poll_assignment()

        daemon.handle_assignment(assignment)
        row = app.state.db.execute(
            "SELECT lease_version, status FROM assignments WHERE assignment_id = ?",
            (assignment_id,),
        ).fetchone()
        event_types = {
            row["type"]
            for row in app.state.db.execute("SELECT type FROM event_outbox").fetchall()
        }

    assert row["lease_version"] == 2
    assert row["status"] == "completed"
    assert "assignment.progress" in event_types


def test_worker_submit_result_with_hashes(tmp_path: Path) -> None:
    app = build_app(tmp_path)
    with TestClient(app) as api_client:
        daemon = WorkerDaemon(
            worker_config(tmp_path),
            client=control_client(api_client),
        )
        daemon.register()
        assignment_id = prepare_assignment(app.state.db)
        assignment = daemon.poll_assignment()

        result = daemon.handle_assignment(assignment)
        row = app.state.db.execute(
            """
            SELECT output_hash, result_hash, body_json
            FROM result_envelopes
            WHERE assignment_id = ?
            """,
            (assignment_id,),
        ).fetchone()

    assert result["status"] == "succeeded"
    assert result["output_hash"] == row["output_hash"]
    assert result["result_hash"] == row["result_hash"]
    assert json.loads(row["body_json"])["output"]["local_tool_stub"] is True


def test_worker_spools_result_on_submit_failure(tmp_path: Path) -> None:
    app = build_app(tmp_path)
    with TestClient(app) as api_client:
        config = worker_config(tmp_path)
        daemon = WorkerDaemon(
            config,
            client=FailingSubmitClient(
                base_url="http://testserver",
                worker_token=WORKER_TOKEN,
                client=api_client,
            ),
        )
        daemon.register()
        assignment_id = prepare_assignment(app.state.db)
        assignment = daemon.poll_assignment()

        with suppress(ControlPlaneRequestError):
            daemon.handle_assignment(assignment)
        spool_files = sorted(config.spool_dir.glob("*.json"))
        spool_text = spool_files[0].read_text(encoding="utf-8")

    assert len(spool_files) == 1
    assert assignment_id in spool_text
    assert "lease_token_hash" in spool_text
    assert '"lease_token":' not in spool_text
    assert "tbk_l_" not in spool_text


def test_worker_restart_completed_spool_submit(tmp_path: Path) -> None:
    app = build_app(tmp_path)
    with TestClient(app) as api_client:
        config = worker_config(tmp_path)
        failing_daemon = WorkerDaemon(
            config,
            client=FailingSubmitClient(
                base_url="http://testserver",
                worker_token=WORKER_TOKEN,
                client=api_client,
            ),
        )
        failing_daemon.register()
        assignment_id = prepare_assignment(app.state.db)
        assignment = failing_daemon.poll_assignment()
        with suppress(ControlPlaneRequestError):
            failing_daemon.handle_assignment(assignment)

        restarted = WorkerDaemon(config, client=control_client(api_client))
        submitted = restarted.replay_completed_spool()
        result_row = app.state.db.execute(
            "SELECT status FROM result_envelopes WHERE assignment_id = ?",
            (assignment_id,),
        ).fetchone()

    assert submitted == 1
    assert result_row["status"] == "succeeded"
    assert list(config.spool_dir.glob("*.json")) == []


def test_worker_sandbox_paths_created(tmp_path: Path) -> None:
    config = worker_config(tmp_path)
    daemon = WorkerDaemon(config, client=object())  # type: ignore[arg-type]

    sandbox = daemon.sandbox.create_assignment("asg_sandbox")

    assert sandbox.input_dir.is_dir()
    assert sandbox.output_dir.is_dir()
    assert sandbox.tmp_dir.is_dir()
    assert sandbox.log_dir.is_dir()


def test_worker_config_example_loads() -> None:
    config = load_worker_config(
        REPO_ROOT / "examples/private_capacity_demo/workers/wrk_win_01.yaml"
    )

    assert config.worker_id == "wrk_win_01"
    assert config.backend_classes == ["local_tool"]
