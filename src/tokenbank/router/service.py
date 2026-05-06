"""RouterService for deterministic RoutePlan generation."""

from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Any

from tokenbank.backends.resolver import BackendResolver
from tokenbank.config_runtime.loader import load_config_dir
from tokenbank.core.canonical import canonical_json_dumps
from tokenbank.models.route_plan import RoutePlan
from tokenbank.routebook.loader import LoadedRoutebook, load_routebook_dir
from tokenbank.router.candidate_generator import CandidateGenerator
from tokenbank.router.classifier import TaskClassifier
from tokenbank.router.normalizer import RoutePlanNormalizer
from tokenbank.router.route_plan_validator import RoutePlanValidator


class RouterService:
    """Build RoutePlan objects without executing or assigning work."""

    def __init__(
        self,
        *,
        routebook: LoadedRoutebook,
        backend_resolver: BackendResolver,
    ):
        self.routebook = routebook
        self.backend_resolver = backend_resolver
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
    ) -> RouterService:
        config = load_config_dir(config_dir)
        return cls(
            routebook=load_routebook_dir(routebook_dir),
            backend_resolver=BackendResolver.from_config(config),
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
        if persist_conn is not None:
            persist_route_plan(persist_conn, validated)
        return validated

    def _risk_level(self, task_level: str) -> str:
        return str(
            self.routebook.task_levels.get(task_level, {}).get("risk_level", "low")
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
