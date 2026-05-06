from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient
from typer.testing import CliRunner

from tokenbank.app.api import create_app
from tokenbank.cli.main import app as cli_app
from tokenbank.core.canonical import canonical_json_dumps
from tokenbank.db.bootstrap import initialize_database
from tokenbank.host import execute_control_plane_gateway_assignment_once
from tokenbank.observability.report_generator import (
    generate_capacity_report,
    generate_cost_quality_report,
)
from tokenbank.observability.sql_queries import business_state_snapshot
from tokenbank.worker.config import WorkerConfig
from tokenbank.worker.daemon import WorkerDaemon
from tokenbank.worker.poller import ControlPlaneClient

REPO_ROOT = Path(__file__).resolve().parents[2]
WORKER_TOKEN = "tbk_w_reports_worker"


@pytest.fixture(scope="module")
def all_five_db(tmp_path_factory: pytest.TempPathFactory) -> dict[str, Any]:
    tmp_path = tmp_path_factory.mktemp("wp11_reports")
    db_path = tmp_path / "tokenbank.db"
    runner = CliRunner()
    submissions = {
        "url_check": _submit(
            runner,
            db_path,
            ["host", "url-check", "https://example.com/status"],
        ),
        "dedup": _submit(
            runner,
            db_path,
            ["host", "dedup", json.dumps(["alpha", "beta", "alpha"])],
        ),
        "webpage_extraction": _submit(
            runner,
            db_path,
            [
                "host",
                "webpage-extract",
                "https://example.com/report",
                "--html",
                "<html><title>Report</title><body>Data only.</body></html>",
            ],
        ),
        "topic_classification": _submit(
            runner,
            db_path,
            [
                "host",
                "topic-classify",
                "The API worker stores software cost evidence.",
            ],
        ),
        "claim_extraction": _submit(
            runner,
            db_path,
            [
                "host",
                "claim-extract",
                "TokenBank routes private capacity through a gateway.",
                "--source-id",
                "src_reports_claim_1",
                "--entity",
                "TokenBank",
            ],
        ),
    }

    app = create_app(config_dir=REPO_ROOT / "config", db_path=db_path)
    with TestClient(app) as api_client:
        daemon = WorkerDaemon(
            _worker_config(tmp_path),
            client=_control_client(api_client),
        )
        daemon.register()
        for _ in range(3):
            assert daemon.run_once()["status"] == "completed"
        execute_control_plane_gateway_assignment_once(
            app.state.db,
            assignment_id=submissions["topic_classification"]["assignment_id"],
        )
        execute_control_plane_gateway_assignment_once(
            app.state.db,
            assignment_id=submissions["claim_extraction"]["assignment_id"],
        )

    return {"db_path": db_path, "submissions": submissions}


def test_host_cost_quality_summary_for_url_check(all_five_db: dict[str, Any]) -> None:
    report = _report(all_five_db, "url_check")
    summary = report["host_cost_quality_summaries"][0]["cost_summary"]

    assert summary["cost_source"] == "zero_internal_phase0"
    assert summary["local_zero_cost_caveat"]
    assert summary["quality_status"] == "passed"


def test_run_cost_quality_report_for_all_five_task_types(
    all_five_db: dict[str, Any],
) -> None:
    task_types = {
        _report(all_five_db, task_type)["summaries"]["by_task_type"][0]["task_type"]
        for task_type in all_five_db["submissions"]
    }

    assert task_types == {
        "url_check",
        "dedup",
        "webpage_extraction",
        "topic_classification",
        "claim_extraction",
    }


def test_capacity_node_summary_counts_work_units(all_five_db: dict[str, Any]) -> None:
    report = _capacity_report(all_five_db, "url_check")
    node_summary = _find(
        report["capacity_node_summaries"],
        "capacity_node_id",
        "capnode:worker:wrk_demo_local",
    )

    assert node_summary["backend_class"] == "local_tool"
    assert node_summary["work_unit_count"] == 1
    assert node_summary["success_count"] == 1


def test_backend_summary_by_backend_class(all_five_db: dict[str, Any]) -> None:
    report = _report(all_five_db, "claim_extraction")
    backend_summary = _find(
        report["summaries"]["by_backend_class"],
        "backend_class",
        "api_model_gateway",
    )

    assert backend_summary["work_unit_count"] == 1
    assert backend_summary["cost_micros"] == 1000
    assert report["totals"]["primary_model_fallback_cost_micros"] == 0


