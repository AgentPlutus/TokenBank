"""Cost accounting helpers derived from persisted result envelopes."""

from __future__ import annotations

from typing import Any

from tokenbank.models.cost_quality import HostCostQualitySummary

LOCAL_ZERO_COST_CAVEAT = (
    "Phase 0 local backend uses zero_internal_phase0 cost accounting."
)
ESTIMATED_ONLY_CAVEAT = "Cost is estimated_only; no measured provider charge exists."


def effective_cost_micros(result_body: dict[str, Any]) -> int:
    actual = _non_negative_int(result_body.get("actual_cost_micros"))
    estimated = _non_negative_int(result_body.get("cost_estimate_micros"))
    if actual > 0:
        return actual
    return estimated


def host_cost_quality_summary(
    *,
    result_body: dict[str, Any],
    verifier_body: dict[str, Any],
    baseline_mode: str = "none",
    baseline_cost_micros: int | None = None,
    saving_ratio_bps: int | None = None,
) -> HostCostQualitySummary:
    cost_source = str(result_body.get("cost_source") or "not_applicable")
    cost_confidence = str(result_body.get("cost_confidence") or "not_applicable")
    recommendation = str(verifier_body.get("recommendation") or "")
    verifier_status = str(verifier_body.get("status") or "unknown")
    caveats = cost_caveats(result_body)
    if baseline_mode == "none":
        caveats.append("baseline_mode=none; no savings claim is generated.")
    return HostCostQualitySummary(
        estimated_cost_micros=_non_negative_int(
            result_body.get("cost_estimate_micros")
        ),
        actual_cost_micros=_non_negative_int(result_body.get("actual_cost_micros")),
        cost_source=cost_source,  # type: ignore[arg-type]
        cost_confidence=cost_confidence,  # type: ignore[arg-type]
        baseline_mode=baseline_mode,
        baseline_cost_micros=baseline_cost_micros,
        saving_ratio_bps=saving_ratio_bps,
        primary_model_fallback_used=_is_primary_model_fallback(result_body),
        primary_model_fallback_cost_micros=(
            effective_cost_micros(result_body)
            if _is_primary_model_fallback(result_body)
            else 0
        ),
        local_zero_cost_caveat=(
            LOCAL_ZERO_COST_CAVEAT if cost_source == "zero_internal_phase0" else None
        ),
        verifier_passed=verifier_status in {"passed", "needs_review"},
        quality_status=_quality_status(verifier_status),
        audit_status=_audit_status(recommendation, verifier_status),
        caveats=caveats,
    )


def cost_caveats(result_body: dict[str, Any]) -> list[str]:
    caveats: list[str] = []
    cost_source = result_body.get("cost_source")
    if cost_source == "zero_internal_phase0":
        caveats.append(LOCAL_ZERO_COST_CAVEAT)
    if cost_source == "estimated":
        caveats.append(ESTIMATED_ONLY_CAVEAT)
    if cost_source == "policy_default":
        caveats.append("Cost comes from policy_default config, not measurement.")
    return caveats


def primary_model_fallback_cost(rows: list[dict[str, Any]]) -> int:
    return sum(
        effective_cost_micros(row["result_body"])
        for row in rows
        if _is_primary_model_fallback(row["result_body"])
    )


def _is_primary_model_fallback(result_body: dict[str, Any]) -> bool:
    backend_class = result_body.get("backend_class")
    backend_id = str(result_body.get("backend_id") or "")
    return backend_class == "primary_model_gateway" or "primary_gateway" in backend_id


def _quality_status(verifier_status: str) -> str:
    if verifier_status == "passed":
        return "passed"
    if verifier_status == "needs_review":
        return "needs_review"
    if verifier_status == "failed":
        return "failed"
    return "unknown"


def _audit_status(recommendation: str, verifier_status: str) -> str:
    if recommendation == "quarantine":
        return "quarantined"
    if verifier_status == "needs_review":
        return "warning"
    if verifier_status == "passed":
        return "clean"
    if verifier_status == "failed":
        return "warning"
    return "unknown"


def _non_negative_int(value: Any) -> int:
    if isinstance(value, bool):
        return 0
    if isinstance(value, int) and value >= 0:
        return value
    return 0
