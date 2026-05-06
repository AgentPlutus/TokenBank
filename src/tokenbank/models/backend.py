"""Backend manifest, health, usage, and error DTOs."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import Field, NonNegativeInt

from tokenbank.models.base import TokenBankModel, utc_now
from tokenbank.models.common import (
    BackendClass,
    CostConfidence,
    CostModel,
    CostSource,
    HealthStatus,
    NonEmptyStr,
    PrivacyLevel,
)


class BackendHealth(TokenBankModel):
    backend_id: NonEmptyStr
    status: HealthStatus = "unknown"
    checked_at: datetime = Field(default_factory=utc_now)
    latency_ms: NonNegativeInt | None = None
    message: str | None = None


class BackendManifest(TokenBankModel):
    backend_id: NonEmptyStr
    backend_class: BackendClass
    capacity_node_id: NonEmptyStr
    display_name: NonEmptyStr
    version: NonEmptyStr
    supported_task_types: list[NonEmptyStr]
    allowed_privacy_levels: list[PrivacyLevel] = Field(
        default_factory=lambda: ["private"]
    )
    execution_location: NonEmptyStr
    manifest_hash: NonEmptyStr
    health: BackendHealth | None = None
    cost_model: CostModel = Field(default_factory=CostModel)
    policy_constraints: dict[str, Any] = Field(default_factory=dict)


class UsageRecord(TokenBankModel):
    usage_record_id: NonEmptyStr
    work_unit_id: NonEmptyStr
    attempt_id: NonEmptyStr
    backend_id: NonEmptyStr
    input_units: NonNegativeInt = 0
    output_units: NonNegativeInt = 0
    estimated_cost_micros: NonNegativeInt = 0
    actual_cost_micros: NonNegativeInt = 0
    cost_source: CostSource = "not_applicable"
    cost_confidence: CostConfidence = "not_applicable"
    recorded_at: datetime = Field(default_factory=utc_now)


class BackendError(TokenBankModel):
    error_code: NonEmptyStr
    error_message: NonEmptyStr
    retryable: bool = False
    fallbackable: bool = False
    redacted_details: dict[str, Any] = Field(default_factory=dict)
    occurred_at: datetime = Field(default_factory=utc_now)