def test_task_type_summary_by_task_type(all_five_db: dict[str, Any]) -> None:
    report = _report(all_five_db, "dedup")
    task_summary = _find(report["summaries"]["by_task_type"], "task_type", "dedup")

    assert task_summary["success_count"] == 1
    assert task_summary["warning_count"] == 0


def test_local_zero_cost_caveat_present(all_five_db: dict[str, Any]) -> None:
    report = _report(all_five_db, "webpage_extraction")

    assert any("zero_internal_phase0" in caveat for caveat in report["caveats"])


def test_baseline_none_has_no_saving_claim(all_five_db: dict[str, Any]) -> None:
    report = _report(all_five_db, "topic_classification")

    assert report["baseline"]["baseline_mode"] == "none"
    assert report["baseline"]["saving_ratio_bps"] is None
    assert report["baseline"]["saving_claimed"] is False


def test_baseline_estimated_has_caveat(all_five_db: dict[str, Any]) -> None:
    conn = initialize_database(all_five_db["db_path"])
    run_id = all_five_db["submissions"]["claim_extraction"]["run_id"]

    report = generate_cost_quality_report(
        conn,
        run_id=run_id,
        baseline_mode="estimated",
    )

    assert report["baseline"]["baseline_mode"] == "estimated"
    assert report["baseline"]["baseline_cost_micros"] == 1000
    assert any("estimated" in caveat for caveat in report["baseline"]["caveats"])


def test_accept_with_warning_not_strict_accept(tmp_path: Path) -> None:
    conn = _seed_report_case(
        tmp_path,
        run_id="run_warning",
        recommendation="accept_with_warning",
        verifier_status="needs_review",
    )

    report = generate_cost_quality_report(conn, run_id="run_warning")

    assert report["totals"]["success_count"] == 0
    assert report["totals"]["warning_count"] == 1


def test_quarantine_count_separate(tmp_path: Path) -> None:
    conn = _seed_report_case(
        tmp_path,
        run_id="run_quarantine",
        result_status="quarantined",
        recommendation="quarantine",
        verifier_status="failed",
    )

    report = generate_cost_quality_report(conn, run_id="run_quarantine")

    assert report["totals"]["quarantine_count"] == 1
    assert report["totals"]["failure_count"] == 0


def test_report_generation_does_not_mutate_business_state(
    all_five_db: dict[str, Any],
) -> None:
    conn = initialize_database(all_five_db["db_path"])
    run_id = all_five_db["submissions"]["claim_extraction"]["run_id"]
    before = business_state_snapshot(conn, run_id)

    generate_cost_quality_report(conn, run_id=run_id)
    generate_capacity_report(conn, run_id=run_id)
    after = business_state_snapshot(conn, run_id)

    assert after == before


def test_report_summary_cli_json(all_five_db: dict[str, Any]) -> None:
    runner = CliRunner()
    run_id = all_five_db["submissions"]["url_check"]["run_id"]
    result = runner.invoke(
        cli_app,
        [
            "report",
            "summary",
            "--run-id",
            run_id,
            "--json",
            "--db-path",
            str(all_five_db["db_path"]),
        ],
    )

    assert result.exit_code == 0, result.output
    report = json.loads(result.output)
    assert report["run_id"] == run_id
    assert report["report_type"] == "cost_quality_report"


def test_report_capacity_cli_json(all_five_db: dict[str, Any]) -> None:
    runner = CliRunner()
    run_id = all_five_db["submissions"]["dedup"]["run_id"]
    result = runner.invoke(
        cli_app,
        [
            "report",
            "capacity",
            "--run-id",
            run_id,
            "--json",
            "--db-path",
            str(all_five_db["db_path"]),
        ],
    )

    assert result.exit_code == 0, result.output
    report = json.loads(result.output)
    assert report["report_type"] == "capacity_performance_report"
    assert report["capacity_node_summaries"]


def _report(data: dict[str, Any], task_type: str) -> dict[str, Any]:
    conn = initialize_database(data["db_path"])
    return generate_cost_quality_report(
        conn,
        run_id=data["submissions"][task_type]["run_id"],
    )


def _capacity_report(data: dict[str, Any], task_type: str) -> dict[str, Any]:
    conn = initialize_database(data["db_path"])
    return generate_capacity_report(
        conn,
        run_id=data["submissions"][task_type]["run_id"],
    )


def _submit(
    runner: CliRunner,
    db_path: Path,
    args: list[str],
) -> dict[str, Any]:
    result = runner.invoke(
        cli_app,
        [
            *args,
            "--config-dir",
            str(REPO_ROOT / "config"),
            "--db-path",
            str(db_path),
        ],
    )
    assert result.exit_code == 0, result.output
    return json.loads(result.output)


