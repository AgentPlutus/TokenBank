"""Route plan DTOs."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import Field, NonNegativeInt, PositiveInt

from tokenbank.models.base import TokenBankModel, utc_now
from tokenbank.models.common import BackendClass, NonEmptyStr, TaskLevel

RouteRiskLevel = Literal["low", "medium", "high"]


class RouteCandidate(TokenBankModel):
    route_candidate_id: NonEmptyStr
    capacity_node_id: NonEmptyStr
    backend_class: BackendClass
    backend_id: NonEmptyStr
    worker_selector: dict[str, Any] = Field(default_factory=dict)
    priority: PositiveInt = 1
    estimated_cost_micros: NonNegativeInt = 0
    verifier_recipe_id: str | None = None
    policy_hints: list[NonEmptyStr] = Field(default_factory=list)


class RoutePlan(TokenBankModel):
    route_plan_id: NonEmptyStr
    work_unit_id: NonEmptyStr
    task_type: NonEmptyStr
    task_level: TaskLevel
    candidates: list[RouteCandidate] = Field(min_length=1)
    selected_candidate_id: NonEmptyStr
    verifier_recipe_id: NonEmptyStr
    risk_level: RouteRiskLevel = "low"
    policy_hints: list[NonEmptyStr] = Field(default_factory=list)
    created_at: datetime = Field(default_factory=utc_now)
    validated_at: datetime | None = None

