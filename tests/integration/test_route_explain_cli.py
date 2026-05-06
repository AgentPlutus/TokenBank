from __future__ import annotations

import json
from pathlib import Path

from typer.testing import CliRunner

from tokenbank.cli.main import app

REPO_ROOT = Path(__file__).resolve().parents[2]


def test_route_explain_cli_returns_profiles_and_trace(tmp_path: Path) -> None:
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
    assert payload["status"] == "ok"
    assert payload["task_profile"]["task_type"] == "url_check"
    assert payload["task_profile"]["routebook_id"] == "tokenbank.base"
    assert payload["route_plan"]["selected_candidate_id"] == (
        "route_url_check_local_tool"
    )
    assert payload["route_decision_trace"]["selected_candidate_id"] == (
        "route_url_check_local_tool"
    )
    assert payload["capacity_profiles"][0]["backend_class"] == "local_tool"
    score_trace = payload["route_decision_trace"]["candidate_scores"][0]
    assert score_trace["hard_filter_results"]["backend_class_allowed"] == "pass"
    assert score_trace["reason_codes"] == [
        "backend_class:local_tool",
        "priority:1",
        "selected_by_existing_routebook_priority",
        "verifier_recipe_available",
        "matches_required_capabilities",
    ]


def test_route_explain_cli_profiles_strong_task_without_executing_it(
    tmp_path: Path,
) -> None:
    input_path = tmp_path / "claim_request.json"
    input_path.write_text(
        json.dumps(
            {
                "text": "TokenBank routes private capacity through Core.",
                "source_id": "src_claim_cli",
                "entity": "TokenBank",
            }
        ),
        encoding="utf-8",
    )
    db_path = tmp_path / "tokenbank.db"

    result = CliRunner().invoke(
        app,
        [
            "route",
            "explain",
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
    task_profile = payload["task_profile"]
    decision_trace = payload["route_decision_trace"]

    assert task_profile["task_family"] == "strong_reasoning"
    assert task_profile["difficulty"] == "high"
    assert task_profile["requires_verifier_recipe_id"] is True
    assert decision_trace["selected_candidate_id"] == "route_claim_model_gateway"
    assert decision_trace["reason_codes"] == [
        "host_model_profiler_only",
        "phase0_route_selection_unchanged",
        "selected_by_existing_routebook_priority",
    ]
    assert decision_trace["rejected_candidates"] == [
        {
            "schema_version": "p0.v1",
            "candidate_id": "route_claim_fallback_primary",
            "reason_codes": [
                "lower_priority_routebook_candidate",
                "available_as_fallback_only",
            ],
        }
    ]
    assert any(
        rule_id == "candidate_rule:route_claim_model_gateway"
        for rule_id in decision_trace["rule_ids"]
    )
    assert all(
        score_trace["hard_filter_results"]["worker_direct_api_model_forbidden"]
        == "pass"
        for score_trace in decision_trace["candidate_scores"]
    )
