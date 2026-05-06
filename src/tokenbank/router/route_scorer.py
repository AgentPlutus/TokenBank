"""Deterministic WP-RB3 route scoring."""

from __future__ import annotations

from dataclasses import dataclass

from tokenbank.backends.registry import BackendRegistry
from tokenbank.capacity.validators import (
    API_GATEWAY_BACKEND_CLASSES,
    CONTROL_PLANE_GATEWAY_WORKER_ID,
)
from tokenbank.models.backend import BackendManifest
from tokenbank.models.capacity_profile import CapacityProfile
from tokenbank.models.route_decision import (
    CandidateScore,
    CandidateScoreTrace,
    RejectedCandidateTrace,
    RouteScoringReport,
)
from tokenbank.models.route_plan import RouteCandidate, RoutePlan
from tokenbank.models.task_analysis import TaskAnalysisReport
from tokenbank.models.task_profile import TaskProfile
from tokenbank.models.work_unit import WorkUnit
from tokenbank.routebook.loader import LoadedRoutebook
from tokenbank.routebook.v1_loader import LoadedRoutebookV1

PASSING_HARD_FILTER_STATUSES = {"pass", "not_required", "pending_policy_decision"}
TASK_LEVEL_ORDER = {"L0": 0, "L1": 1, "L2": 2, "L3": 3}
DIFFICULTY_ORDER = {
    "trivial": 0,
    "easy": 1,
    "medium": 2,
    "high": 3,
    "expert": 4,
}
MODEL_TIER_ORDER = {
    "weak_general": 0,
    "standard": 1,
    "strong": 2,
    "frontier": 3,
    "specialist": 3,
}
DEFAULT_SCORE_WEIGHTS = {
    "capability_fit": 0.30,
    "policy_fit": 0.25,
    "quality_fit": 0.20,
    "cost_fit": 0.10,
    "latency_fit": 0.05,
    "trust_fit": 0.10,
}


