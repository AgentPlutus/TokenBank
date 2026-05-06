"""Local account state snapshots for WP-LEDGER1."""

from __future__ import annotations

import re
from datetime import datetime
from typing import Literal

from pydantic import Field, NonNegativeInt, model_validator

from tokenbank.models.base import TokenBankModel, utc_now
from tokenbank.models.common import NonEmptyStr

AccountSnapshotStatus = Literal["configured", "unconfigured", "error", "unknown"]
BalanceSnapshotSource = Literal["provider_api", "tokenbank_ledger", "manual"]
SecretRefStatus = Literal["present", "missing", "unknown"]

_ALLOWED_SECRET_REF_PREFIXES = (
    "keychain:",
    "env:",
    "vault:",
    "manual:",
    "none:",
)
_RAW_SECRET_VALUE_PATTERNS = (
    re.compile(r"\bsk-[A-Za-z0-9_-]{8,}\b"),
    re.compile(r"(?i)\bbearer\s+[A-Za-z0-9._~+/=-]{8,}"),
    re.compile(r"\btbk_[a-z]_[A-Za-z0-9_-]{8,}\b"),
    re.compile(r"\bxox[abpr]-[A-Za-z0-9-]{8,}\b"),
    re.compile(r"\bgh[pousr]_[A-Za-z0-9_]{12,}\b"),
    re.compile(r"\bAKIA[0-9A-Z]{16}\b"),
    re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----"),
)


class BalanceSnapshot(TokenBankModel):
    source: BalanceSnapshotSource = "manual"
    available_micros: NonNegativeInt | None = None
    monthly_spend_micros: NonNegativeInt | None = None
    monthly_budget_micros: NonNegativeInt | None = None
    confidence: float = Field(default=0.5, ge=0.0, le=1.0)
    captured_at: datetime = Field(default_factory=utc_now)


class RateLimitSnapshot(TokenBankModel):
    requests_per_minute: NonNegativeInt | None = None
    tokens_per_minute: NonNegativeInt | None = None
    concurrent_requests: NonNegativeInt | None = None
    source: BalanceSnapshotSource = "manual"
    captured_at: datetime = Field(default_factory=utc_now)


class AccountSnapshot(TokenBankModel):
    """Host-local account visibility without raw provider credentials."""

    account_snapshot_id: NonEmptyStr
    provider: NonEmptyStr
    account_label: NonEmptyStr
    status: AccountSnapshotStatus = "unknown"
    secret_ref: NonEmptyStr | None = None
    secret_ref_status: SecretRefStatus = "unknown"
    raw_secret_present: bool = False
    balance: BalanceSnapshot | None = None
    rate_limits: RateLimitSnapshot | None = None
    visible_models: list[NonEmptyStr] = Field(default_factory=list)
    evidence_hash: NonEmptyStr | None = None
    reason_codes: list[NonEmptyStr] = Field(default_factory=list)
    captured_at: datetime = Field(default_factory=utc_now)

    @model_validator(mode="after")
    def reject_raw_secret_storage(self) -> AccountSnapshot:
        if self.raw_secret_present:
            raise ValueError("AccountSnapshot cannot contain a raw secret")
        if self.secret_ref is not None:
            _validate_secret_ref(self.secret_ref)
        return self


def _validate_secret_ref(secret_ref: str) -> None:
    if not secret_ref:
        raise ValueError("secret_ref must be non-empty when provided")
    if not secret_ref.startswith(_ALLOWED_SECRET_REF_PREFIXES):
        raise ValueError("secret_ref must use a local reference prefix")
    for pattern in _RAW_SECRET_VALUE_PATTERNS:
        if pattern.search(secret_ref):
            raise ValueError("secret_ref looks like a raw credential")
