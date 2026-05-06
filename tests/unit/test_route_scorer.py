from __future__ import annotations

from pathlib import Path

from tokenbank.host_adapter import HostAdapterCore

REPO_ROOT = Path(__file__).resolve().parents[2]


def _core(tmp_path: Path) -> HostAdapterCore:
    return HostAdapterCore(
        config_dir=REPO_ROOT / "config",
        db_path=tmp_path / "tokenbank.db",
    )


def test_route_scorer_selects_highest_passing_candidate(tmp_path: Path) -> None:
    result = _core(tmp_path).score_route(
        task_type="claim_extraction",
        input_payload={
            "text": "TokenBank verifies private capacity results.",
            "source_id": "src_unit_score",
        },
    )

    report = result["route_scoring_report"]

    assert report["selection_status"] == "selected_highest_scoring_candidate"
    assert report["selected_candidate_id"] == "route_claim_model_gateway"
    assert report["candidate_scores"][0]["rank"] == 1
    assert report["candidate_scores"][0]["score"]["total"] > 0
    assert report["candidate_scores"][1]["rank"] == 2
    assert report["candidate_scores"][1]["score"]["total"] > 0
    assert report["score_weights"]["capability_fit"] == 0.3


def test_route_scorer_blocks_raw_secret_preflight(tmp_path: Path) -> None:
    result = _core(tmp_path).score_route(
        task_type="claim_extraction",
        input_payload={
            "text": "Do not route this raw provider token: sk-testsecret1234567890",
            "source_id": "src_unit_secret",
        },
    )

    report = result["route_scoring_report"]

    assert result["task_analysis_report"]["preflight_decision"] == "deny"
    assert report["selection_status"] == "no_passing_candidate_keep_existing_selection"
    assert all(
        candidate["hard_filter_decision"] == "fail"
        for candidate in report["candidate_scores"]
    )
    first = report["candidate_scores"][0]
    assert first["hard_filter_results"]["preflight_allow"] == "fail"
    assert first["hard_filter_results"]["credential_boundary_valid"] == "fail"
    assert "hard_filter_failed:preflight_allow" in first["reason_codes"]
