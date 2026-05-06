"""Backend error normalization."""

from __future__ import annotations

from typing import Any

from tokenbank.models.backend import BackendError

SECRET_VALUE_MARKERS = ("Bearer ", "sk-", "tbk_", "TOKENBANK_")
SECRET_KEY_FRAGMENTS = ("credential", "secret", "token")


def redact_backend_value(value: Any) -> Any:
    if isinstance(value, dict):
        redacted: dict[str, Any] = {}
        for key, nested in value.items():
            normalized_key = str(key).lower()
            if any(fragment in normalized_key for fragment in SECRET_KEY_FRAGMENTS):
                redacted[key] = "[REDACTED_SECRET]"
            else:
                redacted[key] = redact_backend_value(nested)
        return redacted
    if isinstance(value, list):
        return [redact_backend_value(item) for item in value]
    if isinstance(value, str) and any(
        marker in value
        for marker in SECRET_VALUE_MARKERS
    ):
        return "[REDACTED_SECRET]"
    return value


def normalize_backend_error(
    *,
    error_code: str,
    error_message: str,
    retryable: bool = False,
    fallbackable: bool = False,
    details: dict[str, Any] | None = None,
) -> BackendError:
    return BackendError(
        error_code=error_code,
        error_message=error_message,
        retryable=retryable,
        fallbackable=fallbackable,
        redacted_details=redact_backend_value(details or {}),
    )
