"""VerifierReport construction helpers."""

from __future__ import annotations

from datetime import UTC, datetime

from tokenbank.core.canonical import canonical_json_hash
from tokenbank.models.common import VerifierCheckResult
from tokenbank.models.result_envelope import WorkUnitResultEnvelope
from tokenbank.models.verifier import VerifierReport


def build_verifier_report(
    *,
    recipe_id: str,
    envelope: WorkUnitResultEnvelope,
    checks: list[VerifierCheckResult],
    recommendation: str,
    metadata: dict,
) -> VerifierReport:
    report_id = "vr_" + canonical_json_hash(
        {
            "recipe_id": recipe_id,
            "result_envelope_id": envelope.result_envelope_id,
            "recommendation": recommendation,
            "check_names": [check.name for check in checks],
        }
    )[:24]
    return VerifierReport(
        verifier_report_id=report_id,
        work_unit_id=envelope.work_unit_id,
        result_envelope_id=envelope.result_envelope_id,
        verifier_recipe_id=recipe_id,
        status=_status_for_recommendation(recommendation),
        recommendation=recommendation,  # type: ignore[arg-type]
        checks=checks,
        output_hash=envelope.output_hash or "missing_output_hash",
        result_hash=envelope.result_hash or "missing_result_hash",
        metadata=metadata,
        created_at=datetime.now(UTC),
    )


def _status_for_recommendation(recommendation: str) -> str:
    if recommendation == "accept":
        return "passed"
    if recommendation == "accept_with_warning":
        return "needs_review"
    return "failed"

