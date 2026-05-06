"""Shared router response helpers."""

from __future__ import annotations


def not_implemented(component: str) -> dict[str, str]:
    return {
        "status": "not_implemented",
        "component": component,
        "reason": "Downstream WP5+ runtime module is not implemented yet.",
    }

