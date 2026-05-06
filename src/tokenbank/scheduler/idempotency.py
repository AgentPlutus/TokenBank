"""Idempotency helpers for scheduler handoff stubs."""

from __future__ import annotations

from typing import Any

from tokenbank.core.canonical import canonical_json_hash


def idempotency_key(parts: dict[str, Any]) -> str:
    return "idem_" + canonical_json_hash(parts)[:32]

