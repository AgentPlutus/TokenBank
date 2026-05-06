from __future__ import annotations

from pathlib import Path

import pytest

from tokenbank.policy.bundle import load_policy_bundle
from tokenbank.policy.checks import evaluate_policy

REPO_ROOT = Path(__file__).resolve().parents[2]


def _bundle():
    return load_policy_bundle(REPO_ROOT / "config")


def _work_unit(**overrides):
    payload = {
        "work_unit_id": "wu_001",
        "task_type": "url_check",
        "task_level": "L1",
        "privacy_level": "private",
        "max_cost_micros": 0,
    }
    payload.update(overrides)
    return payload


def _route_plan(**overrides):
    payload = {
        "route_plan_id": "rp_001",
        "backend_id": "backend:url_check:v0",
        "backend_class": "local_tool",
        "verifier_recipe_id": "url_check_v0",
        "estimated_cost_micros": 0,
    }
    payload.update(overrides)
    return payload


def _worker_manifest(**overrides):
    payload = {
        "worker_id": "wrk_demo_local",
        "backend_ids": ["backend:url_check:v0"],
    }
    payload.update(overrides)
    return payload


def _backend_manifest(**overrides):
    payload = {
        "backend_id": "backend:url_check:v0",
        "backend_class": "local_tool",
        "supported_task_types": ["url_check"],
    }
    payload.update(overrides)
    return payload


def _decision(
    *,
    work_unit=None,
    route_plan=None,
    worker_manifest=None,
    backend_manifest=None,
):
    return evaluate_policy(
        work_unit=_work_unit() if work_unit is None else work_unit,
        route_plan=_route_plan() if route_plan is None else route_plan,
        worker_manifest=(
            _worker_manifest() if worker_manifest is None else worker_manifest
        ),
        backend_manifest=(
            _backend_manifest() if backend_manifest is None else backend_manifest
        ),
        policy_bundle=_bundle(),
    )


def test_policy_approves_allowed_private_capacity_fixture() -> None:
    decision = _decision()

    assert decision.decision == "approved"
    assert decision.reasons == ["all deterministic WP3 policy checks passed"]
    assert all(check["passed"] for check in decision.checks)


def test_default_deny_when_required_inputs_missing() -> None:
    decision = _decision(work_unit={})

    assert decision.decision == "denied"
    assert any(
        check["name"] == "default_deny_inputs_present"
        for check in decision.checks
    )


def test_needs_review_is_denied_in_phase0() -> None:
    decision = _decision(work_unit=_work_unit(needs_review=True))

    assert decision.decision == "denied"
    assert "needs_review is denied in Phase 0" in decision.reasons


def test_worker_direct_api_model_is_denied() -> None:
    decision = _decision(
        work_unit=_work_unit(task_type="structured_summary", task_level="L2"),
        route_plan=_route_plan(
            backend_id="backend:api_model_gateway:l1_structured",
            backend_class="api_model_gateway",
            verifier_recipe_id="structured_summary_v0",
        ),
        backend_manifest=_backend_manifest(
            backend_id="backend:api_model_gateway:l1_structured",
            backend_class="api_model_gateway",
        ),
        worker_manifest=_worker_manifest(worker_id="wrk_win_01"),
    )

    assert decision.decision == "denied"
    assert "API model gateway execution must stay on the control plane gateway" in (
        decision.reasons
    )


@pytest.mark.parametrize(
    "backend_class",
    ["account_pool", "oauth_proxy", "credential_broker", "external_seller"],
)
def test_forbidden_backend_classes_are_denied(backend_class: str) -> None:
    decision = _decision(
        route_plan=_route_plan(backend_class=backend_class),
        backend_manifest=_backend_manifest(backend_class=backend_class),
    )

    assert decision.decision == "denied"
    assert any("backend_class" in reason for reason in decision.reasons)


def test_forbidden_extension_keys_are_denied() -> None:
    decision = _decision(
        work_unit=_work_unit(extensions={"marketplace_listing": {"enabled": True}})
    )

    assert decision.decision == "denied"
    assert any("yield-like keys are denied" in reason for reason in decision.reasons)


def test_cost_fields_must_use_integer_micros() -> None:
    decision = _decision(route_plan=_route_plan(estimated_cost_micros=1.5))

    assert decision.decision == "denied"
    assert "cost/currency fields ending in _micros must be integers" in decision.reasons


def test_l1_l2_requires_verifier_recipe_id() -> None:
    decision = _decision(route_plan=_route_plan(verifier_recipe_id=None))

    assert decision.decision == "denied"
    assert "L1/L2 routes require verifier_recipe_id" in decision.reasons
