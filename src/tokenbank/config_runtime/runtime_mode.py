"""Runtime mode handling for TokenBank."""

from __future__ import annotations

from enum import StrEnum


class RuntimeMode(StrEnum):
    DEMO = "demo"
    INTERNAL_SECURE = "internal_secure"
    ALPHA = "alpha"


def runtime_mode_defaults(mode: RuntimeMode | str) -> dict[str, object]:
    runtime_mode = RuntimeMode(mode)
    if runtime_mode is RuntimeMode.DEMO:
        return {
            "localhost_lan_only": True,
            "static_tokens_allowed": True,
            "foreground_worker": True,
            "strict_report_redaction": False,
        }
    if runtime_mode is RuntimeMode.INTERNAL_SECURE:
        return {
            "localhost_lan_only": True,
            "static_tokens_allowed": False,
            "foreground_worker": True,
            "strict_report_redaction": True,
        }
    return {
        "localhost_lan_only": False,
        "static_tokens_allowed": False,
        "foreground_worker": False,
        "strict_report_redaction": True,
    }

