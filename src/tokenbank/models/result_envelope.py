"""Work Unit result envelope DTO."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import Field, NonNegativeInt

from tokenbank.models.backend import BackendError, UsageRecord
from tokenbank.models.base import TokenBankModel, utc_now
from tokenbank.models.common import (
    ArtifactRef,
    BackendClass,
    CostConfidence,
    CostSource,
    NonEmptyStr,
)

ResultEnvelopeStatus = Literal["succeeded", "failed", "quarantined"]


class WorkUnitResultEnvelope(TokenBankModel):
    result_envelope_id: NonEmptyStr
    work_unit_id: NonEmptyStr
    run_id: NonEmptyStr
    attempt_id: NonEmptyStr
    assignment_id: NonEmptyStr
    status: ResultEnvelopeStatus
    backend_id: NonEmptyStr | None = None
    backend_class: BackendClass | None = None
    provider_id: str | None = None
    model_id: str | None = None
    worker_id: str | None = None
    capacity_node_id: str | None = None
    output: dict[str, Any] = Field(default_factory=dict)
    output_hash: NonEmptyStr
    result_hash: NonEmptyStr
    artifact_refs: list[ArtifactRef] = Field(default_factory=list)
    usage_records: list[UsageRecord] = Field(default_factory=list)
    cost_estimate_micros: NonNegativeInt = 0
    actual_cost_micros: NonNegativeInt = 0
    cost_source: CostSource = "not_applicable"
    cost_confidence: CostConfidence = "not_applicable"
    redacted_logs: list[str] = Field(default_factory=list)
    errors: list[BackendError] = Field(default_factory=list)
    backend_error: BackendError | None = None
    started_at: datetime | None = None
    completed_at: datetime = Field(default_factory=utc_now)
    duration_ms: NonNegativeInt | None = None
