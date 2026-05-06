"""Shared redaction helpers."""

from __future__ import annotations

import re
from typing import Any

DEFAULT_TOKEN_PREFIX_PATTERNS = (
    r"tbk_h_[A-Za-z0-9_]+",
    r"tbk_w_[A-Za-z0-9_]+",
    r"tbk_i_[A-Za-z0-9_]+",
)
SECRET_KEY_FRAGMENTS = (
    "api_key",
    "apikey",
    "bearer",
    "cookie",
    "credential",
    "oauth",
    "provider_secret",
    "provider_token",
    "refresh_token",
    "secret",
    "token",
)
SECRET_VALUE_PATTERNS = (
    r"sk-[A-Za-z0-9_-]+",
    r"(?i)bearer\s+[A-Za-z0-9._~+/=-]+",
    r"tbk_h_[A-Za-z0-9_]+",
    r"tbk_w_[A-Za-z0-9_]+",
    r"tbk_i_[A-Za-z0-9_]+",
    r"tbk_l_[A-Za-z0-9_-]+",
)


def redact_token_prefixes(
    text: str,
    patterns: list[str] | tuple[str, ...] = DEFAULT_TOKEN_PREFIX_PATTERNS,
    replacement: str = "[REDACTED_TOKEN]",
) -> str:
    redacted = text
    for pattern in patterns:
        redacted = re.sub(pattern, replacement, redacted)
    return redacted


def redact_sensitive_value(value: Any) -> Any:
    """Recursively redact credential-like keys and secret-like strings."""
    if isinstance(value, dict):
        redacted: dict[str, Any] = {}
        for key, nested in value.items():
            normalized_key = str(key).lower().replace("-", "_")
            if any(fragment in normalized_key for fragment in SECRET_KEY_FRAGMENTS):
                redacted[key] = "[REDACTED_SECRET]"
            else:
                redacted[key] = redact_sensitive_value(nested)
        return redacted
    if isinstance(value, list):
        return [redact_sensitive_value(item) for item in value]
    if isinstance(value, str):
        redacted = value
        for pattern in SECRET_VALUE_PATTERNS:
            redacted = re.sub(pattern, "[REDACTED_SECRET]", redacted)
        return redacted
    return value
