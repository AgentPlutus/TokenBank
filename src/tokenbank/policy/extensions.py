"""Forbidden extension key and path linting."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

FORBIDDEN_EXTENSION_KEY_FRAGMENTS = frozenset(
    {
        "seller",
        "marketplace",
        "payment",
        "payout",
        "settlement",
        "yield",
        "apr",
        "credit_trading",
        "account_pool",
        "oauth_proxy",
        "credential_broker",
    }
)


@dataclass(frozen=True)
class ExtensionLintIssue:
    path: str
    key: str
    reason: str


def normalize_key(key: str) -> str:
    return key.lower().replace("-", "_").replace(" ", "_")


def lint_extension_keys(value: Any, path: str = "$") -> list[ExtensionLintIssue]:
    issues: list[ExtensionLintIssue] = []
    if isinstance(value, Mapping):
        for key, nested in value.items():
            key_text = str(key)
            normalized = normalize_key(key_text)
            for fragment in FORBIDDEN_EXTENSION_KEY_FRAGMENTS:
                if fragment in normalized:
                    issues.append(
                        ExtensionLintIssue(
                            path=f"{path}.{key_text}",
                            key=key_text,
                            reason=f"forbidden extension key fragment: {fragment}",
                        )
                    )
                    break
            issues.extend(lint_extension_keys(nested, f"{path}.{key_text}"))
    elif isinstance(value, list):
        for index, nested in enumerate(value):
            issues.extend(lint_extension_keys(nested, f"{path}[{index}]"))
    return issues

