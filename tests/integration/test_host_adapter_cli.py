from __future__ import annotations

import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from typer.testing import CliRunner

from tokenbank.app.api import create_app
from tokenbank.cli.main import app as cli_app
from tokenbank.host_adapter import HostAdapterCore
from tokenbank.host_adapter.normalizer import HostAdapterInputError
from tokenbank.worker.config import WorkerConfig
from tokenbank.worker.daemon import WorkerDaemon
from tokenbank.worker.poller import ControlPlaneClient

REPO_ROOT = Path(__file__).resolve().parents[2]
WORKER_TOKEN = "tbk_w_wp12_host_adapter"


def test_cli_workunit_submit_and_result_happy_path(tmp_path: Path) -> None:
    db_path = tmp_path / "tokenbank.db"
    input_path = tmp_path / "url.json"
    input_path.write_text(
        json.dumps({"url": "https://example.com/wp12"}),
        encoding="utf-8",
    )
    runner = CliRunner()

    submitted = runner.invoke(
        cli_app,
        [
            "workunit",
            "submit",
            "--task-type",
            "url_check",
            "--input",
            str(input_path),
            "--json",
            "--config-dir",
            str(REPO_ROOT / "config"),
            "--db-path",
            str(db_path),
        ],
    )

    assert submitted.exit_code == 0, submitted.output
    submission = json.loads(submitted.output)
    assert submission["status"] == "submitted"
    assert submission["work_unit_id"].startswith("wu_vs0_")

    status = runner.invoke(
        cli_app,
        [
            "workunit",
            "status",
            submission["work_unit_id"],
            "--json",
            "--config-dir",
            str(REPO_ROOT / "config"),
            "--db-path",
            str(db_path),
        ],
    )
    assert status.exit_code == 0, status.output
    assert json.loads(status.output)["work_unit"]["status"] == "assigned"

    app = create_app(config_dir=REPO_ROOT / "config", db_path=db_path)
    with TestClient(app) as api_client:
        daemon = WorkerDaemon(
            _worker_config(tmp_path),
            client=_control_client(api_client),
        )
        daemon.register()
        assert daemon.run_once()["status"] == "completed"

    result = runner.invoke(
        cli_app,
        [
            "workunit",
            "result",
            submission["work_unit_id"],
            "--json",
            "--config-dir",
            str(REPO_ROOT / "config"),
            "--db-path",
            str(db_path),
        ],
    )

    assert result.exit_code == 0, result.output
    summary = json.loads(result.output)["host_result_summary"]
    assert summary["status"] == "succeeded"
    assert summary["task_type"] == "url_check"
    assert summary["backend_class"] == "local_tool"


def test_host_adapter_core_estimate_and_submit(tmp_path: Path) -> None:
    core = HostAdapterCore(
        config_dir=REPO_ROOT / "config",
        db_path=tmp_path / "tokenbank.db",
    )

    estimate = core.estimate_route(
        task_type="url_check",
        input_payload={"url": "https://example.com/estimate"},
    )
    submission = core.submit_work_unit(
        task_type="url_check",
        input_payload={"url": "https://example.com/submit"},
    )

    assert estimate["status"] == "ok"
    assert estimate["selected_candidate"]["backend_class"] == "local_tool"
    assert submission["status"] == "submitted"
    assert submission["assignment_id"]


def test_host_adapter_rejects_credentials_or_oauth_input(tmp_path: Path) -> None:
    core = HostAdapterCore(
        config_dir=REPO_ROOT / "config",
        db_path=tmp_path / "tokenbank.db",
    )

    with pytest.raises(HostAdapterInputError):
        core.submit_work_unit(
            task_type="url_check",
            input_payload={
                "url": "https://example.com/secret",
                "api_key": "[REDACTED_SECRET]",
            },
        )

    with pytest.raises(HostAdapterInputError):
        core.submit_work_unit(
            task_type="url_check",
            input_payload={
                "url": "https://example.com/secret",
                "oauth": {"access_token": "[REDACTED_TOKEN]"},
            },
        )


def test_host_adapter_no_workspace_scan() -> None:
    source_text = _host_adapter_source_text()

    assert ".rglob(" not in source_text
    assert "os.walk(" not in source_text
    assert "scandir(" not in source_text


def test_host_adapter_no_model_proxy(tmp_path: Path) -> None:
    core = HostAdapterCore(
        config_dir=REPO_ROOT / "config",
        db_path=tmp_path / "tokenbank.db",
    )

    with pytest.raises(HostAdapterInputError):
        core.submit_work_unit(
            task_type="chat_completion",
            input_payload={"messages": [{"role": "user", "content": "hello"}]},
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


def _host_adapter_source_text() -> str:
    package_dir = REPO_ROOT / "src" / "tokenbank" / "host_adapter"
    return "\n".join(
        path.read_text(encoding="utf-8")
        for path in package_dir.iterdir()
        if path.suffix == ".py"
    )
