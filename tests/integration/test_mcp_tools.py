from __future__ import annotations

import json
from pathlib import Path

from fastapi.testclient import TestClient

from tokenbank.app.api import create_app
from tokenbank.host_adapter import HostAdapterCore, MCPStdioServer
from tokenbank.worker.config import WorkerConfig
from tokenbank.worker.daemon import WorkerDaemon
from tokenbank.worker.poller import ControlPlaneClient

REPO_ROOT = Path(__file__).resolve().parents[2]
WORKER_TOKEN = "tbk_w_wp12_mcp"


def test_mcp_list_capabilities(tmp_path: Path) -> None:
    server = _server(tmp_path)

    tools = server.tool_definitions()
    capabilities = server.call_tool("tokenbank_list_capabilities", {})

    assert len(tools) == 8
    assert [tool["name"] for tool in tools] == [
        "tokenbank_list_capabilities",
        "tokenbank_estimate",
        "tokenbank_submit",
        "tokenbank_get_result",
        "tokenbank_cancel",
        "tokenbank_get_routebook_excerpt",
        "tokenbank_get_route_explanation",
        "tokenbank_get_task_analysis",
    ]
    assert all("inputSchema" in tool and "outputSchema" in tool for tool in tools)
    assert capabilities["capacity_network"] == "Private Agent Capacity Network"
    assert "url_check" in capabilities["supported_task_types"]
    assert any("model proxy" in item for item in capabilities["when_not_to_use"])
    assert any("credentials" in item for item in capabilities["when_not_to_use"])
    assert any("workspace" in item for item in capabilities["when_not_to_use"])


def test_mcp_submit_url_check_happy_path(tmp_path: Path) -> None:
    server = _server(tmp_path)

    result = server.call_tool(
        "tokenbank_submit",
        {
            "task_type": "url_check",
            "input": {"url": "https://example.com/mcp-submit"},
        },
    )

    assert result["status"] == "submitted"
    assert result["work_unit_id"].startswith("wu_vs0_")
    assert result["assignment_id"]
    assert result["backend_class"] == "local_tool"


def test_mcp_get_result_returns_host_summary(tmp_path: Path) -> None:
    db_path = tmp_path / "tokenbank.db"
    server = _server(tmp_path, db_path=db_path)
    submission = server.call_tool(
        "tokenbank_submit",
        {
            "task_type": "url_check",
            "input": {"url": "https://example.com/mcp-result"},
        },
    )

    app = create_app(config_dir=REPO_ROOT / "config", db_path=db_path)
    with TestClient(app) as api_client:
        daemon = WorkerDaemon(
            _worker_config(tmp_path),
            client=_control_client(api_client),
        )
        daemon.register()
        assert daemon.run_once()["status"] == "completed"

    result = server.call_tool(
        "tokenbank_get_result",
        {"work_unit_id": submission["work_unit_id"]},
    )

    assert result["status"] == "ok"
    summary = result["host_result_summary"]
    assert summary["status"] == "succeeded"
    assert summary["task_type"] == "url_check"
    assert summary["trace_ref"]


def test_mcp_cancel_unknown_or_running_work_unit_behavior(tmp_path: Path) -> None:
    server = _server(tmp_path)

    unknown = server.call_tool(
        "tokenbank_cancel",
        {"work_unit_id": "wu_missing"},
    )
    submission = server.call_tool(
        "tokenbank_submit",
        {
            "task_type": "url_check",
            "input": {"url": "https://example.com/mcp-cancel"},
        },
    )
    running = server.call_tool(
        "tokenbank_cancel",
        {"work_unit_id": submission["work_unit_id"]},
    )

    assert unknown["status"] == "not_found"
    assert running["status"] == "not_implemented"
    assert running["reason"] == "cancel_not_implemented_in_phase0_stub"


def test_mcp_get_routebook_excerpt(tmp_path: Path) -> None:
    server = _server(tmp_path)

    excerpt = server.call_tool(
        "tokenbank_get_routebook_excerpt",
        {"task_type": "url_check"},
    )

    assert excerpt["status"] == "ok"
    assert excerpt["verifier_recipe_id"] == "url_check_v0"
    assert excerpt["candidate_rules"][0]["backend_class"] == "local_tool"


