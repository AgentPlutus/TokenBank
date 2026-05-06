from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from fastapi.testclient import TestClient
from typer.testing import CliRunner

from tokenbank.app.api import create_app
from tokenbank.cli.main import app as cli_app
from tokenbank.worker.config import WorkerConfig
from tokenbank.worker.daemon import WorkerDaemon
from tokenbank.worker.poller import ControlPlaneClient

REPO_ROOT = Path(__file__).resolve().parents[2]
HOST_HEADERS = {"Authorization": "Bearer tbk_h_vs1a_host"}
WORKER_TOKEN = "tbk_w_vs1a_worker"


def worker_config(tmp_path: Path) -> WorkerConfig:
    return WorkerConfig(
        worker_id="wrk_demo_local",
        worker_token=WORKER_TOKEN,
        capabilities=["url_check", "dedup"],
        backend_ids=["backend:url_check:v0", "backend:dedup:local_script:v0"],
        backend_classes=["local_tool", "local_script"],
        allowed_task_types=["url_check", "dedup"],
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


def event_types(app_db) -> set[str]:
    return {
        row["type"]
        for row in app_db.execute("SELECT type FROM event_outbox").fetchall()
    }


def test_vs1a_dedup_end_to_end(tmp_path: Path) -> None:
    db_path = tmp_path / "tokenbank.db"
    runner = CliRunner()

    submit_result = runner.invoke(
        cli_app,
        [
            "host",
            "dedup",
            json.dumps(["alpha", "beta", "alpha", {"id": 1}, {"id": 1}]),
            "--config-dir",
            str(REPO_ROOT / "config"),
            "--db-path",
            str(db_path),
        ],
    )

    assert submit_result.exit_code == 0, submit_result.output
    submission = json.loads(submit_result.output)
    assert submission["work_unit_id"].startswith("wu_vs1a_")
    assert submission["route_plan_id"]
    assert submission["policy_decision_id"]
    assert submission["assignment_id"]
    assert submission["worker_id"] == "wrk_demo_local"
    assert submission["backend_class"] == "local_script"
    assert submission["backend_id"] == "backend:dedup:local_script:v0"
    assert submission["verifier_recipe_id"] == "dedup_v0"

    app = create_app(
        config_dir=REPO_ROOT / "config",
        db_path=db_path,
    )
    with TestClient(app) as api_client:
        daemon = WorkerDaemon(
            worker_config(tmp_path),
            client=control_client(api_client),
        )
        daemon.register()
        worker_result = daemon.run_once()
        summary_response = api_client.get(
            f"/v0/host/work-units/{submission['work_unit_id']}/result",
            headers=HOST_HEADERS,
        )
        stored_result = app.state.db.execute(
            """
            SELECT output_hash, result_hash, body_json
            FROM result_envelopes
            WHERE work_unit_id = ?
            """,
            (submission["work_unit_id"],),
        ).fetchone()
        verifier_row = app.state.db.execute(
            """
            SELECT recommendation, body_json
            FROM verifier_reports
            WHERE work_unit_id = ?
            """,
            (submission["work_unit_id"],),
        ).fetchone()
        events = event_types(app.state.db)

    assert worker_result["status"] == "completed"
    api_result: dict[str, Any] = worker_result["result"]
    assert api_result["status"] == "succeeded"
    assert api_result["output_hash"]
    assert api_result["result_hash"]
    assert api_result["verifier_report"]["verifier_recipe_id"] == "dedup_v0"
    assert api_result["verifier_report"]["recommendation"] in {
        "accept",
        "accept_with_warning",
    }

    assert summary_response.status_code == 200
    summary = summary_response.json()["host_result_summary"]
    assert summary["status"] == "succeeded"
    assert summary["task_type"] == "dedup"
    assert summary["backend_class"] == "local_script"
    assert summary["worker_id"] == "wrk_demo_local"
    assert summary["verifier_recommendation"] in {"accept", "accept_with_warning"}

    assert stored_result["output_hash"] == api_result["output_hash"]
    assert stored_result["result_hash"] == api_result["result_hash"]
    result_body = json.loads(stored_result["body_json"])
    assert result_body["output"]["unique_items"] == ["alpha", "beta", {"id": 1}]
    assert result_body["output"]["duplicate_count"] == 2
    assert result_body["output_hash"]
    assert result_body["result_hash"]
    assert verifier_row["recommendation"] in {"accept", "accept_with_warning"}
    verifier_body = json.loads(verifier_row["body_json"])
    assert verifier_body["verifier_recipe_id"] == "dedup_v0"

    required_events = {
        "work_unit.created",
        "route_plan.created",
        "policy_decision.created",
        "attempt.created",
        "assignment.created",
        "assignment.accepted",
        "assignment.progress",
        "result.submitted",
        "verifier_report.created",
        "host_result_summary.created",
    }
    assert required_events.issubset(events)
