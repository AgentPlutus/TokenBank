"""Capacity node DTOs."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import Field, NonNegativeInt

from tokenbank.models.base import TokenBankModel, utc_now
from tokenbank.models.common import (
    BackendClass,
    CostModel,
    HealthStatus,
    NonEmptyStr,
    PrivacyLevel,
)

CapacityNodeType = Literal[
    "windows_worker",
    "control_plane_gateway",
    "local_tool",
    "local_script",
    "browser_fetch",
    "local_model",
    "api_model_gateway",
    "primary_model_gateway",
    "future_agent",
]
ExecutionLocation = Literal["mac_control_plane", "windows_worker", "local_machine"]
TrustLevel = Literal["trusted_private", "control_plane", "sandboxed"]


class CapacityNodeHealth(TokenBankModel):
    capacity_node_id: NonEmptyStr
    status: HealthStatus = "unknown"
    checked_at: datetime = Field(default_factory=utc_now)
    latency_ms: NonNegativeInt | None = None
    active_assignments: NonNegativeInt = 0
    message: str | None = None


class CapacityNode(TokenBankModel):
    capacity_node_id: NonEmptyStr
    node_type: CapacityNodeType
    identity: NonEmptyStr
    capabilities: list[NonEmptyStr]
    trust_level: TrustLevel
    allowed_task_types: list[NonEmptyStr]
    allowed_data_labels: list[NonEmptyStr] = Field(default_factory=list)
    allowed_privacy_levels: list[PrivacyLevel] = Field(
        default_factory=lambda: ["private"]
    )
    execution_location: ExecutionLocation
    cost_model: CostModel = Field(default_factory=CostModel)
    health: CapacityNodeHealth
    policy_constraints: dict[str, Any] = Field(default_factory=dict)
    backend_ids: list[NonEmptyStr] = Field(default_factory=list)
    backend_classes: list[BackendClass] = Field(default_factory=list)
    backend_id: str | None = None
    worker_id: str | None = None
    provider_id: str | None = None
    model_id: str | None = None
    manifest_hash: NonEmptyStr
    created_at: datetime = Field(default_factory=utc_now)
    updated_at: datetime = Field(default_factory=utc_now)
