"""Shared DTO types."""

from __future__ import annotations

from typing import Annotated, Any, Literal

from pydantic import Field, NonNegativeInt

from tokenbank.models.base import TokenBankModel

NonEmptyStr = Annotated[str, Field(min_length=1)]

TaskLevel = Literal["L0", "L1", "L2", "L3"]
PrivacyLevel = Literal["private", "internal", "sensitive"]
BackendClass = Literal[
    "local_tool",
    "local_script",
    "browser_fetch",
    "local_model",
    "api_model_gateway",
    "primary_model_gateway",
]
HealthStatus = Literal["healthy", "degraded", "unhealthy", "unknown"]
CostSource = Literal[
    "measured",
    "estimated",
    "policy_default",
    "zero_internal_phase0",
    "not_applicable",
]
CostConfidence = Literal["low", "medium", "high", "not_applicable"]
QualityStatus = Literal["passed", "failed", "needs_review", "unknown"]
AuditStatus = Literal["clean", "warning", "quarantined", "unknown"]
VerifierStatus = Literal["passed", "failed", "needs_review", "skipped"]
VerifierRecommendation = Literal[
    "accept",
    "accept_with_warning",
    "retry",
    "fallback",
    "reject",
    "quarantine",
    "escalate",
    "review",
]


class ArtifactRef(TokenBankModel):
    artifact_id: NonEmptyStr
    uri: NonEmptyStr
    media_type: NonEmptyStr = "application/octet-stream"
    artifact_hash: NonEmptyStr
    metadata: dict[str, Any] = Field(default_factory=dict)


class VerifierCheckResult(TokenBankModel):
    name: NonEmptyStr
    status: VerifierStatus
    message: str = ""
    observed_hash: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class CostModel(TokenBankModel):
    unit: NonEmptyStr = "work_unit"
    estimated_cost_micros: NonNegativeInt = 0
    cost_source: CostSource = "policy_default"
