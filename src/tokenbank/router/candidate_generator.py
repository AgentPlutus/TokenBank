"""Route candidate generation from routebook and backend registry summaries."""

from __future__ import annotations

from typing import Any

from tokenbank.backends.resolver import BackendResolver
from tokenbank.models.route_plan import RouteCandidate
from tokenbank.routebook.loader import LoadedRoutebook


def matching_candidate_rules(
    *,
    routebook: LoadedRoutebook,
    task_type: str,
) -> list[dict[str, Any]]:
    return sorted(
        [
            rule
            for rule in routebook.candidate_rules
            if rule.get("task_type") == task_type
        ],
        key=lambda rule: (int(rule.get("priority", 1)), str(rule.get("rule_id"))),
    )


class CandidateGenerator:
    def __init__(
        self,
        *,
        routebook: LoadedRoutebook,
        backend_resolver: BackendResolver,
    ):
        self.routebook = routebook
        self.backend_resolver = backend_resolver

    def generate(
        self,
        *,
        work_unit: dict[str, Any],
        task_level: str,
    ) -> list[RouteCandidate]:
        task_type = str(work_unit["task_type"])
        verifier_recipe_id = self.routebook.verifier_mapping.get(task_type)
        policy_hints = list(self.routebook.policy_hints.get(task_type, []))
        candidates: list[RouteCandidate] = []

        for rule in matching_candidate_rules(
            routebook=self.routebook,
            task_type=task_type,
        ):
            resolution = self.backend_resolver.resolve(
                {
                    **rule,
                    "task_level": task_level,
                }
            )
            worker_selector = self._worker_selector(resolution.worker_id)
            candidates.append(
                RouteCandidate(
                    route_candidate_id=str(rule["rule_id"]),
                    capacity_node_id=resolution.capacity_node_id,
                    backend_class=resolution.backend_class,  # type: ignore[arg-type]
                    backend_id=resolution.backend_id,
                    worker_selector=worker_selector,
                    priority=int(rule.get("priority", 1)),
                    estimated_cost_micros=self._estimated_cost_micros(
                        resolution.backend_id
                    ),
                    verifier_recipe_id=verifier_recipe_id,
                    policy_hints=policy_hints,
                )
            )

        return candidates

    def _estimated_cost_micros(self, backend_id: str) -> int:
        backend = self.backend_resolver.backend_registry.get(backend_id)
        return int(backend.cost_model.estimated_cost_micros)

    def _worker_selector(self, worker_id: str | None) -> dict[str, str]:
        if worker_id is None:
            return {"selector_type": "registry"}
        return {
            "selector_type": "worker_id",
            "worker_id": worker_id,
        }

