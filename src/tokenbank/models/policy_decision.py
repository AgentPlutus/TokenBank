"""Policy decision DTO."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import Field

from tokenbank.models.base import TokenBankModel, utc_now
from tokenbank.models.common import NonEmptyStr

PolicyDecisionValue = Literal["approved", "denied", "needs_review"]


class PolicyDecision(TokenBankModel):
    policy_decision_id: NonEmptyStr
    work_unit_id: NonEmptyStr
    route_plan_id: NonEmptyStr
    decision: PolicyDecisionValue
    reasons: list[NonEmptyStr] = Field(default_factory=list)
    checks: list[dict[str, Any]] = Field(default_factory=list)
    effective_constraints: dict[str, Any] = Field(default_factory=dict)
    decided_at: datetime = Field(default_factory=utc_now)
