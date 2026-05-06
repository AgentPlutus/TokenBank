"""Local privacy and secret preflight for explicit host inputs."""

from __future__ import annotations

import re
from collections.abc import Iterable
from typing import Any

from tokenbank.models.task_analysis import PrivacyScan

_RAW_SECRET_PATTERNS = {
    "openai_key_shape": re.compile(r"\bsk-[A-Za-z0-9_-]{12,}\b"),
    "github_token_shape": re.compile(r"\bgh[pousr]_[A-Za-z0-9_]{20,}\b"),
    "aws_access_key_shape": re.compile(r"\bAKIA[0-9A-Z]{16}\b"),
    "slack_token_shape": re.compile(r"\bxox[baprs]-[A-Za-z0-9-]{20,}\b"),
    "private_key_block": re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----"),
}
_PRIVATE_DATA_PATTERNS = {
    "email_address": re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b"),
    "us_ssn_shape": re.compile(r"\b\d{3}-\d{2}-\d{4}\b"),
    "phone_number_shape": re.compile(r"\b\+?\d[\d .()-]{8,}\d\b"),
}
_POSSIBLE_SECRET_KEYWORDS = (
    "secret",
    "token",
    "password",
    "bearer",
    "credential",
)
_LONG_OPAQUE_VALUE = re.compile(r"^[A-Za-z0-9_./+=-]{32,}$")


def scan_privacy(value: Any) -> PrivacyScan:
    """Scan explicit input and return redacted privacy signals only."""
    texts = list(_string_values(value))
    raw_counts = _pattern_counts(texts, _RAW_SECRET_PATTERNS)
    private_counts = _pattern_counts(texts, _PRIVATE_DATA_PATTERNS)
    possible_secret_count = _possible_secret_count(value)

    raw_secret_detected = any(count > 0 for count in raw_counts.values())
    possible_secret_detected = raw_secret_detected or possible_secret_count > 0
    private_data_detected = any(count > 0 for count in private_counts.values())

    signal_counts = {
        **raw_counts,
        **private_counts,
    }
    if possible_secret_count:
        signal_counts["possible_secret_shape"] = possible_secret_count
    signal_counts = {
        key: count
        for key, count in signal_counts.items()
        if count > 0
    }

    reason_codes: list[str] = []
    if raw_secret_detected:
        reason_codes.append("raw_secret_shape_detected")
    if possible_secret_detected:
        reason_codes.append("possible_secret_detected")
    if private_data_detected:
        reason_codes.append("private_data_detected")
    if not reason_codes:
        reason_codes.append("no_privacy_signal_detected")

    return PrivacyScan(
        raw_secret_detected=raw_secret_detected,
        possible_secret_detected=possible_secret_detected,
        private_data_detected=private_data_detected,
        remote_eligible=not raw_secret_detected and not private_data_detected,
        matched_signal_counts=signal_counts,
        reason_codes=reason_codes,
    )


def _pattern_counts(
    texts: Iterable[str],
    patterns: dict[str, re.Pattern[str]],
) -> dict[str, int]:
    counts = {name: 0 for name in patterns}
    for text in texts:
        for name, pattern in patterns.items():
            counts[name] += len(pattern.findall(text))
    return counts


def _possible_secret_count(value: Any) -> int:
    count = 0
    if isinstance(value, dict):
        for key, nested in value.items():
            key_text = str(key).lower().replace("-", "_")
            if isinstance(nested, str) and any(
                keyword in key_text
                for keyword in _POSSIBLE_SECRET_KEYWORDS
            ):
                count += 1
            count += _possible_secret_count(nested)
        return count
    if isinstance(value, list):
        return sum(_possible_secret_count(item) for item in value)
    if isinstance(value, str) and _LONG_OPAQUE_VALUE.match(value):
        return 1
    return 0


def _string_values(value: Any) -> Iterable[str]:
    if isinstance(value, dict):
        for nested in value.values():
            yield from _string_values(nested)
        return
    if isinstance(value, list):
        for item in value:
            yield from _string_values(item)
        return
    if isinstance(value, str):
        yield value
