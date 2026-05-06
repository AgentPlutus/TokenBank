"""Base Pydantic DTO primitives for TokenBank."""

from __future__ import annotations

from collections.abc import Mapping
from datetime import UTC, datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, model_validator

FORBIDDEN_FIELD_KEY_FRAGMENTS = frozenset(
    {
        "seller",
        "buyer",
        "marketplace",
        "payment",
        "payout",
        "settlement",
        "yield",
        "credit_trading",
        "account_pool",
        "oauth",
        "cookie",
        "api_key",
        "api_key_sharing",
    }
)
FORBIDDEN_EXACT_FIELD_KEYS = frozenset({"apr"})


def utc_now() -> datetime:
    return datetime.now(UTC)


def _normalized_key(key: str) -> str:
    return key.lower().replace("-", "_").replace(" ", "_")


def _reject_forbidden_keys(value: Any, path: str = "$") -> None:
    if isinstance(value, Mapping):
        for key, nested_value in value.items():
            if isinstance(key, str):
                normalized = _normalized_key(key)
                if normalized in FORBIDDEN_EXACT_FIELD_KEYS or any(
                    fragment in normalized
                    for fragment in FORBIDDEN_FIELD_KEY_FRAGMENTS
                ):
                    raise ValueError(f"Forbidden Phase 0 field at {path}.{key}")
            _reject_forbidden_keys(nested_value, f"{path}.{key}")
    elif isinstance(value, list):
        for index, item in enumerate(value):
            _reject_forbidden_keys(item, f"{path}[{index}]")


class TokenBankModel(BaseModel):
    """Base model for JSON-first Phase 0 DTOs."""

    model_config = ConfigDict(
        extra="forbid",
        populate_by_name=True,
        str_strip_whitespace=True,
        validate_assignment=True,
    )

    schema_version: Literal["p0.v1"] = "p0.v1"

    @model_validator(mode="before")
    @classmethod
    def reject_forbidden_phase0_fields(cls, data: Any) -> Any:
        _reject_forbidden_keys(data)
        return data
