"""Deterministic token estimate helpers for WP-RB2."""

from __future__ import annotations

from math import ceil
from typing import Any

from tokenbank.core.canonical import canonical_json_dumps
from tokenbank.models.task_analysis import TokenEstimate

TOKENIZER_PROFILE_ID = "heuristic:cl100k_like:v0"

_DEFAULT_OUTPUT_TOKENS_BY_TASK_TYPE = {
    "url_check": 64,
    "dedup": 128,
    "webpage_extraction": 512,
    "topic_classification": 96,
    "claim_extraction": 512,
}


def estimate_tokens(
    *,
    task_type: str,
    inline_input: dict[str, Any],
) -> TokenEstimate:
    """Estimate tokens without calling a model or provider tokenizer service."""
    serialized = canonical_json_dumps(inline_input)
    input_tokens = _estimate_text_tokens(serialized)
    output_tokens = _estimated_output_tokens(
        task_type=task_type,
        inline_input=inline_input,
    )
    return TokenEstimate(
        tokenizer_profile_id=TOKENIZER_PROFILE_ID,
        estimated_input_tokens=input_tokens,
        estimated_output_tokens=output_tokens,
        estimated_total_tokens=input_tokens + output_tokens,
        confidence=0.62,
        method="chars_div_4_plus_task_default_output",
    )


def _estimate_text_tokens(text: str) -> int:
    if not text:
        return 0
    return max(1, ceil(len(text) / 4))


def _estimated_output_tokens(
    *,
    task_type: str,
    inline_input: dict[str, Any],
) -> int:
    default = _DEFAULT_OUTPUT_TOKENS_BY_TASK_TYPE.get(task_type, 256)
    if task_type == "dedup":
        items = inline_input.get("items")
        if isinstance(items, list):
            return max(default, len(items) * 12)
    if task_type == "claim_extraction":
        text = inline_input.get("text")
        if isinstance(text, str):
            return max(default, min(2_048, ceil(len(text) / 12)))
    if task_type == "webpage_extraction":
        text = inline_input.get("text") or inline_input.get("html")
        if isinstance(text, str):
            return max(default, min(2_048, ceil(len(text) / 16)))
    return default
