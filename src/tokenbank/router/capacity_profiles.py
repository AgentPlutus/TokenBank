"""CapacityProfile builders used by route explanation and scoring."""

from __future__ import annotations

from tokenbank.backends.registry import BackendRegistry
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
from tokenbank.models.route_plan import RouteCandidate


def capacity_profiles_for_candidates(
    *,
    candidates: list[RouteCandidate],
    backend_registry: BackendRegistry,
) -> list[CapacityProfile]:
    return [
        capacity_profile_for_candidate(
            candidate=candidate,
            backend_registry=backend_registry,
        )
        for candidate in candidates
    ]


def capacity_profile_for_candidate(
    *,
    candidate: RouteCandidate,
    backend_registry: BackendRegistry,
) -> CapacityProfile:
    backend = backend_registry.get(candidate.backend_id)
    capability_names = backend_capabilities(backend, candidate)
    return CapacityProfile(
        capacity_profile_id=f"cp_{safe_id(candidate.backend_id)}",
        capacity_node_id=candidate.capacity_node_id,
        backend_id=candidate.backend_id,
        backend_class=candidate.backend_class,
        ownership_scope="user_local",
        execution_boundary=backend.execution_location,
        availability_state="available"
        if backend.health is None
        else _availability(backend.health.status),
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


def backend_capabilities(
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


def safe_id(value: str) -> str:
    return value.replace(":", "_").replace("/", "_").replace(".", "_")


def _model_profile(backend: BackendManifest) -> ModelProfile | None:
    if backend.backend_class not in {"api_model_gateway", "primary_model_gateway"}:
        return None
    return ModelProfile(
        provider_id="control_plane_gateway",
        model_id=backend.backend_id,
        model_tier=_model_tier(backend),
        context_window_class="unknown",
        supports_structured_output=True,
        supports_tool_calling=False,
        wire_quirks_profile_id=None,
    )


def _model_tier(backend: BackendManifest) -> str:
    if backend.backend_class == "primary_model_gateway":
        return "frontier"
    if "claim_extraction" in backend.supported_task_types:
        return "strong"
    return "standard"


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
