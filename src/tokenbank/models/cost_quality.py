"""Host-facing cost and quality summary DTOs."""

from __future__ import annotations

from pydantic import Field, NonNegativeInt

from tokenbank.models.base import TokenBankModel
from tokenbank.models.common import (
    AuditStatus,
    CostConfidence,
    CostSource,
    NonEmptyStr,
    QualityStatus,
)


class HostCostQualitySummary(TokenBankModel):
    estimated_cost_micros: NonNegativeInt = 0
    actual_cost_micros: NonNegativeInt = 0
    cost_source: CostSource = "not_applicable"
    cost_confidence: CostConfidence = "not_applicable"
    baseline_mode: NonEmptyStr = "none"
    baseline_cost_micros: NonNegativeInt | None = None
    saving_ratio_bps: NonNegativeInt | None = Field(
        default=None,
        description="Cost saving ratio in basis points; 10000 means 100 percent.",
    )
    primary_model_fallback_used: bool = False
    primary_model_fallback_cost_micros: NonNegativeInt = 0
    local_zero_cost_caveat: str | None = None
    verifier_passed: bool | None = None
    quality_status: QualityStatus = "unknown"
    audit_status: AuditStatus = "unknown"
    caveats: list[str] = Field(default_factory=list)
