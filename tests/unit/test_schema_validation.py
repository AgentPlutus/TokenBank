from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest
from jsonschema import Draft202012Validator
from pydantic import ValidationError

from tokenbank.core.canonical import canonical_json_hash, output_hash, result_hash
from tokenbank.models import WorkUnit
from tokenbank.schemas.export import SCHEMA_MODELS

REPO_ROOT = Path(__file__).resolve().parents[2]


def _schema(filename: str) -> dict[str, Any]:
    return json.loads((REPO_ROOT / "schemas" / filename).read_text(encoding="utf-8"))


def _validate_with_json_schema(filename: str, payload: dict[str, Any]) -> None:
    Draft202012Validator(_schema(filename)).validate(payload)


def sample_payloads() -> dict[str, dict[str, Any]]:
    work_unit = {
        "schema_version": "p0.v1",
        "work_unit_id": "wu_001",
        "run_id": "run_001",
        "task_type": "url_check",
        "task_level": "L1",
        "status": "submitted",
        "privacy_level": "private",
        "data_labels": ["public_url"],
        "input_refs": [],
        "inline_input": {"url": "https://example.com"},
        "output_schema_ref": "url_check_v0",
        "max_cost_micros": 0,
        "deadline_ms": 30000,
        "created_at": "2026-05-04T00:00:00Z",
        "updated_at": "2026-05-04T00:00:00Z",
    }
    capacity_health = {
        "schema_version": "p0.v1",
        "capacity_node_id": "capnode:tool:url_check:v0",
        "status": "healthy",
        "checked_at": "2026-05-04T00:00:00Z",
        "latency_ms": 12,
        "active_assignments": 0,
        "message": None,
    }
    capacity_node = {
        "schema_version": "p0.v1",
        "capacity_node_id": "capnode:tool:url_check:v0",
        "node_type": "local_tool",
        "identity": "url_check local tool",
        "capabilities": ["url_check"],
        "trust_level": "trusted_private",
        "allowed_task_types": ["url_check"],
        "allowed_data_labels": ["public_url"],
        "allowed_privacy_levels": ["private"],
        "execution_location": "local_machine",
        "cost_model": {
            "schema_version": "p0.v1",
            "unit": "work_unit",
            "estimated_cost_micros": 0,
            "cost_source": "policy_default",
        },
        "health": capacity_health,
        "policy_constraints": {"allowed_domains": ["example.com"]},
        "backend_ids": ["backend:url_check:v0"],
        "backend_classes": ["local_tool"],
        "worker_id": "wrk_local_01",
        "provider_id": None,
        "model_id": None,
        "manifest_hash": canonical_json_hash({"backend": "url_check", "version": "v0"}),
        "created_at": "2026-05-04T00:00:00Z",
        "updated_at": "2026-05-04T00:00:00Z",
    }
    route_candidate = {
        "schema_version": "p0.v1",
        "route_candidate_id": "rc_001",
        "capacity_node_id": "capnode:tool:url_check:v0",
        "backend_class": "local_tool",
        "backend_id": "backend:url_check:v0",
        "worker_selector": {"worker_id": "wrk_local_01"},
        "priority": 1,
        "estimated_cost_micros": 0,
        "verifier_recipe_id": "url_check_v0",
        "policy_hints": ["domain_allowlist"],
    }
    route_plan = {
        "schema_version": "p0.v1",
        "route_plan_id": "rp_001",
        "work_unit_id": "wu_001",
        "task_type": "url_check",
        "task_level": "L1",
        "candidates": [route_candidate],
        "selected_candidate_id": "rc_001",
        "verifier_recipe_id": "url_check_v0",
        "risk_level": "low",
        "policy_hints": ["domain_allowlist"],
        "created_at": "2026-05-04T00:00:00Z",
        "validated_at": "2026-05-04T00:00:01Z",
    }
    task_profile = {
        "schema_version": "p0.v1",
        "task_profile_id": "tp_wu_001_url_check",
        "work_unit_id": "wu_001",
        "routebook_id": "tokenbank.base",
        "routebook_version": "1.0.0",
        "source": "deterministic",
        "task_family": "browser",
        "task_type": "url_check",
        "difficulty": "easy",
        "risk_level": "L1",
        "privacy_level": "private",
        "context_size": "small",
        "latency_preference": "normal",
        "cost_preference": "balanced",
        "required_capabilities": [
            {
                "schema_version": "p0.v1",
                "capability": "browser_fetch",
                "min_score": 0.75,
                "importance": "required",
            }
        ],
        "forbidden_capabilities": [],
        "requires_tools": ["local_tool"],
        "requires_verifier_recipe_id": True,
        "success_criteria": ["reachable_status", "result_hash"],
        "ambiguity": {
            "schema_version": "p0.v1",
            "status": "low",
            "unresolved_questions": [],
        },
        "confidence": 0.82,
        "profile_reason_codes": ["deterministic_wp_rb1_profile"],
    }
    task_analysis_report = {
        "schema_version": "p0.v1",
        "task_analysis_id": "ta_wu_001_url_check",
        "work_unit_id": "wu_001",
        "source": "deterministic_preflight",
        "routebook_id": "tokenbank.base",
        "routebook_version": "1.0.0",
        "task_type": "url_check",
        "input_shape": {
            "schema_version": "p0.v1",
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
            "schema_version": "p0.v1",
            "tokenizer_profile_id": "heuristic:cl100k_like:v0",
            "estimated_input_tokens": 10,
            "estimated_output_tokens": 64,
            "estimated_total_tokens": 74,
            "confidence": 0.62,
            "method": "chars_div_4_plus_task_default_output",
        },
        "cost_estimate": {
            "schema_version": "p0.v1",
            "cost_profile_id": "backend_cost_model:backend:url_check:v0",
            "min_cost_micros": 0,
            "expected_cost_micros": 0,
            "max_cost_micros": 0,
            "confidence": 0.8,
            "cost_source": "backend_estimate",
        },
        "privacy_scan": {
            "schema_version": "p0.v1",
            "raw_secret_detected": False,
            "possible_secret_detected": False,
            "private_data_detected": False,
            "remote_eligible": True,
            "matched_signal_counts": {},
            "reason_codes": ["no_privacy_signal_detected"],
        },
        "complexity": {
            "schema_version": "p0.v1",
            "difficulty": "easy",
            "estimated_attempts": 1.0,
            "requires_strong_reasoning": False,
            "requires_long_context": False,
            "requires_tools": True,
            "reason_codes": ["default_difficulty:easy"],
        },
        "effective_task_level": "L1",
        "effective_privacy_level": "private",
        "preflight_decision": "allow",
        "confidence": 0.82,
        "reason_codes": ["deterministic_wp_rb2_preflight"],
    }
    capacity_profile = {
        "schema_version": "p0.v1",
        "capacity_profile_id": "cp_backend_url_check_v0",
        "capacity_node_id": "capnode:tool:url_check:v0",
        "backend_id": "backend:url_check:v0",
        "backend_class": "local_tool",
        "ownership_scope": "user_local",
        "execution_boundary": "local_machine",
        "availability_state": "available",
        "model_profile": None,
        "capabilities": {
            "deterministic_local": {
                "schema_version": "p0.v1",
                "score": 0.8,
                "evidence": "declared",
            }
        },
        "cost": {
            "schema_version": "p0.v1",
            "estimated_cost_micros": 0,
            "cost_tier": "free",
        },
        "latency": {
            "schema_version": "p0.v1",
            "p50_ms": None,
            "p95_ms": None,
        },
        "quality_memory": {
            "schema_version": "p0.v1",
            "verifier_pass_rate": None,
            "accepted_result_rate": None,
            "sample_size": 0,
        },
        "verified_for": [
            {
                "schema_version": "p0.v1",
                "task_type": "url_check",
                "verifier_recipe_id": "url_check_v0",
                "status": "declared",
            }
        ],
    }
    route_decision_trace = {
        "schema_version": "p0.v1",
        "route_decision_id": "rd_rp_001",
        "route_plan_id": "rp_001",
        "work_unit_id": "wu_001",
        "routebook_id": "tokenbank.base",
        "routebook_version": "1.0.0",
        "task_analysis_hash": canonical_json_hash(task_analysis_report),
        "task_profile_hash": canonical_json_hash(task_profile),
        "capacity_snapshot_hash": canonical_json_hash([capacity_profile]),
        "selected_candidate_id": "rc_001",
        "candidate_scores": [
            {
                "schema_version": "p0.v1",
                "candidate_id": "rc_001",
                "score": {
                    "schema_version": "p0.v1",
                    "total": 1.0,
                    "capability_fit": 0.8,
                    "policy_fit": 1.0,
                    "quality_fit": 0.5,
                    "cost_fit": 1.0,
                    "latency_fit": 0.5,
                    "trust_fit": 1.0,
                    "uncertainty_penalty": 0.0,
                },
                "hard_filter_results": {"policy_allowed": "pass"},
                "reason_codes": ["selected_candidate"],
            }
        ],
        "rejected_candidates": [],
        "estimate_summary": {
            "task_analysis_id": "ta_wu_001_url_check",
            "estimated_total_tokens": 74,
            "expected_cost_micros": 0,
            "preflight_decision": "allow",
        },
        "reason_codes": ["phase0_route_selection_unchanged"],
        "rule_ids": ["rc_001"],
        "user_summary": "TokenBank kept final route selection inside Core.",
    }
    policy_decision = {
        "schema_version": "p0.v1",
        "policy_decision_id": "pd_001",
        "work_unit_id": "wu_001",
        "route_plan_id": "rp_001",
        "decision": "approved",
        "reasons": ["allowed public URL check"],
        "effective_constraints": {"allowed_domains": ["example.com"]},
        "decided_at": "2026-05-04T00:00:02Z",
    }
    attempt = {
        "schema_version": "p0.v1",
        "attempt_id": "att_001",
        "work_unit_id": "wu_001",
        "route_plan_id": "rp_001",
        "policy_decision_id": "pd_001",
        "attempt_number": 1,
        "status": "created",
        "created_at": "2026-05-04T00:00:03Z",
        "started_at": None,
        "completed_at": None,
    }
    assignment = {
        "schema_version": "p0.v1",
        "assignment_id": "asg_001",
        "attempt_id": "att_001",
        "work_unit_id": "wu_001",
        "worker_id": "wrk_local_01",
        "capacity_node_id": "capnode:tool:url_check:v0",
        "backend_id": "backend:url_check:v0",
        "status": "created",
        "lease_token_hash": "sha256:lease",
        "lease_version": 0,
        "effective_constraints": {"allowed_domains": ["example.com"]},
        "assigned_at": "2026-05-04T00:00:04Z",
        "lease_expires_at": "2026-05-04T00:05:04Z",
    }
    backend_health = {
        "schema_version": "p0.v1",
        "backend_id": "backend:url_check:v0",
        "status": "healthy",
        "checked_at": "2026-05-04T00:00:00Z",
        "latency_ms": 10,
        "message": None,
    }
    backend_manifest = {
        "schema_version": "p0.v1",
        "backend_id": "backend:url_check:v0",
        "backend_class": "local_tool",
        "capacity_node_id": "capnode:tool:url_check:v0",
        "display_name": "URL Check Tool",
        "version": "v0",
        "supported_task_types": ["url_check"],
        "allowed_privacy_levels": ["private"],
        "execution_location": "local_machine",
        "manifest_hash": canonical_json_hash({"backend": "url_check", "version": "v0"}),
        "health": backend_health,
        "cost_model": {
            "schema_version": "p0.v1",
            "unit": "work_unit",
            "estimated_cost_micros": 0,
            "cost_source": "policy_default",
        },
        "policy_constraints": {"allowed_domains": ["example.com"]},
    }
    usage = {
        "schema_version": "p0.v1",
        "usage_record_id": "usage_001",
        "work_unit_id": "wu_001",
        "attempt_id": "att_001",
        "backend_id": "backend:url_check:v0",
        "input_units": 1,
        "output_units": 1,
        "estimated_cost_micros": 0,
        "actual_cost_micros": 0,
        "cost_source": "not_applicable",
        "recorded_at": "2026-05-04T00:00:06Z",
    }
    backend_error = {
        "schema_version": "p0.v1",
        "error_code": "TIMEOUT",
        "error_message": "Request timed out after policy timeout.",
        "retryable": True,
        "redacted_details": {"timeout_ms": 30000},
        "occurred_at": "2026-05-04T00:00:07Z",
    }
    output = {"url": "https://example.com", "reachable": True}
    out_hash = output_hash(output)
    res_hash = result_hash({"work_unit_id": "wu_001", "output_hash": out_hash})
    result_envelope = {
        "schema_version": "p0.v1",
        "result_envelope_id": "res_001",
        "work_unit_id": "wu_001",
        "run_id": "run_001",
        "attempt_id": "att_001",
        "assignment_id": "asg_001",
        "status": "succeeded",
        "output": output,
        "output_hash": out_hash,
        "result_hash": res_hash,
        "artifact_refs": [],
        "usage_records": [usage],
        "backend_error": None,
        "started_at": "2026-05-04T00:00:05Z",
        "completed_at": "2026-05-04T00:00:06Z",
        "duration_ms": 1000,
    }
    verifier_report = {
        "schema_version": "p0.v1",
        "verifier_report_id": "vr_001",
        "work_unit_id": "wu_001",
        "result_envelope_id": "res_001",
        "verifier_recipe_id": "url_check_v0",
        "status": "passed",
        "recommendation": "accept",
        "checks": [
            {
                "schema_version": "p0.v1",
                "name": "output_hash_present",
                "status": "passed",
                "message": "hash exists",
                "observed_hash": out_hash,
                "metadata": {},
            }
        ],
        "output_hash": out_hash,
        "result_hash": res_hash,
        "metadata": {},
        "created_at": "2026-05-04T00:00:08Z",
    }
    cost_summary = {
        "schema_version": "p0.v1",
        "estimated_cost_micros": 0,
        "actual_cost_micros": 0,
        "cost_source": "not_applicable",
        "cost_confidence": "not_applicable",
        "baseline_mode": "none",
        "baseline_cost_micros": None,
        "saving_ratio_bps": None,
        "primary_model_fallback_used": False,
        "primary_model_fallback_cost_micros": 0,
        "local_zero_cost_caveat": "Local tool execution has no provider bill.",
        "verifier_passed": True,
        "quality_status": "passed",
        "audit_status": "clean",
        "caveats": [],
    }
    host_summary = {
        "schema_version": "p0.v1",
        "work_unit_id": "wu_001",
        "run_id": "run_001",
        "status": "succeeded",
        "task_type": "url_check",
        "task_level": "L1",
        "verifier_status": "passed",
        "verifier_recommendation": "accept",
        "result_summary": "URL was reachable.",
        "artifact_refs": [],
        "duration_ms": 1000,
        "backend_class": "local_tool",
        "backend_id": "backend:url_check:v0",
        "worker_id": "wrk_local_01",
        "capacity_node_id": "capnode:tool:url_check:v0",
        "cost_summary": cost_summary,
        "warnings": [],
        "caveats": [],
        "fallback_used": False,
        "quarantine_status": "none",
        "retry_count": 0,
        "trace_ref": "trace_001",
        "generated_at": "2026-05-04T00:00:09Z",
    }
    return {
        "work_unit": work_unit,
        "work_unit_result_envelope": result_envelope,
        "capacity_node": capacity_node,
        "capacity_node_health": capacity_health,
        "capacity_profile": capacity_profile,
        "route_plan": route_plan,
        "route_candidate": route_candidate,
        "route_decision_trace": route_decision_trace,
        "task_analysis_report": task_analysis_report,
        "task_profile": task_profile,
        "policy_decision": policy_decision,
        "execution_attempt": attempt,
        "assignment": assignment,
        "backend_manifest": backend_manifest,
        "backend_health": backend_health,
        "usage_record": usage,
        "backend_error": backend_error,
        "verifier_report": verifier_report,
        "host_result_summary": host_summary,
        "host_cost_quality_summary": cost_summary,
    }


@pytest.mark.parametrize(("schema_name", "model"), SCHEMA_MODELS)
def test_payloads_validate_against_pydantic_and_json_schema(
    schema_name: str,
    model: type,
) -> None:
    payload = sample_payloads()[schema_name]

    dto = model.model_validate(payload)
    serialized = dto.model_dump(mode="json")

    _validate_with_json_schema(f"{schema_name}.schema.json", serialized)


def test_forbidden_nested_phase0_fields_are_rejected() -> None:
    payload = sample_payloads()["work_unit"]
    payload["inline_input"] = {"url": "https://example.com", "seller_id": "bad"}

    with pytest.raises(ValidationError):
        WorkUnit.model_validate(payload)


def test_money_like_fields_use_integer_micros() -> None:
    payloads = sample_payloads()

    for schema_name in ("usage_record", "host_cost_quality_summary"):
        payload = payloads[schema_name]
        for field_name, value in payload.items():
            if field_name.endswith("_micros") and value is not None:
                assert isinstance(value, int)
