"""Verifier report DTO."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import Field

from tokenbank.models.base import TokenBankModel, utc_now
from tokenbank.models.common import (
    NonEmptyStr,
    VerifierCheckResult,
    VerifierRecommendation,
    VerifierStatus,
)


class VerifierReport(TokenBankModel):
    verifier_report_id: NonEmptyStr
    work_unit_id: NonEmptyStr
    result_envelope_id: NonEmptyStr
    verifier_recipe_id: NonEmptyStr
    status: VerifierStatus
    recommendation: VerifierRecommendation
    checks: list[VerifierCheckResult] = Field(default_factory=list)
    output_hash: NonEmptyStr
    result_hash: NonEmptyStr
    metadata: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime = Field(default_factory=utc_now)

