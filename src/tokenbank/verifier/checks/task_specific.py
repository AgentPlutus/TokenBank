"""Task-specific deterministic verifier checks."""

from __future__ import annotations

from tokenbank.models.common import VerifierCheckResult
from tokenbank.models.result_envelope import WorkUnitResultEnvelope
from tokenbank.verifier.checks.common import failed_check, passed_check, warning_check

ALLOWED_CLAIM_TYPES = {"factual", "metric", "policy", "product", "other"}


def run_task_specific_checks(
    *,
    recipe_id: str,
    envelope: WorkUnitResultEnvelope,
) -> list[VerifierCheckResult]:
    if recipe_id == "url_check_v0":
        return _url_check(envelope)
    if recipe_id == "dedup_v0":
        return _dedup(envelope)
    if recipe_id == "topic_classification_v0":
        return _topic_classification(envelope)
    if recipe_id == "claim_extraction_v0":
        return _claim_extraction(envelope)
    if recipe_id == "webpage_extraction_v0":
        return _webpage_extraction(envelope)
    return [failed_check("recipe_known", f"unknown verifier recipe: {recipe_id}")]


def _url_check(envelope: WorkUnitResultEnvelope) -> list[VerifierCheckResult]:
    output = envelope.output
    if output.get("private_ip_denied") or output.get("redirect_denied"):
        return [
            failed_check(
                "url_policy_safety",
                "private IP or redirect denial must quarantine",
            )
        ]
    if output.get("timed_out"):
        return [failed_check("url_timeout", "url_check timed out")]
    status_code = output.get("status_code")
    if status_code is None and output.get("ok") is True:
        return [passed_check("url_status", "url_check output marked ok")]
    if isinstance(status_code, int) and 200 <= status_code < 300:
        return [passed_check("url_status", f"HTTP {status_code}")]
    if isinstance(status_code, int) and 400 <= status_code < 500:
        return [warning_check("url_status", f"HTTP {status_code}")]
    return [failed_check("url_status", "url_check status is not acceptable")]


def _dedup(envelope: WorkUnitResultEnvelope) -> list[VerifierCheckResult]:
    output = envelope.output
    if output.get("overmerge_detected"):
        return [warning_check("dedup_overmerge", "dedup overmerge was detected")]
    if "unique_items" in output and isinstance(output.get("duplicate_count"), int):
        return [passed_check("dedup_exact")]
    return [failed_check("dedup_exact", "dedup output is missing required fields")]


def _topic_classification(
    envelope: WorkUnitResultEnvelope,
) -> list[VerifierCheckResult]:
    output = envelope.output
    label = output.get("label")
    allowed_labels = output.get("allowed_labels")
    if isinstance(allowed_labels, list) and label not in allowed_labels:
        return [
            failed_check(
                "topic_label_enum",
                "topic label is not in allowed label enum",
            )
        ]
    confidence = output.get("confidence")
    if (
        not isinstance(confidence, int | float)
        or isinstance(confidence, bool)
        or not 0 <= confidence <= 1
    ):
        return [
            failed_check(
                "topic_confidence_range",
                "topic confidence must be numeric and between 0 and 1",
            )
        ]
    if confidence < 0.65:
        return [warning_check("topic_confidence", "topic confidence is low")]
    return [passed_check("topic_classification")]


def _claim_extraction(envelope: WorkUnitResultEnvelope) -> list[VerifierCheckResult]:
    output = envelope.output
    claims = output.get("claims")
    if not isinstance(claims, list) or not claims:
        return [failed_check("claim_entity", "claim extraction produced no claims")]
    failures: list[VerifierCheckResult] = []
    source_ids = _claim_source_ids(output)
    for claim in claims:
        if not isinstance(claim, dict):
            failures.append(
                failed_check("claim_entity", "claim entry is not an object")
            )
            continue
        claim_text = claim.get("claim_text") or claim.get("text")
        if not isinstance(claim_text, str) or not claim_text:
            failures.append(failed_check("claim_text", "claim is missing claim_text"))
        if not claim.get("entity"):
            failures.append(failed_check("claim_entity", "claim is missing entity"))
        claim_type = claim.get("claim_type")
        allowed_claim_types = _allowed_claim_types(output)
        if not isinstance(claim_type, str) or claim_type not in allowed_claim_types:
            failures.append(
                failed_check("claim_type_enum", "claim_type is not allowed")
            )
        confidence = claim.get("confidence")
        if (
            not isinstance(confidence, int | float)
            or isinstance(confidence, bool)
            or not 0 <= confidence <= 1
        ):
            failures.append(
                failed_check(
                    "claim_confidence_range",
                    "claim confidence must be numeric and between 0 and 1",
                )
            )
        source_refs = _claim_source_refs(claim)
        if not source_refs:
            failures.append(
                failed_check("claim_source_ref", "claim is missing source_post_refs")
            )
        elif not _source_refs_allowed(source_refs, source_ids):
            failures.append(
                failed_check(
                    "claim_source_ref",
                    "claim source_post_refs are not in input source ids",
                )
            )
        evidence_hint = claim.get("evidence_hint")
        if not isinstance(evidence_hint, str) or not evidence_hint:
            failures.append(
                failed_check("claim_evidence_hint", "claim is missing evidence_hint")
            )
    return failures or [passed_check("claim_extraction")]


def _allowed_claim_types(output: dict) -> set[str]:
    value = output.get("allowed_claim_types")
    if isinstance(value, list):
        allowed = {
            item
            for item in value
            if isinstance(item, str) and item in ALLOWED_CLAIM_TYPES
        }
        if allowed:
            return allowed
    return set(ALLOWED_CLAIM_TYPES)


def _claim_source_ids(output: dict) -> set[str]:
    value = output.get("source_ids")
    if not isinstance(value, list):
        return set()
    return {
        item
        for item in value
        if isinstance(item, str) and item
    }


def _claim_source_refs(claim: dict) -> list[str]:
    source_post_refs = claim.get("source_post_refs")
    if isinstance(source_post_refs, list):
        refs = [
            item
            for item in source_post_refs
            if isinstance(item, str) and item
        ]
        if refs:
            return refs
    source_ref = claim.get("source_ref")
    if isinstance(source_ref, str) and source_ref:
        return [source_ref]
    return []


def _source_refs_allowed(source_refs: list[str], source_ids: set[str]) -> bool:
    if source_ids:
        return all(source_ref in source_ids for source_ref in source_refs)
    return all(
        source_ref.startswith(("src_", "fixture_"))
        for source_ref in source_refs
    )


def _webpage_extraction(envelope: WorkUnitResultEnvelope) -> list[VerifierCheckResult]:
    output = envelope.output
    extracted = output.get("extracted")
    if not isinstance(extracted, dict) or not extracted:
        return [failed_check("webpage_empty", "webpage extraction output is empty")]
    if output.get("prompt_injection_detected"):
        return [
            warning_check(
                "webpage_prompt_injection",
                "prompt injection marker detected in untrusted content",
            )
        ]
    return [passed_check("webpage_extraction")]
