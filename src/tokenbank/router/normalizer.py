"""RoutePlan normalizer."""

from __future__ import annotations

from tokenbank.models.route_plan import RouteCandidate, RoutePlan


class RoutePlanNormalizer:
    def normalize(self, route_plan: RoutePlan) -> RoutePlan:
        candidates = sorted(
            route_plan.candidates,
            key=lambda candidate: (
                candidate.priority,
                candidate.backend_id,
                candidate.route_candidate_id,
            ),
        )
        selected_candidate_id = candidates[0].route_candidate_id
        normalized_candidates = [
            self._normalize_candidate(candidate)
            for candidate in candidates
        ]
        return route_plan.model_copy(
            update={
                "candidates": normalized_candidates,
                "selected_candidate_id": selected_candidate_id,
            }
        )

    def _normalize_candidate(self, candidate: RouteCandidate) -> RouteCandidate:
        worker_selector = dict(sorted(candidate.worker_selector.items()))
        return candidate.model_copy(update={"worker_selector": worker_selector})
