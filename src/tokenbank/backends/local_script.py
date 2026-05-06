"""Local script backend scaffold for dedup."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from tokenbank.backends.adapter import BackendExecutionContext, build_result_envelope
from tokenbank.backends.errors import normalize_backend_error
from tokenbank.backends.usage import make_usage_record
from tokenbank.core.canonical import canonical_json_hash
from tokenbank.models.result_envelope import WorkUnitResultEnvelope


class LocalScriptAdapter:
    backend_class = "local_script"

    def execute(self, context: BackendExecutionContext) -> WorkUnitResultEnvelope:
        started_at = datetime.now(UTC)
        usage = [
            make_usage_record(
                work_unit_id=context.work_unit_id,
                attempt_id=context.attempt_id,
                backend_id=context.backend_id,
                cost_source="zero_internal_phase0",
                cost_confidence="high",
            )
        ]
        allowed_hashes = set(
            context.effective_constraints.get("allowed_script_hashes", [])
        )
        script_hash = context.effective_constraints.get("script_hash")
        if script_hash and script_hash not in allowed_hashes:
            error = normalize_backend_error(
                error_code="local_script.hash_not_allowed",
                error_message="local_script scaffold denied unlisted script hash",
                retryable=False,
                fallbackable=False,
                details={"script_hash": script_hash},
            )
            return build_result_envelope(
                context=context,
                output={"ok": False, "reason": "script_hash_not_allowed"},
                usage_records=usage,
                started_at=started_at,
                status="failed",
                errors=[error],
                redacted_logs=["dedup local_script hash allowlist denied execution"],
            )

        items = context.input_payload.get("items", [])
        if not isinstance(items, list):
            error = normalize_backend_error(
                error_code="local_script.bad_input",
                error_message="dedup expects an items list",
                retryable=False,
                fallbackable=False,
            )
            return build_result_envelope(
                context=context,
                output={"ok": False, "reason": "items_must_be_list"},
                usage_records=usage,
                started_at=started_at,
                status="failed",
                errors=[error],
            )

        seen: set[str] = set()
        unique_items: list[Any] = []
        duplicate_count = 0
        for item in items:
            item_hash = canonical_json_hash(item)
            if item_hash in seen:
                duplicate_count += 1
                continue
            seen.add(item_hash)
            unique_items.append(item)

        return build_result_envelope(
            context=context,
            output={
                "ok": True,
                "tool": "dedup",
                "unique_items": unique_items,
                "duplicate_count": duplicate_count,
                "local_script_scaffold": True,
            },
            usage_records=usage,
            started_at=started_at,
            redacted_logs=["dedup local_script scaffold completed"],
        )
