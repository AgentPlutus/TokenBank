"""Common verifier checks."""

from __future__ import annotations

import re
from typing import Any

from jsonschema import Draft202012Validator, ValidationError

from tokenbank.core.canonical import output_hash, result_hash
from tokenbank.models.common import VerifierCheckResult
from tokenbank.models.result_envelope import WorkUnitResultEnvelope
from tokenbank.verifier.recipes import VerifierRecipe

SECRET_PATTERNS = (
    r"sk-[A-Za-z0-9_-]+",
    r"tbk_[hwil]_[A-Za-z0-9_-]+",
    r"(?i)authorization:\s*bearer\s+[^\s]+",
)


def passed_check(name: str, message: str = "", **metadata: Any) -> VerifierCheckResult:
    return VerifierCheckResult(
        name=name,
        status="passed",
        message=message or "passed",
        metadata=metadata,
    )


def failed_check(
    name: str,
    message: str,
    *,
    observed_hash: str | None = None,
    **metadata: Any,
) -> VerifierCheckResult:
    return VerifierCheckResult(
        name=name,
        status="failed",
        message=message,
        observed_hash=observed_hash,
        metadata=metadata,
    )


def warning_check(name: str, message: str, **metadata: Any) -> VerifierCheckResult:
    return VerifierCheckResult(
        name=name,
        status="needs_review",
        message=message,
        metadata=metadata,
    )


def skipped_check(name: str, message: str, **metadata: Any) -> VerifierCheckResult:
    return VerifierCheckResult(
        name=name,
        status="skipped",
        message=message,
        metadata=metadata,
    )


def check_envelope_integrity(
    envelope: WorkUnitResultEnvelope,
) -> list[VerifierCheckResult]:
    checks: list[VerifierCheckResult] = []
    required = {
        "result_envelope_id": envelope.result_envelope_id,
        "work_unit_id": envelope.work_unit_id,
        "attempt_id": envelope.attempt_id,
        "assignment_id": envelope.assignment_id,
    }
    missing = [key for key, value in required.items() if not value]
    if missing:
        checks.append(
            failed_check(
                "result_envelope_integrity",
                "result envelope is missing required identifiers",
                missing=missing,
            )
        )
    else:
        checks.append(passed_check("result_envelope_integrity"))
    return checks


def check_hashes(envelope: WorkUnitResultEnvelope) -> list[VerifierCheckResult]:
    checks: list[VerifierCheckResult] = []
    if not envelope.output_hash:
        checks.append(failed_check("output_hash_present", "output_hash is missing"))
        return checks

    expected_output_hash = output_hash(envelope.output)
    if expected_output_hash != envelope.output_hash:
        checks.append(
            failed_check(
                "output_hash_valid",
                "output_hash does not match output",
                observed_hash=expected_output_hash,
            )
        )
    else:
        checks.append(
            passed_check(
                "output_hash_valid",
                observed_hash=expected_output_hash,
            )
        )

    expected_result_hash = expected_envelope_result_hash(envelope)
    if expected_result_hash != envelope.result_hash:
        checks.append(
            failed_check(
                "result_hash_valid",
                "result_hash does not match result envelope",
                observed_hash=expected_result_hash,
            )
        )
    else:
        checks.append(
            passed_check(
                "result_hash_valid",
                observed_hash=expected_result_hash,
            )
        )
    return checks


def expected_envelope_result_hash(envelope: WorkUnitResultEnvelope) -> str:
    return result_hash(
        {
            "work_unit_id": envelope.work_unit_id,
            "attempt_id": envelope.attempt_id,
            "assignment_id": envelope.assignment_id,
            "backend_id": envelope.backend_id,
            "backend_class": envelope.backend_class,
            "output_hash": envelope.output_hash,
            "status": envelope.status,
            "usage_record_ids": [
                record.usage_record_id
                for record in envelope.usage_records
            ],
            "error_codes": [
                error.error_code
                for error in envelope.errors
            ],
        }
    )


def check_policy_linkage(
    *,
    envelope: WorkUnitResultEnvelope,
    policy_decision: dict[str, Any] | None,
) -> list[VerifierCheckResult]:
    if policy_decision is None:
        return [
            skipped_check(
                "policy_linkage",
                "policy decision linkage not provided to verifier runner",
            )
        ]
    if policy_decision.get("work_unit_id") != envelope.work_unit_id:
        return [
            failed_check(
                "policy_linkage",
                "policy decision work_unit_id does not match result envelope",
            )
        ]
    if policy_decision.get("decision") != "approved":
        return [failed_check("policy_linkage", "policy decision is not approved")]
    return [passed_check("policy_linkage")]


def check_secret_redaction(
    envelope: WorkUnitResultEnvelope,
) -> list[VerifierCheckResult]:
    leaks = list(_secret_paths(envelope.model_dump(mode="json")))
    if leaks:
        return [
            failed_check(
                "secret_redaction",
                "result envelope contains unredacted secret-like values",
                leaks=leaks,
            )
        ]
    return [passed_check("secret_redaction")]


def _secret_paths(value: Any, path: str = "$"):
    if isinstance(value, dict):
        for key, nested in value.items():
            yield from _secret_paths(nested, f"{path}.{key}")
    elif isinstance(value, list):
        for index, nested in enumerate(value):
            yield from _secret_paths(nested, f"{path}[{index}]")
    elif isinstance(value, str) and any(
        re.search(pattern, value)
        for pattern in SECRET_PATTERNS
    ):
        yield path


def check_output_schema(
    *,
    envelope: WorkUnitResultEnvelope,
    recipe: VerifierRecipe,
    work_unit: dict[str, Any] | None = None,
) -> list[VerifierCheckResult]:
    schema = {}
    if work_unit is not None and isinstance(work_unit.get("output_schema"), dict):
        schema = dict(work_unit["output_schema"])
    if not schema:
        schema = recipe.output_schema
    if not schema:
        return [skipped_check("output_schema", "no output schema configured")]
    try:
        Draft202012Validator(schema).validate(envelope.output)
    except ValidationError as exc:
        return [
            failed_check(
                "output_schema",
                "output does not validate against configured schema",
                error_path=list(exc.path),
            )
        ]
    return [passed_check("output_schema")]
