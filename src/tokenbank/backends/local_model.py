"""Local model backend scaffold."""

from __future__ import annotations

from datetime import UTC, datetime

from tokenbank.backends.adapter import BackendExecutionContext, build_result_envelope
from tokenbank.backends.errors import normalize_backend_error
from tokenbank.backends.usage import make_usage_record
from tokenbank.models.result_envelope import WorkUnitResultEnvelope


class LocalModelAdapter:
    backend_class = "local_model"

    def execute(self, context: BackendExecutionContext) -> WorkUnitResultEnvelope:
        started_at = datetime.now(UTC)
        usage = [
            make_usage_record(
                work_unit_id=context.work_unit_id,
                attempt_id=context.attempt_id,
                backend_id=context.backend_id,
                cost_source="zero_internal_phase0",
                cost_confidence="low",
            )
        ]
        error = normalize_backend_error(
            error_code="local_model.not_configured",
            error_message="local_model backend scaffold is not configured in WP9",
            retryable=False,
            fallbackable=True,
        )
        return build_result_envelope(
            context=context,
            output={"ok": False, "reason": "local_model_not_configured"},
            usage_records=usage,
            started_at=started_at,
            status="failed",
            errors=[error],
        )

