"""RoutePlan validation guardrails."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from tokenbank.backends.registry import BackendRegistry
from tokenbank.capacity.validators import (
    API_GATEWAY_BACKEND_CLASSES,
    CONTROL_PLANE_GATEWAY_WORKER_ID,
)
from tokenbank.models.route_plan import RoutePlan
from tokenbank.routebook.loader import LoadedRoutebook


class RoutePlanValidationError(ValueError):
    """Raised when a RoutePlan violates router guardrails."""


class RoutePlanValidator:
    def __init__(
        self,
        *,
        routebook: LoadedRoutebook,
        backend_registry: BackendRegistry,
    ):
        self.routebook = routebook
        self.backend_registry = backend_registry

    def validate_payload(self, payload: dict[str, Any]) -> RoutePlan:
        self._reject_forbidden_shape(payload)
        route_plan = RoutePlan.model_validate(payload)
        return self.validate(route_plan)

    def validate(self, route_plan: RoutePlan) -> RoutePlan:
        self._reject_forbidden_shape(route_plan.model_dump(mode="json"))
        self._validate_verifier(route_plan)
        self._validate_candidates(route_plan)
        return route_plan

    def _validate_verifier(self, route_plan: RoutePlan) -> None:
        level = route_plan.task_level
        requires_verifier = self.routebook.task_levels.get(level, {}).get(
            "requires_verifier_recipe_id",
            level in {"L1", "L2", "L3"},
        )
        if requires_verifier and not route_plan.verifier_recipe_id:
            raise RoutePlanValidationError(
                "L1/L2/L3 RoutePlan requires verifier_recipe_id"
            )
        expected = self.routebook.verifier_mapping.get(route_plan.task_type)
        if requires_verifier and route_plan.verifier_recipe_id != expected:
            raise RoutePlanValidationError(
                "RoutePlan verifier_recipe_id does not match routebook"
            )
        for candidate in route_plan.candidates:
            if requires_verifier and not candidate.verifier_recipe_id:
                raise RoutePlanValidationError(
                    "L1/L2/L3 RouteCandidate requires verifier_recipe_id"
                )

    def _validate_candidates(self, route_plan: RoutePlan) -> None:
        candidate_ids = {
            candidate.route_candidate_id
            for candidate in route_plan.candidates
        }
        if route_plan.selected_candidate_id not in candidate_ids:
            raise RoutePlanValidationError("selected_candidate_id is not a candidate")

        forbidden_classes = set(
            self.routebook.forbidden_routes.get("forbidden_backend_classes", [])
        )
        for candidate in route_plan.candidates:
            try:
                backend = self.backend_registry.get(candidate.backend_id)
            except KeyError as exc:
                raise RoutePlanValidationError("unknown backend_id") from exc
            if candidate.backend_class != backend.backend_class:
                raise RoutePlanValidationError(
                    "candidate backend_class does not match backend_id"
                )
            if candidate.backend_class in forbidden_classes:
                raise RoutePlanValidationError("forbidden backend_class")
            if candidate.backend_class in API_GATEWAY_BACKEND_CLASSES:
                worker_id = candidate.worker_selector.get("worker_id")
                if worker_id != CONTROL_PLANE_GATEWAY_WORKER_ID:
                    raise RoutePlanValidationError(
                        "worker direct API model route is denied"
                    )
                if candidate.capacity_node_id != (
                    f"capnode:worker:{CONTROL_PLANE_GATEWAY_WORKER_ID}"
                ):
                    raise RoutePlanValidationError(
                        "API model gateway route must use control-plane gateway"
                    )

    def _reject_forbidden_shape(self, payload: Any) -> None:
        forbidden = self.routebook.forbidden_routes
        field_fragments = tuple(
            str(fragment)
            for fragment in forbidden.get("forbidden_field_fragments", [])
        )
        path_fragments = tuple(
            str(fragment)
            for fragment in forbidden.get("forbidden_path_fragments", [])
        )
        backend_id_fragments = tuple(
            str(fragment)
            for fragment in forbidden.get("forbidden_backend_id_fragments", [])
        )
        self._scan(
            payload,
            field_fragments=field_fragments,
            path_fragments=path_fragments,
            backend_id_fragments=backend_id_fragments,
        )

    def _scan(
        self,
        value: Any,
        *,
        field_fragments: tuple[str, ...],
        path_fragments: tuple[str, ...],
        backend_id_fragments: tuple[str, ...],
        path: str = "$",
    ) -> None:
        if isinstance(value, Mapping):
            if value.get("allowed_domains_source") in {"fetched_content", "llm"}:
                raise RoutePlanValidationError(
                    "LLM/fetched-content generated allowed_domains are denied"
                )
            for key, nested in value.items():
                normalized_key = str(key).lower().replace("-", "_")
                if any(fragment in normalized_key for fragment in field_fragments):
                    raise RoutePlanValidationError(
                        f"forbidden route field at {path}.{key}"
                    )
                if normalized_key == "backend_id" and any(
                    fragment in str(nested)
                    for fragment in backend_id_fragments
                ):
                    raise RoutePlanValidationError("OpenAI-compatible proxy route")
                self._scan(
                    nested,
                    field_fragments=field_fragments,
                    path_fragments=path_fragments,
                    backend_id_fragments=backend_id_fragments,
                    path=f"{path}.{key}",
                )
            return
        if isinstance(value, list):
            for index, nested in enumerate(value):
                self._scan(
                    nested,
                    field_fragments=field_fragments,
                    path_fragments=path_fragments,
                    backend_id_fragments=backend_id_fragments,
                    path=f"{path}[{index}]",
                )
            return
        if isinstance(value, str) and any(
            fragment in value
            for fragment in path_fragments
        ):
            raise RoutePlanValidationError("OpenAI-compatible proxy route")
