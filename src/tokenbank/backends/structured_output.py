"""Structured output validation and repair stubs for model gateways."""

from __future__ import annotations

from typing import Any


def validate_structured_output(output: dict[str, Any]) -> bool:
    return isinstance(output, dict) and "structured_output" in output


def repair_structured_output_stub(output: dict[str, Any]) -> dict[str, Any]:
    if validate_structured_output(output):
        return output
    return {
        "structured_output": output,
        "repair_applied": True,
    }

