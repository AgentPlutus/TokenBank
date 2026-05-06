"""Routebook V1 task profile DTOs."""

from __future__ import annotations

from typing import Literal

from pydantic import Field

from tokenbank.models.base import TokenBankModel
from tokenbank.models.common import NonEmptyStr, PrivacyLevel, TaskLevel

TaskProfileSource = Literal["deterministic", "llm_assisted", "host_supplied"]
TaskDifficulty = Literal["trivial", "easy", "medium", "high", "expert"]
ContextSize = Literal["small", "medium", "large", "unknown"]
RoutePreference = Literal["low", "normal", "high"]
CostPreference = Literal["cost_first", "balanced", "quality_first"]
RequirementImportance = Literal["required", "preferred", "optional"]
AmbiguityStatus = Literal["low", "medium", "high", "unknown"]


class RequiredCapability(TokenBankModel):
    capability: NonEmptyStr
    min_score: float = Field(ge=0.0, le=1.0)
    importance: RequirementImportance = "required"


class AmbiguityProfile(TokenBankModel):
    status: AmbiguityStatus = "unknown"
    unresolved_questions: list[NonEmptyStr] = Field(default_factory=list)


class TaskProfile(TokenBankModel):
    """Structured pre-route task profile.

    A host model or deterministic profiler may produce this object, but it is
    not itself a route decision.
    """

    task_profile_id: NonEmptyStr
    work_unit_id: NonEmptyStr
    routebook_id: NonEmptyStr
    routebook_version: NonEmptyStr
    source: TaskProfileSource = "deterministic"
    task_family: NonEmptyStr
    task_type: NonEmptyStr
    difficulty: TaskDifficulty = "medium"
    risk_level: TaskLevel = "L1"
    privacy_level: PrivacyLevel = "private"
    context_size: ContextSize = "unknown"
    latency_preference: RoutePreference = "normal"
    cost_preference: CostPreference = "balanced"
    required_capabilities: list[RequiredCapability] = Field(default_factory=list)
    forbidden_capabilities: list[NonEmptyStr] = Field(default_factory=list)
    requires_tools: list[NonEmptyStr] = Field(default_factory=list)
    requires_verifier_recipe_id: bool = True
    success_criteria: list[NonEmptyStr] = Field(default_factory=list)
    ambiguity: AmbiguityProfile = Field(default_factory=AmbiguityProfile)
    confidence: float = Field(default=0.0, ge=0.0, le=1.0)
    profile_reason_codes: list[NonEmptyStr] = Field(default_factory=list)