@dataclass(frozen=True)
class RouteScorer:
    """Score RoutePlan candidates without executing work or mutating state."""

    routebook: LoadedRoutebook
    routebook_v1: LoadedRoutebookV1
    backend_registry: BackendRegistry

    def score(
        self,
        *,
        work_unit: WorkUnit,
        route_plan: RoutePlan,
        task_profile: TaskProfile,
        capacity_profiles: list[CapacityProfile],
        task_analysis_report: TaskAnalysisReport,
    ) -> RouteScoringReport:
        score_weights = _score_weights(self.routebook_v1)
        profiles_by_backend_id = {
            profile.backend_id: profile
            for profile in capacity_profiles
        }
        candidate_by_id = {
            candidate.route_candidate_id: candidate
            for candidate in route_plan.candidates
        }
        candidate_scores: list[CandidateScoreTrace] = []

        for candidate in route_plan.candidates:
            backend = self.backend_registry.get(candidate.backend_id)
            capacity_profile = profiles_by_backend_id[candidate.backend_id]
            hard_filter_results = self._hard_filter_results(
                work_unit=work_unit,
                route_plan=route_plan,
                candidate=candidate,
                capacity_profile=capacity_profile,
                backend=backend,
                task_analysis_report=task_analysis_report,
            )
            hard_filter_decision = (
                "pass"
                if _hard_filters_pass(hard_filter_results)
                else "fail"
            )
            score, weighted = self._candidate_score(
                candidate=candidate,
                hard_filter_decision=hard_filter_decision,
                hard_filter_results=hard_filter_results,
                task_profile=task_profile,
                capacity_profile=capacity_profile,
                task_analysis_report=task_analysis_report,
                score_weights=score_weights,
            )
            candidate_scores.append(
                CandidateScoreTrace(
                    candidate_id=candidate.route_candidate_id,
                    score=score,
                    hard_filter_decision=hard_filter_decision,  # type: ignore[arg-type]
                    hard_filter_results=hard_filter_results,
                    weighted_components=weighted,
                    reason_codes=self._candidate_reason_codes(
                        candidate=candidate,
                        hard_filter_results=hard_filter_results,
                        hard_filter_decision=hard_filter_decision,
                        task_profile=task_profile,
                        capacity_profile=capacity_profile,
                        task_analysis_report=task_analysis_report,
                    ),
                )
            )

        ranked_scores = _ranked_scores(
            candidate_scores=candidate_scores,
            candidate_by_id=candidate_by_id,
        )
        ranked_scores_by_id = {
            score.candidate_id: score.model_copy(update={"rank": rank})
            for rank, score in enumerate(ranked_scores, start=1)
        }
        candidate_scores = [
            ranked_scores_by_id[score.candidate_id]
            for score in candidate_scores
        ]
        passing_scores = [
            score
            for score in ranked_scores
            if score.hard_filter_decision == "pass"
        ]
        if passing_scores:
            selected_candidate_id = passing_scores[0].candidate_id
            selection_status = "selected_highest_scoring_candidate"
            reason_codes = [
                "wp_rb3_route_scorer_applied",
                "selected_highest_scoring_passing_candidate",
            ]
        else:
            selected_candidate_id = route_plan.selected_candidate_id
            selection_status = "no_passing_candidate_keep_existing_selection"
            reason_codes = [
                "wp_rb3_route_scorer_applied",
                "no_passing_candidate",
                "kept_existing_route_plan_selection",
            ]

        return RouteScoringReport(
            route_scoring_id=f"rs_{route_plan.route_plan_id}",
            route_plan_id=route_plan.route_plan_id,
            work_unit_id=work_unit.work_unit_id,
            routebook_id=self.routebook_v1.routebook_id,
            routebook_version=self.routebook_v1.version,
            scorer_id=str(self.routebook_v1.scoring["scorer_id"]),
            scorer_version=str(self.routebook_v1.scoring["version"]),
            baseline_selected_candidate_id=route_plan.selected_candidate_id,
            selected_candidate_id=selected_candidate_id,
            selection_status=selection_status,  # type: ignore[arg-type]
            score_weights=score_weights,
            candidate_scores=candidate_scores,
            rejected_candidates=_rejected_candidates(
                selected_candidate_id=selected_candidate_id,
                candidate_scores=candidate_scores,
            ),
            reason_codes=reason_codes,
        )

    def _hard_filter_results(
        self,
        *,
        work_unit: WorkUnit,
        route_plan: RoutePlan,
        candidate: RouteCandidate,
        capacity_profile: CapacityProfile,
        backend: BackendManifest,
        task_analysis_report: TaskAnalysisReport,
    ) -> dict[str, str]:
        effective_task_level = task_analysis_report.effective_task_level
        effective_privacy_level = task_analysis_report.effective_privacy_level
        requires_verifier = effective_task_level in {"L1", "L2", "L3"}
        forbidden_classes = set(
            self.routebook.forbidden_routes.get("forbidden_backend_classes", [])
        )
        return {
            "preflight_allow": "pass"
            if task_analysis_report.preflight_decision == "allow"
            else "fail",
            "task_type_supported": "pass"
            if work_unit.task_type in backend.supported_task_types
            else "fail",
            "privacy_boundary_allowed": "pass"
            if effective_privacy_level in backend.allowed_privacy_levels
            else "fail",
            "verifier_available_for_L1_L2_L3": "pass"
            if not requires_verifier or candidate.verifier_recipe_id
            else "fail",
            "backend_class_allowed": "pass"
            if candidate.backend_class not in forbidden_classes
            else "fail",
            "worker_direct_api_model_forbidden": _api_gateway_boundary_result(
                candidate
            ),
            "credential_boundary_valid": "pass"
            if not task_analysis_report.privacy_scan.raw_secret_detected
            else "fail",
            "capacity_health_not_quarantined": "pass"
            if capacity_profile.availability_state != "unavailable"
            else "fail",
            "task_level_not_downgraded": "pass"
            if TASK_LEVEL_ORDER[route_plan.task_level]
            >= TASK_LEVEL_ORDER[effective_task_level]
            else "fail",
            "peer_negotiation_complete_for_peer_capacity": "not_required"
            if capacity_profile.ownership_scope != "peer"
            else "fail",
        }

    def _candidate_score(
        self,
        *,
        candidate: RouteCandidate,
        hard_filter_decision: str,
        hard_filter_results: dict[str, str],
        task_profile: TaskProfile,
        capacity_profile: CapacityProfile,
        task_analysis_report: TaskAnalysisReport,
        score_weights: dict[str, float],
    ) -> tuple[CandidateScore, dict[str, float]]:
        capability_fit = _capability_fit(task_profile, capacity_profile)
        policy_fit = 1.0 if hard_filter_decision == "pass" else 0.0
        quality_fit = _quality_fit(task_profile, capacity_profile)
        cost_fit = _cost_fit(candidate, task_profile=task_profile)
        latency_fit = _latency_fit(capacity_profile, task_profile=task_profile)
        trust_fit = _trust_fit(capacity_profile)
        uncertainty_penalty = _uncertainty_penalty(
            capacity_profile=capacity_profile,
            task_analysis_report=task_analysis_report,
            hard_filter_results=hard_filter_results,
        )
        weighted = {
            "capability_fit": round(
                capability_fit * score_weights["capability_fit"],
                4,
            ),
            "policy_fit": round(policy_fit * score_weights["policy_fit"], 4),
            "quality_fit": round(quality_fit * score_weights["quality_fit"], 4),
            "cost_fit": round(cost_fit * score_weights["cost_fit"], 4),
            "latency_fit": round(latency_fit * score_weights["latency_fit"], 4),
            "trust_fit": round(trust_fit * score_weights["trust_fit"], 4),
        }
        priority_penalty = min(0.08, (candidate.priority - 1) * 0.04)
        total = max(
            0.0,
            min(1.0, sum(weighted.values()) - uncertainty_penalty - priority_penalty),
        )
        if hard_filter_decision == "fail":
            total = 0.0
        return (
            CandidateScore(
                total=round(total, 4),
                capability_fit=round(capability_fit, 4),
                policy_fit=policy_fit,
                quality_fit=round(quality_fit, 4),
                cost_fit=round(cost_fit, 4),
                latency_fit=round(latency_fit, 4),
                trust_fit=round(trust_fit, 4),
                uncertainty_penalty=round(uncertainty_penalty, 4),
            ),
            weighted,
        )

    def _candidate_reason_codes(
        self,
        *,
        candidate: RouteCandidate,
        hard_filter_results: dict[str, str],
        hard_filter_decision: str,
        task_profile: TaskProfile,
        capacity_profile: CapacityProfile,
        task_analysis_report: TaskAnalysisReport,
    ) -> list[str]:
        reason_codes = [
            "scorer:wp_rb3",
            f"backend_class:{candidate.backend_class}",
            f"priority:{candidate.priority}",
            f"hard_filters:{hard_filter_decision}",
        ]
        if candidate.verifier_recipe_id:
            reason_codes.append("verifier_recipe_available")
        missing = _missing_required_capabilities(task_profile, capacity_profile)
        if missing:
            reason_codes.extend(
                f"missing_capability:{capability}"
                for capability in missing
            )
        else:
            reason_codes.append("matches_required_capabilities")
        if task_analysis_report.complexity.requires_strong_reasoning:
            reason_codes.append("strong_reasoning_required")
        if candidate.estimated_cost_micros == 0:
            reason_codes.append("zero_internal_cost_estimate")
        failed_filters = [
            name
            for name, status in hard_filter_results.items()
            if status not in PASSING_HARD_FILTER_STATUSES
        ]
        reason_codes.extend(f"hard_filter_failed:{name}" for name in failed_filters)
        return reason_codes


