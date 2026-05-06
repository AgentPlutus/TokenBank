from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from fastapi.testclient import TestClient
from typer.testing import CliRunner

from tokenbank.app.api import create_app
from tokenbank.capacity.validators import CONTROL_PLANE_GATEWAY_WORKER_ID
from tokenbank.cli.main import app as cli_app
from tokenbank.host import execute_control_plane_gateway_assignment_once

REPO_ROOT = Path(__file__).resolve().parents[2]
HOST_HEADERS = {"Authorization": "Bearer tbk_h_vs1c_host"}
ALLOWED_LABELS = ["engineering", "science", "finance", "policy", "general"]


def event_types(app_db) -> set[str]:
    return {
        row["type"]
        for row in app_db.execute("SELECT type FROM event_outbox").fetchall()
    }


def test_vs1c_topic_classification_end_to_end(tmp_path: Path) -> None:
    db_path = tmp_path / "tokenbank.db"
    runner = CliRunner()

    submit_result = runner.invoke(
        cli_app,
        [
            "host",
            "topic-classify",
            "The API worker stores software cost evidence for research review.",
            "--allowed-labels-json",
            json.dumps(ALLOWED_LABELS),
            "--config-dir",
            str(REPO_ROOT / "config"),
            "--db-path",
            str(db_path),
        ],
    )

    assert submit_result.exit_code == 0, submit_result.output
    submission = json.loads(submit_result.output)
    assert submission["work_unit_id"].startswith("wu_vs1c_")
    assert submission["route_plan_id"]
    assert submission["policy_decision_id"]
    assert submission["assignment_id"]
    assert submission["worker_id"] == CONTROL_PLANE_GATEWAY_WORKER_ID
    assert submission["capacity_node_id"] == (
        f"capnode:worker:{CONTROL_PLANE_GATEWAY_WORKER_ID}"
    )
    assert submission["backend_class"] == "api_model_gateway"
    assert submission["backend_id"] == "backend:topic_classification:api_gateway:v0"
    assert submission["verifier_recipe_id"] == "topic_classification_v0"

    app = create_app(
        config_dir=REPO_ROOT / "config",
        db_path=db_path,
    )
    with TestClient(app) as api_client:
        gateway_result = execute_control_plane_gateway_assignment_once(
            app.state.db,
            assignment_id=submission["assignment_id"],
        )
        summary_response = api_client.get(
            f"/v0/host/work-units/{submission['work_unit_id']}/result",
            headers=HOST_HEADERS,
        )
        capacity_response = api_client.get("/v0/capacity/nodes", headers=HOST_HEADERS)
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
        route_row = app.state.db.execute(
            """
            SELECT body_json
            FROM route_plans
            WHERE work_unit_id = ?
            """,
            (submission["work_unit_id"],),
        ).fetchone()
        events = event_types(app.state.db)

    assert gateway_result is not None
    assert gateway_result["status"] == "completed"
    assert gateway_result["worker_id"] == CONTROL_PLANE_GATEWAY_WORKER_ID
    api_result: dict[str, Any] = gateway_result["result"]
    assert api_result["status"] == "succeeded"
    assert api_result["output_hash"]
    assert api_result["result_hash"]
    assert api_result["verifier_report"]["verifier_recipe_id"] == (
        "topic_classification_v0"
    )
    assert api_result["verifier_report"]["recommendation"] in {
        "accept",
        "accept_with_warning",
    }

    assert summary_response.status_code == 200
    summary = summary_response.json()["host_result_summary"]
    assert summary["status"] == "succeeded"
    assert summary["task_type"] == "topic_classification"
    assert summary["task_level"] == "L1"
    assert summary["backend_class"] == "api_model_gateway"
    assert summary["worker_id"] == CONTROL_PLANE_GATEWAY_WORKER_ID
    assert summary["verifier_recommendation"] in {"accept", "accept_with_warning"}

    assert stored_result["output_hash"] == api_result["output_hash"]
    assert stored_result["result_hash"] == api_result["result_hash"]
    result_body = json.loads(stored_result["body_json"])
    output = result_body["output"]
    assert output["ok"] is True
    assert output["label"] in ALLOWED_LABELS
    assert isinstance(output["confidence"], int | float)
    assert not isinstance(output["confidence"], bool)
    assert 0 <= output["confidence"] <= 1
    assert output["provider_call_executed"] is False
    assert output["control_plane_only"] is True
    assert output["deterministic_stub"] is True
    assert result_body["output_hash"]
    assert result_body["result_hash"]

    assert verifier_row["recommendation"] in {"accept", "accept_with_warning"}
    verifier_body = json.loads(verifier_row["body_json"])
    assert verifier_body["verifier_recipe_id"] == "topic_classification_v0"

    route_body = json.loads(route_row["body_json"])
    assert route_body["task_level"] == "L1"
    assert route_body["verifier_recipe_id"] == "topic_classification_v0"
    assert route_body["candidates"][0]["worker_selector"]["worker_id"] == (
        CONTROL_PLANE_GATEWAY_WORKER_ID
    )

    assert capacity_response.status_code == 200
    capacity_node_ids = {
        node["capacity_node_id"]
        for node in capacity_response.json()["nodes"]
    }
    assert f"capnode:worker:{CONTROL_PLANE_GATEWAY_WORKER_ID}" in capacity_node_ids

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
