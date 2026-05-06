"""Execution attempt DTO."""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import Field, PositiveInt

from tokenbank.models.base import TokenBankModel, utc_now
from tokenbank.models.common import NonEmptyStr

ExecutionAttemptStatus = Literal[
    "created",
    "scheduled",
    "assigned",
    "running",
    "succeeded",
    "failed",
    "quarantined",
    "cancelled",
]


class ExecutionAttempt(TokenBankModel):
    attempt_id: NonEmptyStr
    work_unit_id: NonEmptyStr
    route_plan_id: NonEmptyStr
    policy_decision_id: NonEmptyStr
    attempt_number: PositiveInt = 1
    status: ExecutionAttemptStatus = "created"
    created_at: datetime = Field(default_factory=utc_now)
    started_at: datetime | None = None
    completed_at: datetime | None = None

