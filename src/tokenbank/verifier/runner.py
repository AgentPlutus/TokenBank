"""VerifierRunner for deterministic P0 recipes."""

from __future__ import annotations

from typing import Any

from tokenbank.models.common import VerifierCheckResult
from tokenbank.models.result_envelope import WorkUnitResultEnvelope
from tokenbank.models.verifier import VerifierReport
from tokenbank.verifier.checks.common import (
    check_envelope_integrity,
    check_hashes,
    check_output_schema,
    check_policy_linkage,
    check_secret_redaction,
)
from tokenbank.verifier.checks.task_specific import run_task_specific_checks
from tokenbank.verifier.recipes import VerifierRecipe, load_verifier_recipe
from tokenbank.verifier.report_builder import build_verifier_report

BLOCKING_SAFETY_CHECKS = {"secret_redaction"}
HASH_CHECKS = {"output_hash_present", "output_hash_valid", "result_hash_valid"}
SCHEMA_CHECKS = {"output_schema"}
POLICY_CHECKS = {"policy_linkage"}


class VerifierRunner:
    """Run deterministic recipe checks and return VerifierReport only."""

    def __init__(self, recipe: VerifierRecipe):
        self.recipe = recipe

    @classmethod
    def for_recipe_id(cls, recipe_id: str) -> VerifierRunner:
        return cls(load_verifier_recipe(recipe_id))

    def run(
        self,
        *,
        result_envelope: WorkUnitResultEnvelope,
        work_unit: dict[str, Any] | None = None,
        policy_decision: dict[str, Any] | None = None,
    ) -> VerifierReport:
        common_checks: list[VerifierCheckResult] = []
        common_checks.extend(check_envelope_integrity(result_envelope))
        common_checks.extend(check_hashes(result_envelope))
        common_checks.extend(
            check_policy_linkage(
                envelope=result_envelope,
                policy_decision=policy_decision,
            )
        )
        common_checks.extend(check_secret_redaction(result_envelope))
        common_checks.extend(
            check_output_schema(
                envelope=result_envelope,
                recipe=self.recipe,
                work_unit=work_unit,
            )
        )
        deterministic_checks = run_task_specific_checks(
            recipe_id=self.recipe.verifier_recipe_id,
            envelope=result_envelope,
        )
        checks = [*common_checks, *deterministic_checks]
        recommendation = self._recommendation(checks)
        metadata = self._metadata(
            checks=checks,
            deterministic_checks=deterministic_checks,
            recommendation=recommendation,
        )
        return build_verifier_report(
            recipe_id=self.recipe.verifier_recipe_id,
            envelope=result_envelope,
            checks=checks,
            recommendation=recommendation,
            metadata=metadata,
        )

    def _recommendation(self, checks: list[VerifierCheckResult]) -> str:
        failed_names = {
            check.name
            for check in checks
            if check.status == "failed"
        }
        warning_names = {
            check.name
            for check in checks
            if check.status == "needs_review"
        }

        if "secret_redaction" in failed_names:
            return self.recipe.recommendation("secret_detected", "quarantine")
        if "output_hash_present" in failed_names:
            return self.recipe.recommendation("output_hash_missing", "reject")
        if failed_names.intersection({"output_hash_valid", "result_hash_valid"}):
            return self.recipe.recommendation("hash_mismatch", "quarantine")
        if "output_schema" in failed_names:
            return self.recipe.recommendation("schema_invalid", "retry")
        if "policy_linkage" in failed_names:
            return "quarantine"

        task_recommendation = self._task_recommendation(failed_names, warning_names)
        if task_recommendation is not None:
            return task_recommendation
        return "accept"

    def _task_recommendation(
        self,
        failed_names: set[str],
        warning_names: set[str],
    ) -> str | None:
        if "url_policy_safety" in failed_names:
            return self.recipe.recommendation("private_ip_or_redirect", "quarantine")
        if "url_timeout" in failed_names:
            return self.recipe.recommendation("timeout", "retry")
        if "url_status" in warning_names:
            return self.recipe.recommendation("http_4xx", "accept_with_warning")
        if "url_status" in failed_names:
            return self.recipe.recommendation("default_failure", "reject")
        if "dedup_overmerge" in warning_names:
            return self.recipe.recommendation("overmerge", "accept_with_warning")
        if "dedup_exact" in failed_names:
            return self.recipe.recommendation("default_failure", "reject")
        if "topic_label_enum" in failed_names:
            return self.recipe.recommendation("label_not_enum", "retry")
        if "topic_confidence_range" in failed_names:
            return self.recipe.recommendation("schema_invalid", "retry")
        if "topic_confidence" in warning_names:
            return self.recipe.recommendation("low_confidence", "accept_with_warning")
        if "claim_source_ref" in failed_names:
            return self.recipe.recommendation("missing_source_ref", "fallback")
        if "claim_entity" in failed_names:
            return self.recipe.recommendation("missing_entity", "retry")
        if failed_names.intersection(
            {
                "claim_text",
                "claim_type_enum",
                "claim_confidence_range",
                "claim_evidence_hint",
            }
        ):
            return self.recipe.recommendation("schema_invalid", "retry")
        if "webpage_empty" in failed_names:
            return self.recipe.recommendation("empty", "fallback")
        if "webpage_prompt_injection" in warning_names:
            return self.recipe.recommendation(
                "prompt_injection",
                "accept_with_warning",
            )
        return None

    def _metadata(
        self,
        *,
        checks: list[VerifierCheckResult],
        deterministic_checks: list[VerifierCheckResult],
        recommendation: str,
    ) -> dict[str, Any]:
        blocking_failures = [
            check.name
            for check in checks
            if check.status == "failed"
        ]
        warning_failures = [
            check.name
            for check in checks
            if check.status == "needs_review"
        ]
        return {
            "safety_status": _status_for_group(checks, BLOCKING_SAFETY_CHECKS),
            "schema_status": _status_for_group(checks, SCHEMA_CHECKS),
            "policy_status": _status_for_group(checks, POLICY_CHECKS),
            "deterministic_status": _aggregate_status(deterministic_checks),
            "blocking_failures": blocking_failures,
            "warning_failures": warning_failures,
            "sampled_audit_required": False,
            "sampled_audit_rate_bps": self.recipe.sampled_audit_rate_bps,
            "llm_judge_used": False,
            "quarantine_auto_fallback": False,
            "recommendation": recommendation,
        }


def _status_for_group(
    checks: list[VerifierCheckResult],
    names: set[str],
) -> str:
    relevant = [
        check
        for check in checks
        if check.name in names
    ]
    return _aggregate_status(relevant)


def _aggregate_status(checks: list[VerifierCheckResult]) -> str:
    if not checks:
        return "skipped"
    if any(check.status == "failed" for check in checks):
        return "failed"
    if any(check.status == "needs_review" for check in checks):
        return "needs_review"
    if all(check.status == "skipped" for check in checks):
        return "skipped"
    return "passed"
