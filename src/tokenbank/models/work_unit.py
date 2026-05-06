"""Work Unit DTO."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import Field, NonNegativeInt, PositiveInt

from tokenbank.models.base import TokenBankModel, utc_now
from tokenbank.models.common import ArtifactRef, NonEmptyStr, PrivacyLevel, TaskLevel

WorkUnitStatus = Literal[
    "submitted",
    "routing",
    "queued",
    "assigned",
    "running",
    "succeeded",
    "failed",
    "quarantined",
    "cancelled",
]


class WorkUnit(TokenBankModel):
    work_unit_id: NonEmptyStr
    run_id: NonEmptyStr
    task_type: NonEmptyStr
    task_level: TaskLevel
    status: WorkUnitStatus = "submitted"
    privacy_level: PrivacyLevel = "private"
    data_labels: list[NonEmptyStr] = Field(default_factory=list)
    input_refs: list[ArtifactRef] = Field(default_factory=list)
    inline_input: dict[str, Any] = Field(default_factory=dict)
    output_schema_ref: str | None = None
    max_cost_micros: NonNegativeInt | None = None
    deadline_ms: PositiveInt | None = None
    created_at: datetime = Field(default_factory=utc_now)
    updated_at: datetime = Field(default_factory=utc_now)