def test_mcp_get_route_explanation(tmp_path: Path) -> None:
    server = _server(tmp_path)

    explanation = server.call_tool(
        "tokenbank_get_route_explanation",
        {
            "task_type": "url_check",
            "input": {"url": "https://example.com/mcp-explain"},
        },
    )

    assert explanation["status"] == "ok"
    assert explanation["task_profile"]["task_type"] == "url_check"
    assert explanation["route_decision_trace"]["selected_candidate_id"] == (
        "route_url_check_local_tool"
    )
    assert explanation["route_plan"]["selected_candidate_id"] == (
        "route_url_check_local_tool"
    )
    assert (
        explanation["route_decision_trace"]["candidate_scores"][0][
            "hard_filter_results"
        ]["worker_direct_api_model_forbidden"]
        == "pass"
    )


def test_mcp_get_task_analysis(tmp_path: Path) -> None:
    server = _server(tmp_path)

    analysis = server.call_tool(
        "tokenbank_get_task_analysis",
        {
            "task_type": "claim_extraction",
            "input": {
                "text": "TokenBank verifies private capacity results.",
                "source_id": "src_mcp_analysis",
            },
        },
    )

    assert analysis["status"] == "ok"
    report = analysis["task_analysis_report"]
    assert report["task_type"] == "claim_extraction"
    assert report["complexity"]["requires_strong_reasoning"] is True
    assert report["token_estimate"]["estimated_total_tokens"] > 0


def test_mcp_does_not_expose_workspace_resources(tmp_path: Path) -> None:
    server = _server(tmp_path)

    response = server.handle_request(
        {"jsonrpc": "2.0", "id": 1, "method": "resources/list", "params": {}}
    )

    assert response is not None
    assert response["error"]["code"] == -32601
    assert all("resource" not in tool["name"] for tool in server.tool_definitions())


def test_mcp_rejects_credentials_or_oauth_input(tmp_path: Path) -> None:
    server = _server(tmp_path)

    response = server.handle_request(
        {
            "jsonrpc": "2.0",
            "id": 2,
            "method": "tools/call",
            "params": {
                "name": "tokenbank_submit",
                "arguments": {
                    "task_type": "url_check",
                    "input": {
                        "url": "https://example.com/mcp-reject",
                        "api_key": "[REDACTED_SECRET]",
                    },
                },
            },
        }
    )

    assert response is not None
    assert response["error"]["code"] == -32000
    assert "credentials" in response["error"]["message"]


def test_mcp_json_rpc_tools_call(tmp_path: Path) -> None:
    server = _server(tmp_path)

    response = server.handle_request(
        {
            "jsonrpc": "2.0",
            "id": 3,
            "method": "tools/call",
            "params": {
                "name": "tokenbank_estimate",
                "arguments": {
                    "task_type": "url_check",
                    "input": {"url": "https://example.com/mcp-estimate"},
                },
            },
        }
    )

    assert response is not None
    structured = response["result"]["structuredContent"]
    assert structured["status"] == "ok"
    assert structured["selected_candidate"]["backend_class"] == "local_tool"
    assert json.loads(response["result"]["content"][0]["text"])["status"] == "ok"


def _server(tmp_path: Path, *, db_path: Path | None = None) -> MCPStdioServer:
    return MCPStdioServer(
        core=HostAdapterCore(
            config_dir=REPO_ROOT / "config",
            db_path=db_path or tmp_path / "tokenbank.db",
        )
    )


def _worker_config(tmp_path: Path) -> WorkerConfig:
    return WorkerConfig(
        worker_id="wrk_demo_local",
        worker_token=WORKER_TOKEN,
        sandbox_root=tmp_path / "sandbox",
        spool_dir=tmp_path / "spool",
        heartbeat_interval_seconds=0.01,
        poll_interval_seconds=0.01,
    )


def _control_client(api_client: TestClient) -> ControlPlaneClient:
    return ControlPlaneClient(
        base_url="http://testserver",
        worker_token=WORKER_TOKEN,
        client=api_client,
    )
