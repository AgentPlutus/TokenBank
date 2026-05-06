"""Deterministic Phase 0 policy checks."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from tokenbank.core.canonical import canonical_json_hash
from tokenbank.models.policy_decision import PolicyDecision
from tokenbank.policy.bundle import PolicyBundle
from tokenbank.policy.extensions import lint_extension_keys

CONTROL_PLANE_GATEWAY_WORKER_ID = "wrk_control_plane_gateway"


@dataclass(frozen=True)
class PolicyCheck:
    name: str
    passed: bool
    reason: str

    def as_dict(self) -> dict[str, object]:
        return {"name": self.name, "passed": self.passed, "reason": self.reason}


def _value_at(payload: dict[str, Any], *keys: str) -> Any:
    for key in keys:
        if key in payload:
            return payload[key]
    return None


def _contains_bad_micros(value: Any) -> bool:
    if isinstance(value, dict):
        for key, nested in value.items():
            if str(key).endswith("_micros") and not (
                isinstance(nested, int) and not isinstance(nested, bool)
            ):
                return True
            if _contains_bad_micros(nested):
                return True
    elif isinstance(value, list):
        return any(_contains_bad_micros(item) for item in value)
    return False


def _check(name: str, passed: bool, reason: str) -> PolicyCheck:
    return PolicyCheck(name=name, passed=passed, reason=reason)


def evaluate_policy(
    *,
    work_unit: dict[str, Any],
    route_plan: dict[str, Any],
    worker_manifest: dict[str, Any],
    backend_manifest: dict[str, Any],
    policy_bundle: PolicyBundle,
) -> PolicyDecision:
    """Evaluate deterministic WP3 policy fixtures and return a PolicyDecision."""
    checks: list[PolicyCheck] = []
    backend_id = str(
        _value_at(route_plan, "backend_id") or backend_manifest.get("backend_id")
    )
    backend_class = str(
        _value_at(route_plan, "backend_class") or backend_manifest.get("backend_class")
    )
    worker_id = str(worker_manifest.get("worker_id", ""))
    task_level = str(work_unit.get("task_level", ""))
    verifier_recipe_id = _value_at(route_plan, "verifier_recipe_id")

    checks.append(
        _check(
            "default_deny_inputs_present",
            bool(work_unit and route_plan and backend_manifest),
            "work unit, route plan, and backend manifest are required",
        )
    )
    checks.append(
        _check(
            "needs_review_denied",
            not bool(work_unit.get("needs_review") or route_plan.get("needs_review")),
            "needs_review is denied in Phase 0",
        )
    )
    checks.append(
        _check(
            "backend_allowlist",
            backend_id in policy_bundle.allowed_backend_ids,
            f"backend_id {backend_id} must be allowed",
        )
    )
    checks.append(
        _check(
            "backend_class_allowlist",
            backend_class in policy_bundle.allowed_backend_classes,
            f"backend_class {backend_class} must be allowed",
        )
    )
    checks.append(
        _check(
            "forbidden_backend_class",
            backend_class not in policy_bundle.forbidden_backend_classes,
            f"backend_class {backend_class} must not be forbidden",
        )
    )
    direct_api_worker = backend_class in {
        "api_model_gateway",
        "primary_model_gateway",
    } and worker_id != CONTROL_PLANE_GATEWAY_WORKER_ID
    checks.append(
        _check(
            "worker_direct_api_model_denied",
            not direct_api_worker,
            "API model gateway execution must stay on the control plane gateway",
        )
    )
    checks.append(
        _check(
            "l1_l2_verifier_required",
            task_level not in {"L1", "L2"} or bool(verifier_recipe_id),
            "L1/L2 routes require verifier_recipe_id",
        )
    )

    extension_issues = [
        *lint_extension_keys(work_unit.get("extensions", {}), "$.work_unit.extensions"),
        *lint_extension_keys(
            route_plan.get("extensions", {}),
            "$.route_plan.extensions",
        ),
        *lint_extension_keys(
            backend_manifest.get("extensions", {}),
            "$.backend_manifest.extensions",
        ),
    ]
    checks.append(
        _check(
            "forbidden_extension_keys",
            not extension_issues,
            "seller/marketplace/payment/payout/settlement/yield-like keys are denied",
        )
    )
    checks.append(
        _check(
            "micros_fields_integer",
            not _contains_bad_micros([work_unit, route_plan, backend_manifest]),
            "cost/currency fields ending in _micros must be integers",
        )
    )

    passed = all(check.passed for check in checks)
    decision = "approved" if passed else "denied"
    reasons = [check.reason for check in checks if not check.passed]
    if not reasons:
        reasons = ["all deterministic WP3 policy checks passed"]

    work_unit_id = str(work_unit.get("work_unit_id", "unknown_work_unit"))
    route_plan_id = str(route_plan.get("route_plan_id", "unknown_route_plan"))
    return PolicyDecision(
        policy_decision_id=(
            "pd_"
            + canonical_json_hash(
                {
                    "work_unit_id": work_unit_id,
                    "route_plan_id": route_plan_id,
                    "checks": [check.as_dict() for check in checks],
                }
            )[:24]
        ),
        work_unit_id=work_unit_id,
        route_plan_id=route_plan_id,
        decision=decision,
        reasons=reasons,
        checks=[check.as_dict() for check in checks],
        effective_constraints={
            "allowed_backend_ids": sorted(policy_bundle.allowed_backend_ids),
            "allowed_backend_classes": sorted(policy_bundle.allowed_backend_classes),
        },
    )
