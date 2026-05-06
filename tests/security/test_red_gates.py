from __future__ import annotations

import json
import shutil
from pathlib import Path

import pytest
import yaml

from tests.integration.test_scheduler_assignment import scheduler_fixture
from tokenbank.config_runtime.validator import validate_config_dir
from tokenbank.db.bootstrap import initialize_database
from tokenbank.events.outbox import OutboxEventInput, enqueue_event
from tokenbank.host_adapter import HostAdapterCore, MCPStdioServer
from tokenbank.router.route_plan_validator import RoutePlanValidationError
from tokenbank.router.service import RouterService
from tokenbank.scheduler.lifecycle import update_work_unit_status
from tokenbank.verifier.runner import VerifierRunner
from tokenbank.worker.executor import LocalToolExecutor
from tokenbank.worker.sandbox import WorkerSandbox

REPO_ROOT = Path(__file__).resolve().parents[2]


def test_raw_credential_not_in_event_outbox(tmp_path: Path) -> None:
    conn = initialize_database(tmp_path / "tokenbank.db")
    secret = "sk-redgate-secret"
    token = "tbk_h_redgate_token"

    enqueue_event(
        conn,
        OutboxEventInput(
            source="tokenbank.test",
            type="redgate.secret",
            subject="redgate/secret",
            body={
                "api_key": secret,
                "message": f"Authorization: Bearer {token}",
                "nested": {"oauth_token": token},
            },
        ),
    )
    body_json = conn.execute("SELECT body_json FROM event_outbox").fetchone()[
        "body_json"
    ]

    assert secret not in body_json
    assert token not in body_json
    assert "[REDACTED_SECRET]" in body_json


def test_worker_direct_api_model_call_red_gate(tmp_path: Path) -> None:
    sandbox = WorkerSandbox(tmp_path / "sandbox", "wrk_1").create_assignment("asg_1")

    with pytest.raises(PermissionError):
        LocalToolExecutor().execute(
            assignment={
                "assignment_id": "asg_1",
                "backend_id": "backend:api_model_gateway:l1_structured",
                "backend_class": "api_model_gateway",
            },
            sandbox=sandbox,
        )


def test_l1_l2_route_without_verifier_red_gate() -> None:
    service = RouterService.from_dirs(
        config_dir=REPO_ROOT / "config",
        routebook_dir=REPO_ROOT / "routebook",
    )
    payload = service.plan_route(
        {
            "work_unit_id": "wu_redgate_l1",
            "run_id": "run_redgate_l1",
            "task_type": "dedup",
            "privacy_level": "private",
            "data_labels": ["public_url"],
        }
    ).model_dump(mode="json")
    payload["candidates"][0]["verifier_recipe_id"] = None

    with pytest.raises(RoutePlanValidationError, match="requires verifier"):
        service.validator.validate_payload(payload)


def test_quarantine_auto_fallback_red_gate() -> None:
    from tests.security.test_quarantine_semantics import envelope_for

    envelope = envelope_for(
        task_type="url_check",
        output={"ok": False, "private_ip_denied": True},
    )
    report = VerifierRunner.for_recipe_id("url_check_v0").run(
        result_envelope=envelope
    )

    assert report.recommendation == "quarantine"
    assert report.metadata["quarantine_auto_fallback"] is False


def test_worker_direct_work_unit_update_red_gate(tmp_path: Path) -> None:
    conn, _, _, _ = scheduler_fixture(tmp_path)

    with pytest.raises(PermissionError):
        update_work_unit_status(
            conn,
            work_unit_id="wu_001",
            status="succeeded",
            actor="worker",
        )


def test_accepted_result_lacks_hash_red_gate(tmp_path: Path) -> None:
    conn, scheduler, _, assignment_id = scheduler_fixture(tmp_path)
    accepted = scheduler.accept_assignment(
        assignment_id=assignment_id,
        worker_id="wrk_1",
    )

    result = scheduler.submit_result(
        assignment_id=assignment_id,
        worker_id="wrk_1",
        lease_token=accepted["lease_token"],
        output={"ok": True},
    )
    row = conn.execute(
        """
        SELECT output_hash, result_hash, body_json
        FROM result_envelopes
        WHERE result_envelope_id = ?
        """,
        (result["result_envelope_id"],),
    ).fetchone()
    body = json.loads(row["body_json"])

    assert row["output_hash"]
    assert row["result_hash"]
    assert body["output_hash"]
    assert body["result_hash"]


def test_host_adapter_recursive_workspace_read_red_gate() -> None:
    host_adapter_source = "\n".join(
        path.read_text(encoding="utf-8")
        for path in (REPO_ROOT / "src" / "tokenbank" / "host_adapter").iterdir()
        if path.suffix == ".py"
    )

    assert ".rglob(" not in host_adapter_source
    assert "os.walk(" not in host_adapter_source
    assert "scandir(" not in host_adapter_source


def test_critical_state_transition_event_outbox_red_gate(tmp_path: Path) -> None:
    conn, scheduler, _, assignment_id = scheduler_fixture(tmp_path)
    accepted = scheduler.accept_assignment(
        assignment_id=assignment_id,
        worker_id="wrk_1",
    )
    scheduler.progress_assignment(
        assignment_id=assignment_id,
        worker_id="wrk_1",
        lease_token=accepted["lease_token"],
        expected_lease_version=accepted["lease_version"],
    )

    event_types = {
        row["type"]
        for row in conn.execute("SELECT type FROM event_outbox").fetchall()
    }

    assert {
        "attempt.created",
        "assignment.created",
        "assignment.accepted",
        "assignment.progress",
        "work_unit.assigned",
        "work_unit.running",
    }.issubset(event_types)


def test_capacity_nodes_drift_red_gate(tmp_path: Path) -> None:
    config_dir = tmp_path / "config"
    shutil.copytree(REPO_ROOT / "config", config_dir)
    capacity_path = config_dir / "capacity_registry.yaml"
    capacity = yaml.safe_load(capacity_path.read_text(encoding="utf-8"))
    capacity["capacity_registry"]["capacity_nodes"] = []
    capacity_path.write_text(yaml.safe_dump(capacity), encoding="utf-8")

    issue_codes = {
        issue.code
        for issue in validate_config_dir(config_dir).issues
    }

    assert "capacity_node.projection_missing" in issue_codes


def test_mcp_tool_cap_and_no_proxy_red_gate(tmp_path: Path) -> None:
    server = MCPStdioServer(
        core=HostAdapterCore(
            config_dir=REPO_ROOT / "config",
            db_path=tmp_path / "tokenbank.db",
        )
    )
    tools = server.tool_definitions()
    tool_names = [tool["name"] for tool in tools]

    assert len(tools) == 9
    assert "tokenbank_get_route_explanation" in tool_names
    assert "tokenbank_get_task_analysis" in tool_names
    assert "tokenbank_get_route_score" in tool_names
    assert "chat_completion" not in tool_names
    assert "responses" not in tool_names
    assert all("proxy" not in name for name in tool_names)
