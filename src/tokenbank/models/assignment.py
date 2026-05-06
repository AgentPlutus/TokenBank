"""Assignment DTO."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import Field, NonNegativeInt

from tokenbank.models.base import TokenBankModel, utc_now
from tokenbank.models.common import NonEmptyStr

AssignmentStatus = Literal[
    "created",
    "accepted",
    "running",
    "completed",
    "rejected",
    "quarantined",
    "expired",
    "cancelled",
    "failed",
]


class Assignment(TokenBankModel):
    assignment_id: NonEmptyStr
    attempt_id: NonEmptyStr
    work_unit_id: NonEmptyStr
    worker_id: NonEmptyStr
    capacity_node_id: NonEmptyStr
    backend_id: NonEmptyStr
    status: AssignmentStatus = "created"
    lease_token_hash: str | None = None
    lease_version: NonNegativeInt = 0
    effective_constraints: dict[str, Any] = Field(default_factory=dict)
    assigned_at: datetime = Field(default_factory=utc_now)
    lease_expires_at: datetime | None = None