def _worker_config(tmp_path: Path) -> WorkerConfig:
    return WorkerConfig(
        worker_id="wrk_demo_local",
        worker_token=WORKER_TOKEN,
        capabilities=["url_check", "dedup", "webpage_extraction"],
        backend_ids=[
            "backend:url_check:v0",
            "backend:dedup:local_script:v0",
            "backend:webpage_extraction:browser_fetch:v0",
        ],
        backend_classes=["local_tool", "local_script", "browser_fetch"],
        allowed_task_types=["url_check", "dedup", "webpage_extraction"],
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


def _find(items: list[dict[str, Any]], key: str, value: str) -> dict[str, Any]:
    for item in items:
        if item[key] == value:
            return item
    raise AssertionError(f"{key}={value} not found in {items}")


def _seed_report_case(
    tmp_path: Path,
    *,
    run_id: str,
    result_status: str = "succeeded",
    recommendation: str = "accept",
    verifier_status: str = "passed",
) -> sqlite3.Connection:
    conn = initialize_database(tmp_path / f"{run_id}.db")
    now = "2026-05-04T00:00:00Z"
    work_unit_id = f"wu_{run_id}"
    attempt_id = f"att_{run_id}"
    assignment_id = f"asg_{run_id}"
    result_envelope_id = f"res_{run_id}"
    verifier_report_id = f"vr_{run_id}"
    result_body = {
        "result_envelope_id": result_envelope_id,
        "work_unit_id": work_unit_id,
        "run_id": run_id,
        "attempt_id": attempt_id,
        "assignment_id": assignment_id,
        "status": result_status,
        "backend_id": "backend:url_check:v0",
        "backend_class": "local_tool",
        "worker_id": "wrk_seed",
        "capacity_node_id": "capnode:worker:wrk_seed",
        "output_hash": "f" * 64,
        "result_hash": "e" * 64,
        "cost_estimate_micros": 0,
        "actual_cost_micros": 0,
        "cost_source": "zero_internal_phase0",
        "cost_confidence": "high",
        "duration_ms": 10,
        "errors": [],
    }
    verifier_body = {
        "verifier_report_id": verifier_report_id,
        "work_unit_id": work_unit_id,
        "result_envelope_id": result_envelope_id,
        "status": verifier_status,
        "recommendation": recommendation,
    }
    conn.execute(
        "INSERT INTO runs VALUES (?, ?, ?, ?, ?)",
        (run_id, "succeeded", "{}", now, now),
    )
    conn.execute(
        """
        INSERT INTO work_units
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (work_unit_id, run_id, "succeeded", "url_check", "L1", "{}", now, now),
    )
    conn.execute(
        """
        INSERT INTO route_plans
        VALUES (?, ?, ?, ?, ?)
        """,
        (f"rp_{run_id}", work_unit_id, "planned", "{}", now),
    )
    conn.execute(
        """
        INSERT INTO policy_decisions
        VALUES (?, ?, ?, ?, ?, ?)
        """,
        (f"pd_{run_id}", work_unit_id, f"rp_{run_id}", "approved", "{}", now),
    )
    conn.execute(
        """
        INSERT INTO execution_attempts (
          attempt_id,
          work_unit_id,
          route_plan_id,
          policy_decision_id,
          status,
          body_json,
          created_at,
          attempt_number
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            attempt_id,
            work_unit_id,
            f"rp_{run_id}",
            f"pd_{run_id}",
            "succeeded",
            "{}",
            now,
            1,
        ),
    )
    conn.execute(
        """
        INSERT INTO assignments (
          assignment_id,
          attempt_id,
          work_unit_id,
          worker_id,
          status,
          body_json,
          created_at,
          capacity_node_id,
          backend_id,
          effective_constraints_json,
          assigned_at,
          updated_at
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            assignment_id,
            attempt_id,
            work_unit_id,
            "wrk_seed",
            "completed",
            "{}",
            now,
            "capnode:worker:wrk_seed",
            "backend:url_check:v0",
            "{}",
            now,
            now,
        ),
    )
    conn.execute(
        """
        INSERT INTO result_envelopes
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            result_envelope_id,
            work_unit_id,
            attempt_id,
            assignment_id,
            result_status,
            "f" * 64,
            "e" * 64,
            canonical_json_dumps(result_body),
            now,
        ),
    )
    conn.execute(
        """
        INSERT INTO verifier_reports
        VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        (
            verifier_report_id,
            work_unit_id,
            result_envelope_id,
            verifier_status,
            recommendation,
            canonical_json_dumps(verifier_body),
            now,
        ),
    )
    conn.commit()
    return conn
