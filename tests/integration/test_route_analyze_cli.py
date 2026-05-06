from __future__ import annotations

import json
from pathlib import Path

from typer.testing import CliRunner

from tokenbank.cli.main import app

REPO_ROOT = Path(__file__).resolve().parents[2]


def test_route_analyze_cli_returns_task_analysis_report(tmp_path: Path) -> None:
    input_path = REPO_ROOT / "tests/fixtures/route_requests/url_check.json"
    db_path = tmp_path / "tokenbank.db"

    result = CliRunner().invoke(
        app,
        [
            "route",
            "analyze",
            "--task-type",
            "url_check",
            "--input",
            str(input_path),
            "--db-path",
            str(db_path),
            "--config-dir",
            str(REPO_ROOT / "config"),
            "--json",
        ],
    )

    assert result.exit_code == 0, result.output
    payload = json.loads(result.output)
    report = payload["task_analysis_report"]

    assert payload["status"] == "ok"
    assert payload["task_analysis_hash"]
    assert report["task_type"] == "url_check"
    assert report["input_shape"]["explicit_urls_count"] == 1
    assert report["token_estimate"]["tokenizer_profile_id"] == (
        "heuristic:cl100k_like:v0"
    )
    assert report["preflight_decision"] == "allow"


def test_route_analyze_cli_profiles_high_contrast_claim_task(
    tmp_path: Path,
) -> None:
    input_path = REPO_ROOT / "tests/fixtures/route_requests/claim_extraction.json"
    db_path = tmp_path / "tokenbank.db"

    result = CliRunner().invoke(
        app,
        [
            "route",
            "analyze",
            "--task-type",
            "claim_extraction",
            "--input",
            str(input_path),
            "--db-path",
            str(db_path),
            "--config-dir",
            str(REPO_ROOT / "config"),
            "--json",
        ],
    )

    assert result.exit_code == 0, result.output
    payload = json.loads(result.output)
    report = payload["task_analysis_report"]

    assert report["complexity"]["difficulty"] == "high"
    assert report["complexity"]["requires_strong_reasoning"] is True
    assert report["effective_task_level"] == "L2"
    assert report["cost_estimate"]["expected_cost_micros"] > 0


def test_route_explain_includes_task_analysis_summary(tmp_path: Path) -> None:
    input_path = REPO_ROOT / "tests/fixtures/route_requests/url_check.json"
    db_path = tmp_path / "tokenbank.db"

    result = CliRunner().invoke(
        app,
        [
            "route",
            "explain",
            "--task-type",
            "url_check",
            "--input",
            str(input_path),
            "--db-path",
            str(db_path),
            "--config-dir",
            str(REPO_ROOT / "config"),
            "--json",
        ],
    )

    assert result.exit_code == 0, result.output
    payload = json.loads(result.output)
    trace = payload["route_decision_trace"]

    assert payload["task_analysis_report"]["task_type"] == "url_check"
    assert payload["task_analysis_hash"] == trace["task_analysis_hash"]
    assert trace["estimate_summary"]["estimated_total_tokens"] > 0
    assert trace["estimate_summary"]["expected_cost_micros"] == 0
