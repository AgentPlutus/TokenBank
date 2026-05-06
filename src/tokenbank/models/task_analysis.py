"""Routebook V1 task analysis DTOs."""

from __future__ import annotations

from typing import Literal

from pydantic import Field, NonNegativeInt

from tokenbank.models.base import TokenBankModel
from tokenbank.models.common import NonEmptyStr, PrivacyLevel, TaskLevel
from tokenbank.models.task_profile import TaskDifficulty

TaskAnalysisSource = Literal[
    "deterministic_preflight",
    "lightweight_model",
    "escalation_profiler",
]
PreflightDecision = Literal["allow", "deny"]


class InputShape(TokenBankModel):
    explicit_refs_count: NonNegativeInt = 0
    explicit_urls_count: NonNegativeInt = 0
    file_refs_count: NonNegativeInt = 0
    inline_chars: NonNegativeInt = 0
    inline_bytes: NonNegativeInt = 0
    json_depth: NonNegativeInt = 0
    list_items_count: NonNegativeInt = 0
    workspace_scan_requested: bool = False


class TokenEstimate(TokenBankModel):
    tokenizer_profile_id: NonEmptyStr
    estimated_input_tokens: NonNegativeInt
    estimated_output_tokens: NonNegativeInt
    estimated_total_tokens: NonNegativeInt
    confidence: float = Field(ge=0.0, le=1.0)
    method: NonEmptyStr


class CostEstimate(TokenBankModel):
    cost_profile_id: NonEmptyStr
    min_cost_micros: NonNegativeInt = 0
    expected_cost_micros: NonNegativeInt = 0
    max_cost_micros: NonNegativeInt = 0
    confidence: float = Field(ge=0.0, le=1.0)
    cost_source: NonEmptyStr = "estimate"


class PrivacyScan(TokenBankModel):
    raw_secret_detected: bool = False
    possible_secret_detected: bool = False
    private_data_detected: bool = False
    remote_eligible: bool = True
    matched_signal_counts: dict[NonEmptyStr, NonNegativeInt] = Field(
        default_factory=dict
    )
    reason_codes: list[NonEmptyStr] = Field(default_factory=list)


class ComplexityEstimate(TokenBankModel):
    difficulty: TaskDifficulty = "medium"
    estimated_attempts: float = Field(default=1.0, ge=1.0)
    requires_strong_reasoning: bool = False
    requires_long_context: bool = False
    requires_tools: bool = False
    reason_codes: list[NonEmptyStr] = Field(default_factory=list)


class TaskAnalysisReport(TokenBankModel):
    """Deterministic pre-route analysis artifact.

    This object is advisory evidence for routing. It does not execute work and
    cannot lower the WorkUnit privacy or risk level.
    """

    task_analysis_id: NonEmptyStr
    work_unit_id: NonEmptyStr
    source: TaskAnalysisSource = "deterministic_preflight"
    routebook_id: NonEmptyStr
    routebook_version: NonEmptyStr
    task_type: NonEmptyStr
    input_shape: InputShape
    token_estimate: TokenEstimate
    cost_estimate: CostEstimate
    privacy_scan: PrivacyScan
    complexity: ComplexityEstimate
    effective_task_level: TaskLevel
    effective_privacy_level: PrivacyLevel
    preflight_decision: PreflightDecision = "allow"
    confidence: float = Field(ge=0.0, le=1.0)
    reason_codes: list[NonEmptyStr] = Field(default_factory=list)