def apply_scored_selection(
    *,
    route_plan: RoutePlan,
    scoring_report: RouteScoringReport,
) -> RoutePlan:
    return route_plan.model_copy(
        update={"selected_candidate_id": scoring_report.selected_candidate_id}
    )


def _score_weights(routebook_v1: LoadedRoutebookV1) -> dict[str, float]:
    weights = dict(routebook_v1.scoring.get("score_weights", {}))
    result = {
        component: float(weights.get(component, default_weight))
        for component, default_weight in DEFAULT_SCORE_WEIGHTS.items()
    }
    total = sum(result.values())
    if total <= 0:
        return DEFAULT_SCORE_WEIGHTS
    return {
        component: round(weight / total, 4)
        for component, weight in result.items()
    }


def _hard_filters_pass(hard_filter_results: dict[str, str]) -> bool:
    return all(
        status in PASSING_HARD_FILTER_STATUSES
        for status in hard_filter_results.values()
    )


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
        if capability is None:
            scores.append(0.0)
            continue
        scores.append(min(1.0, capability.score / max(required.min_score, 0.01)))
    return sum(scores) / len(scores)


def _quality_fit(
    task_profile: TaskProfile,
    capacity_profile: CapacityProfile,
) -> float:
    tier_fit = _model_or_backend_tier_fit(task_profile, capacity_profile)
    verifier_fit = 0.85 if any(
        verified.task_type == task_profile.task_type
        for verified in capacity_profile.verified_for
    ) else 0.55
    memory = capacity_profile.quality_memory
    if memory.sample_size > 0 and memory.verifier_pass_rate is not None:
        memory_fit = memory.verifier_pass_rate
    else:
        memory_fit = 0.70
    return 0.55 * tier_fit + 0.25 * verifier_fit + 0.20 * memory_fit


