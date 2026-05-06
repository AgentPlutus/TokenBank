"""Redacted worker logging helpers."""

from __future__ import annotations

import re
from pathlib import Path

from tokenbank.policy.redaction import redact_token_prefixes

WORKER_SECRET_PATTERNS = (
    r"tbk_l_[A-Za-z0-9_-]+",
    r"(?i)(authorization:\s*bearer\s+)[^\s]+",
    r"(?i)(worker_token:\s*)[^\s]+",
    r"(?i)(api[_-]?key\s*[:=]\s*)[^\s]+",
)
UNREDACTED_TOKEN_PATTERNS = (
    r"tbk_h_[A-Za-z0-9_]+",
    r"tbk_w_[A-Za-z0-9_]+",
    r"tbk_i_[A-Za-z0-9_]+",
    r"tbk_l_[A-Za-z0-9_-]+",
)


def redact_worker_log(text: str) -> str:
    redacted = redact_token_prefixes(text)
    redacted = re.sub(WORKER_SECRET_PATTERNS[0], "[REDACTED_LEASE_TOKEN]", redacted)
    for pattern in WORKER_SECRET_PATTERNS[1:]:
        redacted = re.sub(pattern, r"\1[REDACTED_SECRET]", redacted)
    return redacted


def contains_unredacted_worker_secret(text: str) -> bool:
    return any(re.search(pattern, text) for pattern in UNREDACTED_TOKEN_PATTERNS)


class WorkerLog:
    def __init__(self, path: Path):
        self.path = path
        self.path.parent.mkdir(parents=True, exist_ok=True)

    def write(self, message: str) -> None:
        redacted = redact_worker_log(message)
        if contains_unredacted_worker_secret(redacted):
            raise ValueError("worker log still contains a secret-like token")
        with self.path.open("a", encoding="utf-8") as handle:
            handle.write(redacted)
            handle.write("\n")
