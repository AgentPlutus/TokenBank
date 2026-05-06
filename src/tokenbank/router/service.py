"""RouterService for deterministic RoutePlan generation."""

from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Any

from tokenbank.backends.resolver import BackendResolver
from tokenbank.config_runtime.loader import load_config_dir
from tokenbank.core.canonical import canonical_json_dumps
from tokenbank.models.route_plan import RoutePlan
from tokenbank.models.work_unit import WorkUnit
from tokenbank.routebook.loader import LoadedRoutebook, load_routebook_dir
from tokenbank.routebook.v1_loader import LoadedRoutebookV1, load_routebook_v1_dir
from tokenbank.router.candidate_generator import CandidateGenerator
from tokenbank.router.capacity_profiles import capacity_profiles_for_candidates
from tokenbank.router.classifier import TaskClassifier
from tokenbank.router.normalizer import RoutePlanNormalizer
from tokenbank.router.route_plan_validator import RoutePlanValidator
from tokenbank.router.route_scorer import RouteScorer, apply_scored_selection
from tokenbank.router.task_analyzer import TaskAnalyzer
from tokenbank.router.task_profiler import TaskProfiler


class RouterService:
    """Build RoutePlan objects without executing or assigning work."""

    def __init__(
        self,
        *,
        routebook: LoadedRoutebook,
        backend_resolver: BackendResolver,
        routebook_v1: LoadedRoutebookV1 | None = None,
        loaded_config_root: Path | None = None,
    ):
        self.routebook = routebook
        self.backend_resolver = backend_resolver
        self.routebook_v1 = routebook_v1
        self.loaded_config_root = loaded_config_root
        self.classifier = TaskClassifier(routebook)
        self.candidate_generator = CandidateGenerator(
            routebook=routebook,
            backend_resolver=backend_resolver,
        )
        self.normalizer = RoutePlanNormalizer()
        self.validator = RoutePlanValidator(
            routebook=routebook,
            backend_registry=backend_resolver.backend_registry,
        )

    @classmethod
    def from_dirs(
        cls,
        *,
        config_dir: str | Path = "config",
        routebook_dir: str | Path = "routebook",
        routebook_v1_dir: str | Path | None = None,
    ) -> RouterService:
        config = load_config_dir(config_dir)
        v1_dir = (
            Path(routebook_v1_dir)
            if routebook_v1_dir is not None
            else config.root.parent / "packs" / "base-routing" / "routebook"
        )
        return cls(
            routebook=load_routebook_dir(routebook_dir),
            backend_resolver=BackendResolver.from_config(config),
            routebook_v1=load_routebook_v1_dir(v1_dir) if v1_dir.exists() else None,
            loaded_config_root=config.root,
        )

    def plan_route(
        self,
        work_unit: dict[str, Any],
        *,
        persist_conn: sqlite3.Connection | None = None,
    ) -> RoutePlan:
        task_level = self.classifier.classify(work_unit)
        candidates = self.candidate_generator.generate(
            work_unit=work_unit,
            task_level=task_level,
        )
        if not candidates:
            raise ValueError(
                f"no route candidates for task_type: {work_unit['task_type']}"
            )

        task_type = str(work_unit["task_type"])
        route_plan = RoutePlan(
            route_plan_id=f"rp_{work_unit['work_unit_id']}_{task_type}",
            work_unit_id=str(work_unit["work_unit_id"]),
            task_type=task_type,
            task_level=task_level,  # type: ignore[arg-type]
            candidates=candidates,
            selected_candidate_id=candidates[0].route_candidate_id,
            verifier_recipe_id=self.routebook.verifier_mapping[task_type],
            risk_level=self._risk_level(task_level),  # type: ignore[arg-type]
            policy_hints=list(self.routebook.policy_hints.get(task_type, [])),
        )
        normalized = self.normalizer.normalize(route_plan)
        validated = self.validator.validate(normalized)
        validated = self._apply_scored_selection(
            work_unit=work_unit,
            task_level=task_level,
            route_plan=validated,
        )
        if persist_conn is not None:
            persist_route_plan(persist_conn, validated)
        return validated

    def _risk_level(self, task_level: str) -> str:
        return str(
            self.routebook.task_levels.get(task_level, {}).get("risk_level", "low")
        )

    def _apply_scored_selection(
        self,
        *,
        work_unit: dict[str, Any],
        task_level: str,
        route_plan: RoutePlan,
    ) -> RoutePlan:
        if self.routebook_v1 is None or self.loaded_config_root is None:
            return route_plan
        work_unit_model = WorkUnit.model_validate(
            {
                **work_unit,
                "task_level": task_level,
                "inline_input": work_unit.get("inline_input", {}),
            }
        )
        task_analysis_report = TaskAnalyzer.from_dirs(
            config_dir=self.loaded_config_root,
            routebook_v1_dir=self.routebook_v1.root,
        ).analyze(work_unit=work_unit_model, route_plan=route_plan)
        task_profile = TaskProfiler(
            routebook=self.routebook,
            routebook_v1=self.routebook_v1,
        ).profile(work_unit=work_unit_model, route_plan=route_plan)
        capacity_profiles = capacity_profiles_for_candidates(
            candidates=route_plan.candidates,
            backend_registry=self.backend_resolver.backend_registry,
        )
        scoring_report = RouteScorer(
            routebook=self.routebook,
            routebook_v1=self.routebook_v1,
            backend_registry=self.backend_resolver.backend_registry,
        ).score(
            work_unit=work_unit_model,
            route_plan=route_plan,
            task_profile=task_profile,
            capacity_profiles=capacity_profiles,
            task_analysis_report=task_analysis_report,
        )
        return self.validator.validate(
            apply_scored_selection(
                route_plan=route_plan,
                scoring_report=scoring_report,
            )
        )


def persist_route_plan(conn: sqlite3.Connection, route_plan: RoutePlan) -> None:
    conn.execute(
        """
        INSERT INTO route_plans (
          route_plan_id,
          work_unit_id,
          status,
          body_json,
          created_at
        )
        VALUES (?, ?, ?, ?, ?)
        ON CONFLICT(route_plan_id) DO UPDATE SET
          status = excluded.status,
          body_json = excluded.body_json
        """,
        (
            route_plan.route_plan_id,
            route_plan.work_unit_id,
            "planned",
            canonical_json_dumps(route_plan.model_dump(mode="json")),
            route_plan.created_at.isoformat().replace("+00:00", "Z"),
        ),
    )
    conn.commit()
