"""BackendAdapter interface and ResultEnvelope builder."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any, Protocol

from tokenbank.core.canonical import canonical_json_hash, output_hash, result_hash
from tokenbank.models.backend import BackendError, UsageRecord
from tokenbank.models.common import BackendClass, CostConfidence, CostSource
from tokenbank.models.result_envelope import WorkUnitResultEnvelope

KNOWN_BACKEND_CLASSES: set[str] = {
    "api_model_gateway",
    "browser_fetch",
    "local_model",
    "local_script",
    "local_tool",
    "primary_model_gateway",
}


@dataclass(frozen=True)
class BackendExecutionContext:
    work_unit_id: str
    run_id: str
    attempt_id: str
    assignment_id: str
    backend_id: str
    backend_class: str
    task_type: str
    input_payload: dict[str, Any] = field(default_factory=dict)
    effective_constraints: dict[str, Any] = field(default_factory=dict)
    provider_id: str | None = None
    model_id: str | None = None
    worker_id: str | None = None
    capacity_node_id: str | None = None
    provider_token: str | None = field(default=None, repr=False, compare=False)


class BackendAdapter(Protocol):
    backend_class: str

    def execute(self, context: BackendExecutionContext) -> WorkUnitResultEnvelope:
        """Execute backend work and return a result envelope."""


class UnsupportedBackendAdapter:
    backend_class = "unsupported"

    def execute(self, context: BackendExecutionContext) -> WorkUnitResultEnvelope:
        from datetime import UTC, datetime

        from tokenbank.backends.errors import normalize_backend_error
        from tokenbank.backends.usage import make_usage_record

        started_at = datetime.now(UTC)
        error = normalize_backend_error(
            error_code="backend.unsupported",
            error_message=f"unsupported backend_class: {context.backend_class}",
            retryable=False,
            fallbackable=True,
            details={"backend_id": context.backend_id},
        )
        usage = [
            make_usage_record(
                work_unit_id=context.work_unit_id,
                attempt_id=context.attempt_id,
                backend_id=context.backend_id,
                cost_source="not_applicable",
                cost_confidence="not_applicable",
            )
        ]
        return build_result_envelope(
            context=context,
            output={"ok": False, "reason": "unsupported_backend"},
            usage_records=usage,
            started_at=started_at,
            status="failed",
            errors=[error],
        )


def adapter_for_backend_class(backend_class: str) -> BackendAdapter:
    if backend_class == "api_model_gateway":
        from tokenbank.backends.api_model_gateway import APIModelGatewayAdapter

        return APIModelGatewayAdapter()
    if backend_class == "browser_fetch":
        from tokenbank.backends.browser_fetch import BrowserFetchAdapter

        return BrowserFetchAdapter()
    if backend_class == "local_model":
        from tokenbank.backends.local_model import LocalModelAdapter

        return LocalModelAdapter()
    if backend_class == "local_script":
        from tokenbank.backends.local_script import LocalScriptAdapter

        return LocalScriptAdapter()
    if backend_class == "local_tool":
        from tokenbank.backends.local_tool import LocalToolAdapter

        return LocalToolAdapter()
    if backend_class == "primary_model_gateway":
        from tokenbank.backends.primary_model_gateway import PrimaryModelGatewayAdapter

        return PrimaryModelGatewayAdapter()
    return UnsupportedBackendAdapter()


def backend_class_or_none(value: str) -> BackendClass | None:
    return value if value in KNOWN_BACKEND_CLASSES else None  # type: ignore[return-value]


def build_result_envelope(
    *,
    context: BackendExecutionContext,
    output: dict[str, Any],
    usage_records: list[UsageRecord],
    started_at: datetime,
    status: str = "succeeded",
    errors: list[BackendError] | None = None,
    redacted_logs: list[str] | None = None,
    provider_id: str | None = None,
    model_id: str | None = None,
) -> WorkUnitResultEnvelope:
    completed_at = datetime.now(UTC)
    duration_ms = max(0, int((completed_at - started_at).total_seconds() * 1000))
    normalized_errors = errors or []
    out_hash = output_hash(output)
    total_estimated = sum(record.estimated_cost_micros for record in usage_records)
    total_actual = sum(record.actual_cost_micros for record in usage_records)
    cost_source, cost_confidence = _aggregate_cost_metadata(usage_records)
    result_payload = {
        "work_unit_id": context.work_unit_id,
        "attempt_id": context.attempt_id,
        "assignment_id": context.assignment_id,
        "backend_id": context.backend_id,
        "backend_class": context.backend_class,
        "output_hash": out_hash,
        "status": status,
        "usage_record_ids": [record.usage_record_id for record in usage_records],
        "error_codes": [error.error_code for error in normalized_errors],
    }
    res_hash = result_hash(result_payload)
    result_envelope_id = "res_" + canonical_json_hash(result_payload)[:24]
    return WorkUnitResultEnvelope(
        result_envelope_id=result_envelope_id,
        work_unit_id=context.work_unit_id,
        run_id=context.run_id,
        attempt_id=context.attempt_id,
        assignment_id=context.assignment_id,
        status=status,  # type: ignore[arg-type]
        backend_id=context.backend_id,
        backend_class=backend_class_or_none(context.backend_class),
        provider_id=provider_id if provider_id is not None else context.provider_id,
        model_id=model_id if model_id is not None else context.model_id,
        worker_id=context.worker_id,
        capacity_node_id=context.capacity_node_id,
        output=output,
        output_hash=out_hash,
        result_hash=res_hash,
        usage_records=usage_records,
        cost_estimate_micros=total_estimated,
        actual_cost_micros=total_actual,
        cost_source=cost_source,
        cost_confidence=cost_confidence,
        redacted_logs=redacted_logs or [],
        errors=normalized_errors,
        backend_error=normalized_errors[0] if normalized_errors else None,
        started_at=started_at,
        completed_at=completed_at,
        duration_ms=duration_ms,
    )


def _aggregate_cost_metadata(
    usage_records: list[UsageRecord],
) -> tuple[CostSource, CostConfidence]:
    if not usage_records:
        return "not_applicable", "not_applicable"
    source = usage_records[0].cost_source
    confidence = usage_records[0].cost_confidence
    if any(record.cost_source != source for record in usage_records):
        return "estimated", "low"
    return source, confidence
