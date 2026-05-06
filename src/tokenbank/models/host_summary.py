"""Host-facing result summary DTO."""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import Field, NonNegativeInt

from tokenbank.models.base import TokenBankModel, utc_now
from tokenbank.models.common import (
    ArtifactRef,
    BackendClass,
    NonEmptyStr,
    TaskLevel,
    VerifierRecommendation,
    VerifierStatus,
)
from tokenbank.models.cost_quality import HostCostQualitySummary

HostResultStatus = Literal["succeeded", "failed", "running", "quarantined", "cancelled"]
QuarantineStatus = Literal["none", "quarantined", "released"]


class HostResultSummary(TokenBankModel):
    work_unit_id: NonEmptyStr
    run_id: NonEmptyStr
    status: HostResultStatus
    task_type: NonEmptyStr
    task_level: TaskLevel
    verifier_status: VerifierStatus
    verifier_recommendation: VerifierRecommendation
    result_summary: str
    artifact_refs: list[ArtifactRef] = Field(default_factory=list)
    duration_ms: NonNegativeInt | None = None
    backend_class: BackendClass
    backend_id: NonEmptyStr
    worker_id: NonEmptyStr
    capacity_node_id: NonEmptyStr
    cost_summary: HostCostQualitySummary
    warnings: list[str] = Field(default_factory=list)
    caveats: list[str] = Field(default_factory=list)
    fallback_used: bool = False
    quarantine_status: QuarantineStatus = "none"
    retry_count: NonNegativeInt = 0
    trace_ref: str | None = None
    generated_at: datetime = Field(default_factory=utc_now)
