"""Routebook V1 route decision trace DTOs."""

from __future__ import annotations

from typing import Literal

from pydantic import Field

from tokenbank.models.base import TokenBankModel
from tokenbank.models.common import NonEmptyStr

HardFilterDecision = Literal["pass", "fail"]
RouteSelectionStatus = Literal[
    "selected_highest_scoring_candidate",
    "no_passing_candidate_keep_existing_selection",
]


class CandidateScore(TokenBankModel):
    total: float = Field(ge=0.0, le=1.0)
    capability_fit: float = Field(default=0.0, ge=0.0, le=1.0)
    policy_fit: float = Field(default=1.0, ge=0.0, le=1.0)
    quality_fit: float = Field(default=0.0, ge=0.0, le=1.0)
    cost_fit: float = Field(default=0.0, ge=0.0, le=1.0)
    latency_fit: float = Field(default=0.0, ge=0.0, le=1.0)
    trust_fit: float = Field(default=1.0, ge=0.0, le=1.0)
    uncertainty_penalty: float = Field(default=0.0, ge=0.0, le=1.0)


class CandidateScoreTrace(TokenBankModel):
    candidate_id: NonEmptyStr
    score: CandidateScore
    rank: int | None = Field(default=None, ge=1)
    hard_filter_decision: HardFilterDecision = "pass"
    hard_filter_results: dict[NonEmptyStr, NonEmptyStr] = Field(default_factory=dict)
    weighted_components: dict[NonEmptyStr, float] = Field(default_factory=dict)
    reason_codes: list[NonEmptyStr] = Field(default_factory=list)


class RejectedCandidateTrace(TokenBankModel):
    candidate_id: NonEmptyStr
    reason_codes: list[NonEmptyStr] = Field(default_factory=list)


class RouteDecisionTrace(TokenBankModel):
    """Host-safe explanation for a RoutePlan selection."""

    route_decision_id: NonEmptyStr
    route_plan_id: NonEmptyStr
    work_unit_id: NonEmptyStr
    routebook_id: NonEmptyStr
    routebook_version: NonEmptyStr
    task_analysis_hash: NonEmptyStr | None = None
    task_profile_hash: NonEmptyStr
    capacity_snapshot_hash: NonEmptyStr
    selected_candidate_id: NonEmptyStr
    candidate_scores: list[CandidateScoreTrace] = Field(default_factory=list)
    rejected_candidates: list[RejectedCandidateTrace] = Field(default_factory=list)
    estimate_summary: dict[NonEmptyStr, object] = Field(default_factory=dict)
    reason_codes: list[NonEmptyStr] = Field(default_factory=list)
    rule_ids: list[NonEmptyStr] = Field(default_factory=list)
    user_summary: NonEmptyStr


class RouteScoringReport(TokenBankModel):
    """Deterministic WP-RB3 scoring report for a RoutePlan candidate set."""

    route_scoring_id: NonEmptyStr
    route_plan_id: NonEmptyStr
    work_unit_id: NonEmptyStr
    routebook_id: NonEmptyStr
    routebook_version: NonEmptyStr
    scorer_id: NonEmptyStr
    scorer_version: NonEmptyStr
    baseline_selected_candidate_id: NonEmptyStr
    selected_candidate_id: NonEmptyStr
    selection_status: RouteSelectionStatus
    score_weights: dict[NonEmptyStr, float] = Field(default_factory=dict)
    candidate_scores: list[CandidateScoreTrace] = Field(default_factory=list)
    rejected_candidates: list[RejectedCandidateTrace] = Field(default_factory=list)
    reason_codes: list[NonEmptyStr] = Field(default_factory=list)
