"""Routebook V1 host-safe route explanations."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from tokenbank.backends.registry import BackendRegistry
from tokenbank.config_runtime.loader import load_config_dir
from tokenbank.core.canonical import canonical_json_hash
from tokenbank.models.capacity_profile import CapacityProfile
from tokenbank.models.route_decision import (
    RouteDecisionTrace,
    RouteScoringReport,
)
from tokenbank.models.route_plan import RoutePlan
from tokenbank.models.task_analysis import TaskAnalysisReport
from tokenbank.models.task_profile import TaskProfile
from tokenbank.models.work_unit import WorkUnit
from tokenbank.routebook.loader import LoadedRoutebook, load_routebook_dir
from tokenbank.routebook.v1_loader import LoadedRoutebookV1, load_routebook_v1_dir
from tokenbank.router.capacity_profiles import capacity_profiles_for_candidates
from tokenbank.router.route_scorer import RouteScorer
from tokenbank.router.task_profiler import TaskProfiler


class RouteExplainer:
    """Build host-safe V1 profiles, analysis, and WP-RB3 scoring traces."""

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
        capacity_profiles = capacity_profiles_for_candidates(
            candidates=route_plan.candidates,
            backend_registry=self.backend_registry,
        )
        scoring_report = None
        if task_analysis_report is not None:
            scoring_report = RouteScorer(
                routebook=self.routebook,
                routebook_v1=self.routebook_v1,
                backend_registry=self.backend_registry,
            ).score(
                work_unit=work_unit,
                route_plan=route_plan,
                task_profile=task_profile,
                capacity_profiles=capacity_profiles,
                task_analysis_report=task_analysis_report,
            )
        decision_trace = self._decision_trace(
            work_unit=work_unit,
            route_plan=route_plan,
            task_profile=task_profile,
            capacity_profiles=capacity_profiles,
            task_analysis_report=task_analysis_report,
            scoring_report=scoring_report,
        )
        result = {
            "task_profile": task_profile.model_dump(mode="json"),
            "capacity_profiles": [
                profile.model_dump(mode="json")
                for profile in capacity_profiles
            ],
            "route_decision_trace": decision_trace.model_dump(mode="json"),
        }
        if scoring_report is not None:
            result["route_scoring_report"] = scoring_report.model_dump(mode="json")
            result["route_scoring_hash"] = canonical_json_hash(
                scoring_report.model_dump(mode="json")
            )
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

    def _decision_trace(
        self,
        *,
        work_unit: WorkUnit,
        route_plan: RoutePlan,
        task_profile: TaskProfile,
        capacity_profiles: list[CapacityProfile],
        task_analysis_report: TaskAnalysisReport | None,
        scoring_report: RouteScoringReport | None,
    ) -> RouteDecisionTrace:
        selected = (
            scoring_report.selected_candidate_id
            if scoring_report is not None
            else route_plan.selected_candidate_id
        )
        candidate_scores = (
            scoring_report.candidate_scores if scoring_report is not None else []
        )
        rejected = (
            scoring_report.rejected_candidates if scoring_report is not None else []
        )
        reason_codes = (
            [
                "host_model_profiler_only",
                "wp_rb3_route_scorer_applied",
                "selected_by_scored_routebook_candidate",
            ]
            if scoring_report is not None
            else [
                "host_model_profiler_only",
                "phase0_route_selection_unchanged",
                "selected_by_existing_routebook_priority",
            ]
        )
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
            reason_codes=reason_codes,
            rule_ids=[
                f"routebook:{self.routebook_v1.routebook_id}@{self.routebook_v1.version}",
                (
                    f"route_scorer:{self.routebook_v1.scoring['scorer_id']}"
                    f"@{self.routebook_v1.scoring['version']}"
                ),
                f"ontology:task_type_defaults:{work_unit.task_type}",
                f"verifier_mapping:{route_plan.verifier_recipe_id}",
                *[
                    f"candidate_rule:{candidate.route_candidate_id}"
                    for candidate in route_plan.candidates
                ],
            ],
            user_summary=(
                "TokenBank treated the host model as a profiler and used Core "
                "RouteScorer hard filters plus weighted scoring to rank private "
                "capacity. The scorer does not execute work, bypass policy, or "
                "call provider models."
            ),
        )


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
