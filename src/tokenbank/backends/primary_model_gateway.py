"""Primary model gateway fallback adapter scaffold."""

from __future__ import annotations

from datetime import UTC, datetime

from tokenbank.backends.adapter import BackendExecutionContext, build_result_envelope
from tokenbank.backends.api_model_gateway import _control_plane_boundary_error
from tokenbank.backends.errors import normalize_backend_error
from tokenbank.backends.structured_output import repair_structured_output_stub
from tokenbank.backends.usage import make_usage_record
from tokenbank.models.result_envelope import WorkUnitResultEnvelope


class PrimaryModelGatewayAdapter:
    backend_class = "primary_model_gateway"
    provider_protocol = "openai_compatible_single_provider"

    def execute(self, context: BackendExecutionContext) -> WorkUnitResultEnvelope:
        started_at = datetime.now(UTC)
        usage = [
            make_usage_record(
                work_unit_id=context.work_unit_id,
                attempt_id=context.attempt_id,
                backend_id=context.backend_id,
                estimated_cost_micros=1000,
                actual_cost_micros=0,
                cost_source="estimated",
                cost_confidence="low",
            )
        ]
        boundary_error = _control_plane_boundary_error(context)
        if boundary_error is not None:
            return build_result_envelope(
                context=context,
                output={"ok": False, "reason": boundary_error.error_code},
                usage_records=usage,
                started_at=started_at,
                status="failed",
                errors=[boundary_error],
                provider_id=context.provider_id,
                model_id=context.model_id,
            )
        if not context.provider_token:
            error = normalize_backend_error(
                error_code="primary_model_gateway.credentials_missing",
                error_message=(
                    "Primary model gateway provider credential is not configured"
                ),
                retryable=False,
                fallbackable=True,
                details={"provider_id": context.provider_id or "default"},
            )
            return build_result_envelope(
                context=context,
                output={"ok": False, "reason": "credentials_missing"},
                usage_records=usage,
                started_at=started_at,
                status="failed",
                errors=[error],
                provider_id=context.provider_id,
                model_id=context.model_id,
                redacted_logs=["primary_model_gateway credential lookup failed"],
            )

        output = repair_structured_output_stub(
            {
                "ok": True,
                "gateway": "primary_model_gateway",
                "structured_output": {},
                "provider_call_executed": False,
                "control_plane_only": True,
                "fallback_path": True,
            }
        )
        return build_result_envelope(
            context=context,
            output=output,
            usage_records=usage,
            started_at=started_at,
            provider_id=context.provider_id,
            model_id=context.model_id,
            redacted_logs=["primary_model_gateway scaffold completed on control plane"],
        )
