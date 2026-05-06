"""Routebook V1 capacity profile DTOs."""

from __future__ import annotations

from typing import Literal

from pydantic import Field, NonNegativeInt

from tokenbank.models.base import TokenBankModel
from tokenbank.models.common import BackendClass, NonEmptyStr

OwnershipScope = Literal["user_local", "team_local", "system", "peer"]
AvailabilityState = Literal["available", "degraded", "unavailable", "unknown"]
ModelTier = Literal["weak_general", "standard", "strong", "frontier", "specialist"]
ContextWindowClass = Literal["small", "medium", "large", "very_large", "unknown"]
CapabilityEvidence = Literal["declared", "tested", "verified", "attested"]
CostTier = Literal["free", "low", "medium", "high", "unknown"]
VerifiedStatus = Literal["declared", "tested", "verified", "failed"]


class ModelProfile(TokenBankModel):
    provider_id: NonEmptyStr
    model_id: NonEmptyStr
    model_tier: ModelTier = "standard"
    context_window_class: ContextWindowClass = "unknown"
    supports_structured_output: bool = False
    supports_tool_calling: bool = False
    wire_quirks_profile_id: str | None = None


class CapacityCapability(TokenBankModel):
    score: float = Field(ge=0.0, le=1.0)
    evidence: CapabilityEvidence = "declared"


class CapacityCostProfile(TokenBankModel):
    estimated_cost_micros: NonNegativeInt = 0
    cost_tier: CostTier = "unknown"


class CapacityLatencyProfile(TokenBankModel):
    p50_ms: NonNegativeInt | None = None
    p95_ms: NonNegativeInt | None = None


class CapacityQualityMemory(TokenBankModel):
    verifier_pass_rate: float | None = Field(default=None, ge=0.0, le=1.0)
    accepted_result_rate: float | None = Field(default=None, ge=0.0, le=1.0)
    sample_size: NonNegativeInt = 0


class VerifiedForTask(TokenBankModel):
    task_type: NonEmptyStr
    verifier_recipe_id: NonEmptyStr
    status: VerifiedStatus = "declared"


class CapacityProfile(TokenBankModel):
    """Routebook V1 capability map for executable private capacity."""

    capacity_profile_id: NonEmptyStr
    capacity_node_id: NonEmptyStr
    backend_id: NonEmptyStr
    backend_class: BackendClass
    ownership_scope: OwnershipScope = "user_local"
    execution_boundary: NonEmptyStr
    availability_state: AvailabilityState = "unknown"
    model_profile: ModelProfile | None = None
    capabilities: dict[NonEmptyStr, CapacityCapability] = Field(default_factory=dict)
    cost: CapacityCostProfile = Field(default_factory=CapacityCostProfile)
    latency: CapacityLatencyProfile = Field(default_factory=CapacityLatencyProfile)
    quality_memory: CapacityQualityMemory = Field(
        default_factory=CapacityQualityMemory
    )
    verified_for: list[VerifiedForTask] = Field(default_factory=list)
