"""Usage ledger DTOs for local audit accounting."""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import Field, NonNegativeInt

from tokenbank.models.base import TokenBankModel, utc_now
from tokenbank.models.common import NonEmptyStr, VerifierRecommendation

UsageLedgerSource = Literal["estimate", "provider_response", "manual"]
UsageCostSource = Literal["estimated", "provider_reported", "manual", "not_applicable"]


class UsageLedgerEntry(TokenBankModel):
    """Local, redacted usage accounting for one WorkUnit result."""

    usage_ledger_entry_id: NonEmptyStr
    work_unit_id: NonEmptyStr
    run_id: NonEmptyStr
    route_plan_id: NonEmptyStr
    result_envelope_id: NonEmptyStr
    verifier_report_id: NonEmptyStr | None = None
    account_snapshot_id: NonEmptyStr | None = None
    routebook_id: NonEmptyStr = "tokenbank.base"
    routebook_version: NonEmptyStr = "unknown"
    capacity_node_id: NonEmptyStr | None = None
    capacity_profile_id: NonEmptyStr | None = None
    backend_id: NonEmptyStr | None = None
    provider_id: str | None = None
    model_id: str | None = None
    estimated_input_tokens: NonNegativeInt = 0
    estimated_output_tokens: NonNegativeInt = 0
    estimated_total_tokens: NonNegativeInt = 0
    reported_input_tokens: NonNegativeInt | None = None
    reported_output_tokens: NonNegativeInt | None = None
    reported_total_tokens: NonNegativeInt | None = None
    estimated_cost_micros: NonNegativeInt = 0
    reported_cost_micros: NonNegativeInt | None = None
    billable_cost_micros: NonNegativeInt = 0
    usage_source: UsageLedgerSource = "estimate"
    cost_source: UsageCostSource = "estimated"
    verifier_recommendation: VerifierRecommendation | None = None
    entry_hash: NonEmptyStr
    created_at: datetime = Field(default_factory=utc_now)
