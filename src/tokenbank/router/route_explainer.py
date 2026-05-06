"""Routebook V1 host-safe route explanations."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from tokenbank.backends.registry import BackendRegistry
from tokenbank.capacity.validators import (
    API_GATEWAY_BACKEND_CLASSES,
    CONTROL_PLANE_GATEWAY_WORKER_ID,
)
from tokenbank.config_runtime.loader import load_config_dir
from tokenbank.core.canonical import canonical_json_hash
from tokenbank.models.backend import BackendManifest
from tokenbank.models.capacity_profile import (
    CapacityCapability,
    CapacityCostProfile,
    CapacityLatencyProfile,
    CapacityProfile,
    CapacityQualityMemory,
    ModelProfile,
    VerifiedForTask,
)
from tokenbank.models.route_decision import (
    CandidateScore,
    CandidateScoreTrace,
    RejectedCandidateTrace,
    RouteDecisionTrace,
)
from tokenbank.models.route_plan import RouteCandidate, RoutePlan
from tokenbank.models.task_analysis import TaskAnalysisReport
from tokenbank.models.task_profile import TaskProfile
from tokenbank.models.work_unit import WorkUnit
from tokenbank.routebook.loader import LoadedRoutebook, load_routebook_dir
from tokenbank.routebook.v1_loader import LoadedRoutebookV1, load_routebook_v1_dir
from tokenbank.router.task_profiler import TaskProfiler


class RouteExplainer:
    """Build explanatory V1 profiles without changing route selection."""

    def __init__(
        self,
        *,
        routebook: LoadedRoutebook,
        routebook_v1: LoadedRoutebookV1,
        backend_registry: BackendRegistry,
    ):
        self.routebook = routebook
        self.routebook_v1 = routebook_v1
        self.backend_registry = backend_registry
        self.task_profiler = TaskProfiler(
            routebook=routebook,
            routebook_v1=routebook_v1,
        )

    @classmethod
    def from_dirs(
        cls,
        *,
        config_dir: str | Path = "config",
        routebook_dir: str | Path = "routebook",
        routebook_v1_dir: str | Path = "packs/base-routing/routebook",
    ) -> RouteExplainer:
        config = load_config_dir(config_dir)
        return cls(
            routebook=load_routebook_dir(routebook_dir),
            routebook_v1=load_routebook_v1_dir(routebook_v1_dir),
            backend_registry=BackendRegistry.from_config(config),
        )

    def explain(
        self,
        *,
        work_unit: WorkUnit,
        route_plan: RoutePlan,
        task_analysis_report: TaskAnalysisReport | None = None,
    ) -> dict[str, Any]:
        task_profile = self._task_profile(work_unit=work_unit, route_plan=route_plan)
        capacity_profiles = [
            self._capacity_profile(candidate)
            for candidate in route_plan.candidates
        ]
        decision_trace = self._decision_trace(
            work_unit=work_unit,
            route_plan=route_plan,
            task_profile=task_profile,
            capacity_profiles=capacity_profiles,
            task_analysis_report=task_analysis_report,
        )
        result = {
            "task_profile": task_profile.model_dump(mode="json"),
            "capacity_profiles": [
                profile.model_dump(mode="json")
                for profile in capacity_profiles
            ],
            "route_decision_trace": decision_trace.model_dump(mode="json"),
        }
        if task_analysis_report is not None:
            result["task_analysis_report"] = task_analysis_report.model_dump(
                mode="json"
            )
            result["task_analysis_hash"] = canonical_json_hash(
                task_analysis_report.model_dump(mode="json")
            )
        return result

    def _task_profile(
        self,
        *,
        work_unit: WorkUnit,
        route_plan: RoutePlan,
    ) -> TaskProfile:
        return self.task_profiler.profile(work_unit=work_unit, route_plan=route_plan)

    def _capacity_profile(self, candidate: RouteCandidate) -> CapacityProfile:
        backend = self.backend_registry.get(candidate.backend_id)
        capability_names = _backend_capabilities(backend, candidate)
        return CapacityProfile(
            capacity_profile_id=f"cp_{_safe_id(candidate.backend_id)}",
            capacity_node_id=candidate.capacity_node_id,
            backend_id=candidate.backend_id,
            backend_class=candidate.backend_class,
            ownership_scope="user_local",
            execution_boundary=backend.execution_location,
            availability_state="available" if backend.health is None else _availability(
                backend.health.status
            ),
            model_profile=_model_profile(backend),
            capabilities={
                capability: CapacityCapability(score=0.80, evidence="declared")
                for capability in capability_names
            },
            cost=CapacityCostProfile(
                estimated_cost_micros=candidate.estimated_cost_micros,
                cost_tier=_cost_tier(candidate.estimated_cost_micros),
            ),
            latency=CapacityLatencyProfile(
                p50_ms=backend.health.latency_ms if backend.health else None,
                p95_ms=None,
            ),
            quality_memory=CapacityQualityMemory(sample_size=0),
            verified_for=[
                VerifiedForTask(
                    task_type=task_type,
                    verifier_recipe_id=candidate.verifier_recipe_id or "none",
                    status="declared",
                )
                for task_type in backend.supported_task_types
                if candidate.verifier_recipe_id is not None
            ],
        )

    def _decision_trace(
        self,
        *,
        work_unit: WorkUnit,
        route_plan: RoutePlan,
        task_profile: TaskProfile,
        capacity_profiles: list[CapacityProfile],
        task_analysis_report: TaskAnalysisReport | None,
    ) -> RouteDecisionTrace:
        selected = route_plan.selected_candidate_id
        profiles_by_backend_id = {
            profile.backend_id: profile
            for profile in capacity_profiles
        }
        candidate_scores = []
        for candidate in route_plan.candidates:
            capacity_profile = profiles_by_backend_id[candidate.backend_id]
            backend = self.backend_registry.get(candidate.backend_id)
            hard_filter_results = _hard_filter_results(
                work_unit=work_unit,
                route_plan=route_plan,
                candidate=candidate,
                capacity_profile=capacity_profile,
                backend=backend,
            )
            candidate_scores.append(
                CandidateScoreTrace(
                    candidate_id=candidate.route_candidate_id,
                    score=_candidate_score(
                        candidate,
                        hard_filter_results=hard_filter_results,
                        task_profile=task_profile,
                        capacity_profile=capacity_profile,
                    ),
                    hard_filter_results=hard_filter_results,
                    reason_codes=_candidate_reason_codes(
                        candidate,
                        selected_candidate_id=selected,
                        task_profile=task_profile,
                        capacity_profile=capacity_profile,
                    ),
                )
            )
        rejected = [
            RejectedCandidateTrace(
                candidate_id=candidate.route_candidate_id,
                reason_codes=[
                    "lower_priority_routebook_candidate",
                    "available_as_fallback_only",
                ],
            )
            for candidate in route_plan.candidates
            if candidate.route_candidate_id != selected
        ]
        return RouteDecisionTrace(
            route_decision_id=f"rd_{route_plan.route_plan_id}",
            route_plan_id=route_plan.route_plan_id,
            work_unit_id=work_unit.work_unit_id,
            routebook_id=self.routebook_v1.routebook_id,
            routebook_version=self.routebook_v1.version,
            task_analysis_hash=canonical_json_hash(
                task_analysis_report.model_dump(mode="json")
            )
            if task_analysis_report is not None
            else None,
            task_profile_hash=canonical_json_hash(task_profile.model_dump(mode="json")),
            capacity_snapshot_hash=canonical_json_hash(
                [
                    profile.model_dump(mode="json")
                    for profile in capacity_profiles
                ]
            ),
            selected_candidate_id=selected,
            candidate_scores=candidate_scores,
            rejected_candidates=rejected,
            estimate_summary=_estimate_summary(task_analysis_report),
            reason_codes=[
                "host_model_profiler_only",
                "phase0_route_selection_unchanged",
                "selected_by_existing_routebook_priority",
            ],
            rule_ids=[
                f"routebook:{self.routebook_v1.routebook_id}@{self.routebook_v1.version}",
                f"ontology:task_type_defaults:{work_unit.task_type}",
                f"verifier_mapping:{route_plan.verifier_recipe_id}",
                *[
                    f"candidate_rule:{candidate.route_candidate_id}"
                    for candidate in route_plan.candidates
                ],
            ],
            user_summary=(
                "TokenBank treated the host model as a profiler and kept final "
                "route selection inside Core. The selected candidate follows the "
                "existing Phase 0 routebook priority and verifier guardrails, "
                "so a weak host model can describe the task without executing it."
            ),
        )


def _backend_capabilities(
    backend: BackendManifest,
    candidate: RouteCandidate,
) -> list[str]:
    capabilities: set[str] = set()
    if candidate.backend_class in {"local_tool", "local_script"}:
        capabilities.update({"deterministic_local", "low_cost"})
    if candidate.backend_class == "browser_fetch":
        capabilities.update({"browser_fetch", "data_extraction"})
    if candidate.backend_class in {"api_model_gateway", "primary_model_gateway"}:
        capabilities.update({"structured_output", "fast_reasoning"})
    if "claim_extraction" in backend.supported_task_types:
        capabilities.update(
            {"strong_reasoning", "structured_output", "data_extraction"}
        )
    if "topic_classification" in backend.supported_task_types:
        capabilities.update({"structured_output", "fast_reasoning"})
    if "url_check" in backend.supported_task_types:
        capabilities.update({"browser_fetch", "deterministic_local"})
    if "dedup" in backend.supported_task_types:
        capabilities.update({"deterministic_local", "data_extraction"})
    if "webpage_extraction" in backend.supported_task_types:
        capabilities.update({"browser_fetch", "data_extraction", "structured_output"})
    return sorted(capabilities or {"private_data_safe"})


def _estimate_summary(
    task_analysis_report: TaskAnalysisReport | None,
) -> dict[str, object]:
    if task_analysis_report is None:
        return {}
    return {
        "task_analysis_id": task_analysis_report.task_analysis_id,
        "estimated_input_tokens": (
            task_analysis_report.token_estimate.estimated_input_tokens
        ),
        "estimated_output_tokens": (
            task_analysis_report.token_estimate.estimated_output_tokens
        ),
        "estimated_total_tokens": (
            task_analysis_report.token_estimate.estimated_total_tokens
        ),
        "expected_cost_micros": (
            task_analysis_report.cost_estimate.expected_cost_micros
        ),
        "effective_task_level": task_analysis_report.effective_task_level,
        "effective_privacy_level": task_analysis_report.effective_privacy_level,
        "preflight_decision": task_analysis_report.preflight_decision,
        "confidence": task_analysis_report.confidence,
    }


def _model_profile(backend: BackendManifest) -> ModelProfile | None:
    if backend.backend_class not in {"api_model_gateway", "primary_model_gateway"}:
        return None
    return ModelProfile(
        provider_id="control_plane_gateway",
        model_id=backend.backend_id,
        model_tier="standard",
        context_window_class="unknown",
        supports_structured_output=True,
        supports_tool_calling=False,
        wire_quirks_profile_id=None,
    )


def _candidate_score(
    candidate: RouteCandidate,
    *,
    hard_filter_results: dict[str, str],
    task_profile: TaskProfile,
    capacity_profile: CapacityProfile,
) -> CandidateScore:
    capability_fit = _capability_fit(task_profile, capacity_profile)
    policy_fit = 0.0 if "fail" in hard_filter_results.values() else 1.0
    quality_fit = max(0.40, 0.70 - ((candidate.priority - 1) * 0.10))
    cost_fit = 1.0 if candidate.estimated_cost_micros == 0 else 0.60
    latency_fit = 0.60 if capacity_profile.latency.p50_ms is None else 0.75
    trust_fit = 1.0 if capacity_profile.ownership_scope == "user_local" else 0.50
    total = (
        0.35 * capability_fit
        + 0.20 * policy_fit
        + 0.15 * quality_fit
        + 0.10 * cost_fit
        + 0.05 * latency_fit
        + 0.15 * trust_fit
    )
    return CandidateScore(
        total=round(total, 4),
        capability_fit=round(capability_fit, 4),
        policy_fit=policy_fit,
        quality_fit=round(quality_fit, 4),
        cost_fit=cost_fit,
        latency_fit=latency_fit,
        trust_fit=trust_fit,
        uncertainty_penalty=0.0,
    )


def _hard_filter_results(
    *,
    work_unit: WorkUnit,
    route_plan: RoutePlan,
    candidate: RouteCandidate,
    capacity_profile: CapacityProfile,
    backend: BackendManifest,
) -> dict[str, str]:
    requires_verifier = route_plan.task_level in {"L1", "L2", "L3"}
    return {
        "policy_allowed": "pending_policy_decision",
        "privacy_boundary_allowed": "pass"
        if work_unit.privacy_level in backend.allowed_privacy_levels
        else "fail",
        "verifier_available_for_L1_L2_L3": "pass"
        if not requires_verifier or candidate.verifier_recipe_id
        else "fail",
        "backend_class_allowed": "pass",
        "worker_direct_api_model_forbidden": _api_gateway_boundary_result(candidate),
        "credential_boundary_valid": "pass",
        "capacity_health_not_quarantined": "pass"
        if capacity_profile.availability_state != "unavailable"
        else "fail",
        "task_level_not_downgraded": "pass"
        if work_unit.task_level == route_plan.task_level
        else "fail",
        "peer_negotiation_complete_for_peer_capacity": "not_required"
        if capacity_profile.ownership_scope != "peer"
        else "fail",
    }


def _api_gateway_boundary_result(candidate: RouteCandidate) -> str:
    if candidate.backend_class not in API_GATEWAY_BACKEND_CLASSES:
        return "pass"
    worker_id = candidate.worker_selector.get("worker_id")
    if worker_id == CONTROL_PLANE_GATEWAY_WORKER_ID:
        return "pass"
    return "fail"


def _capability_fit(
    task_profile: TaskProfile,
    capacity_profile: CapacityProfile,
) -> float:
    if not task_profile.required_capabilities:
        return 1.0
    scores: list[float] = []
    for required in task_profile.required_capabilities:
        capability = capacity_profile.capabilities.get(required.capability)
        scores.append(capability.score if capability is not None else 0.0)
    return sum(scores) / len(scores)


def _candidate_reason_codes(
    candidate: RouteCandidate,
    *,
    selected_candidate_id: str,
    task_profile: TaskProfile,
    capacity_profile: CapacityProfile,
) -> list[str]:
    reason_codes = [
        f"backend_class:{candidate.backend_class}",
        f"priority:{candidate.priority}",
    ]
    if candidate.route_candidate_id == selected_candidate_id:
        reason_codes.append("selected_by_existing_routebook_priority")
    else:
        reason_codes.append("fallback_or_lower_priority_candidate")
    if candidate.verifier_recipe_id:
        reason_codes.append("verifier_recipe_available")
    missing = [
        required.capability
        for required in task_profile.required_capabilities
        if required.capability not in capacity_profile.capabilities
    ]
    if missing:
        reason_codes.extend(
            f"missing_capability:{capability}"
            for capability in missing
        )
    else:
        reason_codes.append("matches_required_capabilities")
    return reason_codes


def _safe_id(value: str) -> str:
    return value.replace(":", "_").replace("/", "_").replace(".", "_")


def _cost_tier(estimated_cost_micros: int) -> str:
    if estimated_cost_micros == 0:
        return "free"
    if estimated_cost_micros <= 10_000:
        return "low"
    if estimated_cost_micros <= 100_000:
        return "medium"
    return "high"


def _availability(status: str) -> str:
    if status == "healthy":
        return "available"
    if status == "degraded":
        return "degraded"
    if status == "unhealthy":
        return "unavailable"
    return "unknown"
