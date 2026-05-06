"""Hash-backed audit receipts for accepted WorkUnit results."""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import Field

from tokenbank.models.base import TokenBankModel, utc_now
from tokenbank.models.common import NonEmptyStr

AuditReceiptStatus = Literal["accepted", "accepted_with_warning"]
AuditReceiptRedactionProfile = Literal["ids_and_hashes_only"]


class AuditReceipt(TokenBankModel):
    """Redacted audit chain from WorkUnit through VerifierReport."""

    audit_receipt_id: NonEmptyStr
    work_unit_id: NonEmptyStr
    run_id: NonEmptyStr
    route_plan_id: NonEmptyStr
    assignment_id: NonEmptyStr
    result_envelope_id: NonEmptyStr
    verifier_report_id: NonEmptyStr
    usage_ledger_entry_id: NonEmptyStr | None = None
    routebook_id: NonEmptyStr = "tokenbank.base"
    routebook_version: NonEmptyStr = "unknown"
    status: AuditReceiptStatus
    work_unit_hash: NonEmptyStr
    route_plan_hash: NonEmptyStr
    assignment_hash: NonEmptyStr
    result_hash: NonEmptyStr
    result_envelope_hash: NonEmptyStr
    verifier_report_hash: NonEmptyStr
    usage_ledger_entry_hash: NonEmptyStr | None = None
    task_analysis_hash: NonEmptyStr | None = None
    task_profile_hash: NonEmptyStr | None = None
    previous_receipt_hash: NonEmptyStr | None = None
    receipt_hash: NonEmptyStr
    redaction_profile: AuditReceiptRedactionProfile = "ids_and_hashes_only"
    reason_codes: list[NonEmptyStr] = Field(default_factory=list)
    created_at: datetime = Field(default_factory=utc_now)
