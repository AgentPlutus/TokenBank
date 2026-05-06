from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from tokenbank.router.route_plan_validator import (
    RoutePlanValidationError,
    RoutePlanValidator,
)
from tokenbank.router.service import RouterService

REPO_ROOT = Path(__file__).resolve().parents[2]


def _service() -> RouterService:
    return RouterService.from_dirs(
        config_dir=REPO_ROOT / "config",
        routebook_dir=REPO_ROOT / "routebook",
    )


def _validator() -> RoutePlanValidator:
    return _service().validator


def _payload(task_type: str = "url_check") -> dict[str, Any]:
    route_plan = _service().plan_route(
        {
            "work_unit_id": f"wu_{task_type}",
            "run_id": "run_validator",
            "task_type": task_type,
            "privacy_level": "private",
            "data_labels": ["public_url"],
        }
    )
    return route_plan.model_dump(mode="json")


def test_reject_unknown_backend() -> None:
    payload = _payload()
    payload["candidates"][0]["backend_id"] = "backend:missing:v0"

    with pytest.raises(RoutePlanValidationError, match="unknown backend_id"):
        _validator().validate_payload(payload)


def test_reject_missing_verifier() -> None:
    payload = _payload()
    payload["verifier_recipe_id"] = "verifier:wrong:v0"

    with pytest.raises(RoutePlanValidationError, match="does not match"):
        _validator().validate_payload(payload)


def test_reject_l1_l2_without_verifier() -> None:
    payload = _payload()
    payload["candidates"][0]["verifier_recipe_id"] = None

    with pytest.raises(RoutePlanValidationError, match="requires verifier"):
        _validator().validate_payload(payload)


def test_reject_seller_field() -> None:
    payload = _payload()
    payload["seller_mode"] = True

    with pytest.raises(RoutePlanValidationError, match="forbidden route field"):
        _validator().validate_payload(payload)


def test_reject_openai_proxy_route() -> None:
    payload = _payload()
    payload["candidates"][0]["backend_id"] = "/v1/chat/completions"

    with pytest.raises(RoutePlanValidationError, match="proxy route"):
        _validator().validate_payload(payload)


def test_reject_worker_direct_api_model_route() -> None:
    payload = _payload("topic_classification")
    payload["candidates"][0]["worker_selector"]["worker_id"] = "wrk_demo_local"
    payload["candidates"][0]["capacity_node_id"] = "capnode:worker:wrk_demo_local"

    with pytest.raises(RoutePlanValidationError, match="worker direct API model"):
        _validator().validate_payload(payload)


def test_reject_shell_command_in_route() -> None:
    payload = _payload()
    payload["candidates"][0]["shell_command"] = "curl https://example.com"

    with pytest.raises(RoutePlanValidationError, match="forbidden route field"):
        _validator().validate_payload(payload)


def test_reject_llm_generated_allowed_domain() -> None:
    payload = _payload()
    payload["allowed_domains_source"] = "llm"

    with pytest.raises(RoutePlanValidationError, match="allowed_domains"):
        _validator().validate_payload(payload)
