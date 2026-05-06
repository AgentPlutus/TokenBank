from __future__ import annotations

import json
from pathlib import Path

from typer.testing import CliRunner

from tokenbank.cli.main import app as cli_app
from tokenbank.demo.private_capacity import (
    DEMO_TASK_ORDER,
    PrivateCapacityDemoRunner,
)
from tokenbank.host_adapter import HostAdapterCore

REPO_ROOT = Path(__file__).resolve().parents[2]


def test_private_capacity_demo_url_check_only(tmp_path: Path) -> None:
    db_path = tmp_path / "tokenbank.db"
    runner = CliRunner()

    result = runner.invoke(
        cli_app,
        [
            "demo",
            "capacity",
            "run",
            "--task",
            "url_check",
            "--json",
            "--config-dir",
            str(REPO_ROOT / "config"),
            "--db-path",
            str(db_path),
            "--demo-dir",
            str(REPO_ROOT / "examples" / "private_capacity_demo"),
        ],
    )

    assert result.exit_code == 0, result.output
    demo = json.loads(result.output)
    assert demo["status"] == "ok"
    assert demo["xradar_required"] is False
    assert demo["tasks_requested"] == ["url_check"]
    assert demo["task_count"] == 1
    assert demo["submissions"]["url_check"]["backend_class"] == "local_tool"
    assert demo["host_results"]["url_check"]["host_result_summary"]["status"] == (
        "succeeded"
    )
    assert demo["cost_quality_memory"]["generated"] is True
    assert demo["capacity"]["after_count"] >= 1


def test_private_capacity_demo_all_five_tasks(tmp_path: Path) -> None:
    demo = PrivateCapacityDemoRunner(
        config_dir=REPO_ROOT / "config",
        db_path=tmp_path / "tokenbank.db",
        demo_dir=REPO_ROOT / "examples" / "private_capacity_demo",
    ).run(all_tasks=True)

    assert demo["status"] == "ok"
    assert demo["tasks_requested"] == list(DEMO_TASK_ORDER)
    assert set(demo["submissions"]) == set(DEMO_TASK_ORDER)
    assert set(demo["host_results"]) == set(DEMO_TASK_ORDER)
    assert set(demo["report_summaries"]) == set(DEMO_TASK_ORDER)

    for task_type in DEMO_TASK_ORDER:
        host_result = demo["host_results"][task_type]
        summary = host_result["host_result_summary"]
        report = demo["report_summaries"][task_type]
        assert host_result["status"] == "ok"
        assert summary["status"] == "succeeded"
        assert summary["task_type"] == task_type
        assert report["report_type"] == "cost_quality_report"
        assert report["totals"]["work_unit_count"] == 1

    assert demo["submissions"]["topic_classification"]["worker_id"] == (
        "wrk_control_plane_gateway"
    )
    assert demo["submissions"]["claim_extraction"]["worker_id"] == (
        "wrk_control_plane_gateway"
    )


def test_private_capacity_demo_does_not_require_xradar(tmp_path: Path) -> None:
    demo = PrivateCapacityDemoRunner(
        config_dir=REPO_ROOT / "config",
        db_path=tmp_path / "tokenbank.db",
        demo_dir=REPO_ROOT / "examples" / "private_capacity_demo",
    ).run(task="url_check")

    demo_source = REPO_ROOT / "src" / "tokenbank" / "demo" / "private_capacity.py"
    source_text = demo_source.read_text(encoding="utf-8")
    assert demo["xradar_required"] is False
    assert "tokenbank.adapters.xradar" not in source_text


def test_private_capacity_demo_generates_report_summary(tmp_path: Path) -> None:
    db_path = tmp_path / "tokenbank.db"
    runner = CliRunner()
    demo_result = runner.invoke(
        cli_app,
        [
            "demo",
            "capacity",
            "run",
            "--all",
            "--json",
            "--config-dir",
            str(REPO_ROOT / "config"),
            "--db-path",
            str(db_path),
            "--demo-dir",
            str(REPO_ROOT / "examples" / "private_capacity_demo"),
        ],
    )
    assert demo_result.exit_code == 0, demo_result.output
    demo = json.loads(demo_result.output)

    report_result = runner.invoke(
        cli_app,
        [
            "report",
            "summary",
            "--run-id",
            demo["run_id"],
            "--json",
            "--db-path",
            str(db_path),
        ],
    )
    capacity_result = runner.invoke(
        cli_app,
        [
            "capacity",
            "list",
            "--json",
            "--config-dir",
            str(REPO_ROOT / "config"),
            "--db-path",
            str(db_path),
        ],
    )

    assert report_result.exit_code == 0, report_result.output
    report = json.loads(report_result.output)
    assert report["run_id"] == demo["run_id"]
    assert report["report_type"] == "cost_quality_report"
    assert report["totals"]["work_unit_count"] == 1

    assert capacity_result.exit_code == 0, capacity_result.output
    capacity = json.loads(capacity_result.output)
    assert any(
        node["capacity_node_id"] == "capnode:worker:wrk_demo_local"
        for node in capacity["nodes"]
    )


def test_private_capacity_demo_uses_host_adapter_path(
    tmp_path: Path,
    monkeypatch,
) -> None:
    calls: list[str] = []
    original_submit = HostAdapterCore.submit_work_unit

    def wrapped_submit(self, *, task_type, input_payload=None, wait=False):
        calls.append(task_type)
        return original_submit(
            self,
            task_type=task_type,
            input_payload=input_payload,
            wait=wait,
        )

    monkeypatch.setattr(HostAdapterCore, "submit_work_unit", wrapped_submit)

    PrivateCapacityDemoRunner(
        config_dir=REPO_ROOT / "config",
        db_path=tmp_path / "tokenbank.db",
        demo_dir=REPO_ROOT / "examples" / "private_capacity_demo",
    ).run(task="url_check")

    assert calls == ["url_check"]


def test_no_xradar_core_dependency() -> None:
    source_text = "\n".join(
        path.read_text(encoding="utf-8")
        for path in (REPO_ROOT / "src" / "tokenbank").rglob("*.py")
    )

    assert "tokenbank.adapters.xradar" not in source_text
