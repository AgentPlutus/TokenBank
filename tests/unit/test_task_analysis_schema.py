from __future__ import annotations

from tokenbank.models import TaskAnalysisReport
from tokenbank.models.work_unit import WorkUnit
from tokenbank.router.privacy_preflight import scan_privacy
from tokenbank.router.task_analyzer import TaskAnalyzer, input_shape_for_work_unit
from tokenbank.router.token_estimator import estimate_tokens


def test_task_analysis_report_validates() -> None:
    report = TaskAnalysisReport.model_validate(
        {
            "task_analysis_id": "ta_wu_001_url_check",
            "work_unit_id": "wu_001",
            "source": "deterministic_preflight",
            "routebook_id": "tokenbank.base",
            "routebook_version": "1.0.0",
            "task_type": "url_check",
            "input_shape": {
                "explicit_refs_count": 0,
                "explicit_urls_count": 1,
                "file_refs_count": 0,
                "inline_chars": 37,
                "inline_bytes": 37,
                "json_depth": 2,
                "list_items_count": 0,
                "workspace_scan_requested": False,
            },
            "token_estimate": {
                "tokenizer_profile_id": "heuristic:cl100k_like:v0",
                "estimated_input_tokens": 10,
                "estimated_output_tokens": 64,
                "estimated_total_tokens": 74,
                "confidence": 0.62,
                "method": "chars_div_4_plus_task_default_output",
            },
            "cost_estimate": {
                "cost_profile_id": "backend_cost_model:backend:url_check:v0",
                "min_cost_micros": 0,
                "expected_cost_micros": 0,
                "max_cost_micros": 0,
                "confidence": 0.8,
                "cost_source": "backend_estimate",
            },
            "privacy_scan": {
                "raw_secret_detected": False,
                "possible_secret_detected": False,
                "private_data_detected": False,
                "remote_eligible": True,
                "matched_signal_counts": {},
                "reason_codes": ["no_privacy_signal_detected"],
            },
            "complexity": {
                "difficulty": "easy",
                "estimated_attempts": 1.0,
                "requires_strong_reasoning": False,
                "requires_long_context": False,
                "requires_tools": True,
                "reason_codes": ["default_difficulty:easy"],
            },
            "effective_task_level": "L0",
            "effective_privacy_level": "private",
            "preflight_decision": "allow",
            "confidence": 0.82,
            "reason_codes": ["deterministic_wp_rb2_preflight"],
        }
    )

    assert report.task_type == "url_check"
    assert report.token_estimate.estimated_total_tokens == 74


def test_input_shape_and_token_estimate_are_deterministic() -> None:
    work_unit = WorkUnit(
        work_unit_id="wu_estimate_url_check",
        run_id="run_estimate_url_check",
        task_type="url_check",
        task_level="L0",
        inline_input={"url": "https://example.com/status"},
        max_cost_micros=0,
    )

    shape = input_shape_for_work_unit(work_unit)
    estimate = estimate_tokens(
        task_type=work_unit.task_type,
        inline_input=work_unit.inline_input,
    )

    assert shape.explicit_urls_count == 1
    assert shape.workspace_scan_requested is False
    assert estimate.tokenizer_profile_id == "heuristic:cl100k_like:v0"
    assert estimate.estimated_total_tokens > estimate.estimated_input_tokens


def test_privacy_preflight_detects_secret_shape_without_exposing_value() -> None:
    scan = scan_privacy({"text": "token sk-abc1234567890SECRET"})

    assert scan.raw_secret_detected is True
    assert scan.remote_eligible is False
    assert "raw_secret_shape_detected" in scan.reason_codes
    assert "sk-abc" not in str(scan.model_dump(mode="json"))


def test_task_analyzer_raises_risk_and_privacy_but_never_lowers() -> None:
    work_unit = WorkUnit(
        work_unit_id="wu_estimate_claim_extraction",
        run_id="run_estimate_claim_extraction",
        task_type="claim_extraction",
        task_level="L2",
        privacy_level="private",
        inline_input={
            "text": "Contact jane@example.com about TokenBank verification.",
            "source_id": "src_1",
        },
        max_cost_micros=0,
    )

    report = TaskAnalyzer.from_dirs().analyze(work_unit=work_unit)

    assert report.effective_task_level == "L2"
    assert report.effective_privacy_level == "sensitive"
    assert report.privacy_scan.private_data_detected is True
    assert report.preflight_decision == "allow"