def _model_or_backend_tier_fit(
    task_profile: TaskProfile,
    capacity_profile: CapacityProfile,
) -> float:
    difficulty = DIFFICULTY_ORDER.get(task_profile.difficulty, 2)
    if capacity_profile.model_profile is None:
        if difficulty <= 1 and "deterministic_local" in capacity_profile.capabilities:
            return 0.95
        if difficulty <= 2 and capacity_profile.backend_class == "browser_fetch":
            return 0.80
        return 0.45
    model_tier = capacity_profile.model_profile.model_tier
    tier = MODEL_TIER_ORDER.get(model_tier, 1)
    required_tier = 0 if difficulty <= 1 else 1 if difficulty <= 2 else 2
    if tier >= required_tier:
        return min(1.0, 0.82 + (tier - required_tier) * 0.07)
    return max(0.25, 0.72 - (required_tier - tier) * 0.18)


def _cost_fit(candidate: RouteCandidate, *, task_profile: TaskProfile) -> float:
    if candidate.estimated_cost_micros == 0:
        return 1.0
    if candidate.estimated_cost_micros <= 1_000:
        base = 0.80
    elif candidate.estimated_cost_micros <= 10_000:
        base = 0.65
    elif candidate.estimated_cost_micros <= 100_000:
        base = 0.45
    else:
        base = 0.25
    if task_profile.cost_preference == "cost_first":
        return max(0.0, base - 0.10)
    if task_profile.cost_preference == "quality_first":
        return min(1.0, base + 0.05)
    return base


def _latency_fit(
    capacity_profile: CapacityProfile,
    *,
    task_profile: TaskProfile,
) -> float:
    if capacity_profile.availability_state == "degraded":
        return 0.45
    if capacity_profile.latency.p50_ms is None:
        return 0.58 if task_profile.latency_preference == "high" else 0.65
    if capacity_profile.latency.p50_ms <= 500:
        return 0.95
    if capacity_profile.latency.p50_ms <= 2_000:
        return 0.75
    return 0.45


def _trust_fit(capacity_profile: CapacityProfile) -> float:
    if capacity_profile.ownership_scope == "user_local":
        return 1.0
    if capacity_profile.ownership_scope == "system":
        return 0.90
    if capacity_profile.ownership_scope == "team_local":
        return 0.85
    return 0.40


def _uncertainty_penalty(
    *,
    capacity_profile: CapacityProfile,
    task_analysis_report: TaskAnalysisReport,
    hard_filter_results: dict[str, str],
) -> float:
    penalty = 0.03
    penalty += max(0.0, 1.0 - task_analysis_report.confidence) * 0.12
    if capacity_profile.latency.p50_ms is None:
        penalty += 0.03
    if capacity_profile.quality_memory.sample_size == 0:
        penalty += 0.04
    if any(
        status == "pending_policy_decision"
        for status in hard_filter_results.values()
    ):
        penalty += 0.03
    return min(0.25, penalty)


def _ranked_scores(
    *,
    candidate_scores: list[CandidateScoreTrace],
    candidate_by_id: dict[str, RouteCandidate],
) -> list[CandidateScoreTrace]:
    return sorted(
        candidate_scores,
        key=lambda score: (
            0 if score.hard_filter_decision == "pass" else 1,
            -score.score.total,
            candidate_by_id[score.candidate_id].priority,
            candidate_by_id[score.candidate_id].estimated_cost_micros,
            score.candidate_id,
        ),
    )


def _rejected_candidates(
    *,
    selected_candidate_id: str,
    candidate_scores: list[CandidateScoreTrace],
) -> list[RejectedCandidateTrace]:
    rejected: list[RejectedCandidateTrace] = []
    for score in candidate_scores:
        if score.candidate_id == selected_candidate_id:
            continue
        reason_codes = []
        if score.hard_filter_decision == "fail":
            reason_codes.append("hard_filter_failed")
        else:
            reason_codes.append("lower_score_than_selected")
        reason_codes.extend(
            reason
            for reason in score.reason_codes
            if reason.startswith("hard_filter_failed:")
        )
        rejected.append(
            RejectedCandidateTrace(
                candidate_id=score.candidate_id,
                reason_codes=reason_codes,
            )
        )
    return rejected


def _missing_required_capabilities(
    task_profile: TaskProfile,
    capacity_profile: CapacityProfile,
) -> list[str]:
    return [
        required.capability
        for required in task_profile.required_capabilities
        if required.capability not in capacity_profile.capabilities
    ]
