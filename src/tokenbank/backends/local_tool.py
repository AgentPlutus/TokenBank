"""Local tool backend adapter for VS0 url_check."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any
from urllib.parse import urlsplit

from tokenbank.backends.adapter import BackendExecutionContext, build_result_envelope
from tokenbank.backends.errors import normalize_backend_error
from tokenbank.backends.usage import make_usage_record
from tokenbank.core.canonical import canonical_url
from tokenbank.models.result_envelope import WorkUnitResultEnvelope


class LocalToolAdapter:
    backend_class = "local_tool"

    def execute(self, context: BackendExecutionContext) -> WorkUnitResultEnvelope:
        started_at = datetime.now(UTC)
        url = _extract_url(context.input_payload, context.effective_constraints)
        usage = [
            make_usage_record(
                work_unit_id=context.work_unit_id,
                attempt_id=context.attempt_id,
                backend_id=context.backend_id,
                cost_source="zero_internal_phase0",
                cost_confidence="high",
            )
        ]
        if not _is_http_url(url):
            error = normalize_backend_error(
                error_code="local_tool.bad_input",
                error_message="url_check requires an explicit http or https URL",
                retryable=False,
                fallbackable=False,
                details={"task_type": context.task_type},
            )
            return build_result_envelope(
                context=context,
                output={"ok": False, "reason": "invalid_url"},
                usage_records=usage,
                started_at=started_at,
                status="failed",
                errors=[error],
                redacted_logs=["url_check rejected invalid input"],
            )

        normalized = canonical_url(url)
        output = {
            "ok": True,
            "tool": "url_check",
            "url": normalized,
            "scheme": urlsplit(normalized).scheme,
            "host": urlsplit(normalized).hostname,
            "network_checked": False,
            "local_tool_stub": True,
            "phase0_local_stub": True,
        }
        return build_result_envelope(
            context=context,
            output=output,
            usage_records=usage,
            started_at=started_at,
            redacted_logs=["url_check completed without external provider call"],
        )


def _extract_url(*payloads: dict[str, Any]) -> str | None:
    for payload in payloads:
        for key in ("url", "target_url"):
            value = payload.get(key)
            if isinstance(value, str):
                return value
        for key in ("input", "inline_input", "body"):
            nested = payload.get(key)
            if isinstance(nested, dict):
                value = _extract_url(nested)
                if value is not None:
                    return value
    return None


def _is_http_url(url: str | None) -> bool:
    if not url:
        return False
    parts = urlsplit(url)
    return parts.scheme in {"http", "https"} and bool(parts.netloc)
