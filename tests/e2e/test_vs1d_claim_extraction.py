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
HOST_HEADERS = {"Authorization": "Bearer tbk_h_vs1d_host"}
SOURCE_ID = "src_vs1d_claim_1"
ALLOWED_CLAIM_TYPES = ["factual", "metric", "policy", "product", "other"]


def event_types(app_db) -> set[str]:
    return {
        row["type"]
        for row in app_db.execute("SELECT type FROM event_outbox").fetchall()
    }


def test_vs1d_claim_extraction_end_to_end(tmp_path: Path) -> None:
    db_path = tmp_path / "tokenbank.db"
    runner = CliRunner()

    submit_result = runner.invoke(
        cli_app,
        [
            "host",
            "claim-extract",
            "TokenBank routes private capacity through a control-plane gateway.",
            "--source-id",
            SOURCE_ID,
            "--entity",
            "TokenBank",
            "--allowed-claim-types-json",
            json.dumps(ALLOWED_CLAIM_TYPES),
            "--config-dir",
            str(REPO_ROOT / "config"),
            "--db-path",
            str(db_path),
        ],
    )

    assert submit_result.exit_code == 0, submit_result.output
    submission = json.loads(submit_result.output)
    assert submission["work_unit_id"].startswith("wu_vs1d_")
    assert submission["route_plan_id"]
    assert submission["policy_decision_id"]
    assert submission["assignment_id"]
    assert submission["worker_id"] == CONTROL_PLANE_GATEWAY_WORKER_ID
    assert submission["capacity_node_id"] == (
        f"capnode:worker:{CONTROL_PLANE_GATEWAY_WORKER_ID}"
    )
    assert submission["backend_class"] == "api_model_gateway"
    assert submission["backend_id"] == "backend:claim_extraction:api_gateway:v0"
    assert submission["verifier_recipe_id"] == "claim_extraction_v0"

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
        policy_row = app.state.db.execute(
            """
            SELECT decision
            FROM policy_decisions
            WHERE policy_decision_id = ?
            """,
            (submission["policy_decision_id"],),
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
        "claim_extraction_v0"
    )
    assert api_result["verifier_report"]["recommendation"] in {
        "accept",
        "accept_with_warning",
    }

    assert policy_row["decision"] == "approved"

    assert summary_response.status_code == 200
    summary = summary_response.json()["host_result_summary"]
    assert summary["status"] == "succeeded"
    assert summary["task_type"] == "claim_extraction"
    assert summary["task_level"] == "L2"
    assert summary["backend_class"] == "api_model_gateway"
    assert summary["worker_id"] == CONTROL_PLANE_GATEWAY_WORKER_ID
    assert summary["verifier_recommendation"] in {"accept", "accept_with_warning"}

    assert stored_result["output_hash"] == api_result["output_hash"]
    assert stored_result["result_hash"] == api_result["result_hash"]
    result_body = json.loads(stored_result["body_json"])
    output = result_body["output"]
    assert output["ok"] is True
    assert output["provider_call_executed"] is False
    assert output["control_plane_only"] is True
    assert output["deterministic_stub"] is True
    assert output["source_ids"] == [SOURCE_ID]
    claims = output["claims"]
    assert len(claims) == 1
    claim = claims[0]
    assert claim["claim_text"]
    assert claim["entity"] == "TokenBank"
    assert claim["claim_type"] in ALLOWED_CLAIM_TYPES
    assert isinstance(claim["confidence"], int | float)
    assert not isinstance(claim["confidence"], bool)
    assert 0 <= claim["confidence"] <= 1
    assert claim["source_post_refs"] == [SOURCE_ID]
    assert claim["evidence_hint"]
    assert result_body["output_hash"]
    assert result_body["result_hash"]

    assert verifier_row["recommendation"] in {"accept", "accept_with_warning"}
    verifier_body = json.loads(verifier_row["body_json"])
    assert verifier_body["verifier_recipe_id"] == "claim_extraction_v0"

    route_body = json.loads(route_row["body_json"])
    assert route_body["task_level"] == "L2"
    assert route_body["verifier_recipe_id"] == "claim_extraction_v0"
    backend_ids = [candidate["backend_id"] for candidate in route_body["candidates"]]
    assert backend_ids == [
        "backend:claim_extraction:api_gateway:v0",
        "backend:claim_extraction:primary_gateway:v0",
    ]
    assert route_body["candidates"][0]["worker_selector"]["worker_id"] == (
        CONTROL_PLANE_GATEWAY_WORKER_ID
    )

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
