"""Routebook V1 deterministic TaskProfile builder."""

from __future__ import annotations

from typing import Any

from tokenbank.models.route_plan import RoutePlan
from tokenbank.models.task_profile import (
    AmbiguityProfile,
    RequiredCapability,
    TaskProfile,
)
from tokenbank.models.work_unit import WorkUnit
from tokenbank.routebook.loader import LoadedRoutebook
from tokenbank.routebook.v1_loader import LoadedRoutebookV1


class TaskProfiler:
    """Build a schema-bound TaskProfile without making a route decision."""

    def __init__(
        self,
        *,
        routebook: LoadedRoutebook,
        routebook_v1: LoadedRoutebookV1,
    ):
        self.routebook = routebook
        self.routebook_v1 = routebook_v1

    def profile(
        self,
        *,
        work_unit: WorkUnit,
        route_plan: RoutePlan,
    ) -> TaskProfile:
        task_defaults = self.task_type_defaults(work_unit.task_type)
        task_entry = self.routebook.task_type_entry(work_unit.task_type)
        return TaskProfile(
            task_profile_id=f"tp_{work_unit.work_unit_id}_{work_unit.task_type}",
            work_unit_id=work_unit.work_unit_id,
            routebook_id=self.routebook_v1.routebook_id,
            routebook_version=self.routebook_v1.version,
            source="deterministic",
            task_family=str(task_defaults.get("task_family", "simple_transform")),
            task_type=work_unit.task_type,
            difficulty=str(task_defaults.get("difficulty", "medium")),  # type: ignore[arg-type]
            risk_level=route_plan.task_level,
            privacy_level=work_unit.privacy_level,
            context_size=self._context_size(work_unit.inline_input),
            latency_preference="normal",
            cost_preference="balanced",
            required_capabilities=self._required_capabilities(task_defaults),
            requires_tools=self._requires_tools(route_plan),
            requires_verifier_recipe_id=bool(route_plan.verifier_recipe_id),
            success_criteria=[
                str(value)
                for value in task_defaults.get("success_criteria", [])
                if isinstance(value, str)
            ],
            ambiguity=AmbiguityProfile(status="low", unresolved_questions=[]),
            confidence=0.82,
            profile_reason_codes=[
                f"routebook_task_type:{work_unit.task_type}",
                f"default_task_level:{task_entry.get('default_task_level')}",
                "deterministic_wp_rb1_profile",
            ],
        )

    def task_type_defaults(self, task_type: str) -> dict[str, Any]:
        defaults = self.routebook_v1.ontology.get("task_type_defaults", {})
        if isinstance(defaults, dict) and isinstance(defaults.get(task_type), dict):
            return dict(defaults[task_type])
        return {}

    def _required_capabilities(
        self,
        task_defaults: dict[str, Any],
    ) -> list[RequiredCapability]:
        known_capabilities = set(self.routebook_v1.capability_tags)
        required: list[RequiredCapability] = []
        for capability in task_defaults.get("required_capabilities", []):
            if not isinstance(capability, str):
                continue
            if capability not in known_capabilities:
                continue
            required.append(
                RequiredCapability(
                    capability=capability,
                    min_score=0.75,
                    importance="required",
                )
            )
        return required

    def _context_size(self, inline_input: dict[str, Any]) -> str:
        text_size = len(str(inline_input))
        if text_size < 1_000:
            return "small"
        if text_size < 20_000:
            return "medium"
        return "large"

    def _requires_tools(self, route_plan: RoutePlan) -> list[str]:
        return sorted(
            {
                candidate.backend_class
                for candidate in route_plan.candidates
                if candidate.backend_class
                not in {"api_model_gateway", "primary_model_gateway"}
            }
        )
