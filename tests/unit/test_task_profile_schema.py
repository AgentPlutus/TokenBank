from __future__ import annotations

from tokenbank.core.canonical import canonical_json_hash
from tokenbank.models import CapacityProfile, RouteDecisionTrace, TaskProfile


def test_task_profile_capacity_profile_and_decision_trace_validate() -> None:
    task_profile = TaskProfile.model_validate(
        {
            "task_profile_id": "tp_wu_001_claim_extraction",
            "work_unit_id": "wu_001",
            "routebook_id": "tokenbank.base",
            "routebook_version": "1.0.0",
            "source": "deterministic",
            "task_family": "strong_reasoning",
            "task_type": "claim_extraction",
            "difficulty": "high",
            "risk_level": "L2",
            "privacy_level": "private",
            "context_size": "small",
            "latency_preference": "normal",
            "cost_preference": "balanced",
            "required_capabilities": [
                {
                    "capability": "strong_reasoning",
                    "min_score": 0.75,
                    "importance": "required",
                }
            ],
            "requires_tools": [],
            "requires_verifier_recipe_id": True,
            "success_criteria": ["factual_claims", "result_hash"],
            "ambiguity": {"status": "low", "unresolved_questions": []},
            "confidence": 0.82,
            "profile_reason_codes": ["deterministic_wp_rb1_profile"],
        }
    )
    capacity_profile = CapacityProfile.model_validate(
        {
            "capacity_profile_id": "cp_backend_claim_extraction_api_gateway_v0",
            "capacity_node_id": "capnode:api_gateway:claim_extraction:v0",
            "backend_id": "backend:claim_extraction:api_gateway:v0",
            "backend_class": "api_model_gateway",
            "ownership_scope": "user_local",
            "execution_boundary": "mac_control_plane",
            "availability_state": "available",
            "model_profile": {
                "provider_id": "control_plane_gateway",
                "model_id": "backend:claim_extraction:api_gateway:v0",
                "model_tier": "standard",
                "context_window_class": "unknown",
                "supports_structured_output": True,
                "supports_tool_calling": False,
                "wire_quirks_profile_id": None,
            },
            "capabilities": {
                "strong_reasoning": {"score": 0.8, "evidence": "declared"}
            },
            "cost": {"estimated_cost_micros": 1000, "cost_tier": "low"},
            "latency": {"p50_ms": None, "p95_ms": None},
            "quality_memory": {
                "verifier_pass_rate": None,
                "accepted_result_rate": None,
                "sample_size": 0,
            },
            "verified_for": [
                {
                    "task_type": "claim_extraction",
                    "verifier_recipe_id": "claim_extraction_v0",
                    "status": "declared",
                }
            ],
        }
    )
    trace = RouteDecisionTrace.model_validate(
        {
            "route_decision_id": "rd_rp_001",
            "route_plan_id": "rp_001",
            "work_unit_id": "wu_001",
            "routebook_id": "tokenbank.base",
            "routebook_version": "1.0.0",
            "task_profile_hash": canonical_json_hash(
                task_profile.model_dump(mode="json")
            ),
            "capacity_snapshot_hash": canonical_json_hash(
                [capacity_profile.model_dump(mode="json")]
            ),
            "selected_candidate_id": "route_claim_model_gateway",
            "candidate_scores": [
                {
                    "candidate_id": "route_claim_model_gateway",
                    "score": {"total": 1.0},
                    "hard_filter_results": {"policy_allowed": "pass"},
                    "reason_codes": ["selected_candidate"],
                }
            ],
            "rejected_candidates": [],
            "reason_codes": ["host_model_profiler_only"],
            "rule_ids": ["route_claim_model_gateway"],
            "user_summary": "TokenBank kept final route selection inside Core.",
        }
    )

    assert task_profile.task_type == "claim_extraction"
    assert capacity_profile.backend_class == "api_model_gateway"
    assert trace.selected_candidate_id == "route_claim_model_gateway"
