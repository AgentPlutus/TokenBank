"""Internal policy and report endpoint skeletons."""

from __future__ import annotations

from fastapi import APIRouter, Depends

from tokenbank.app.deps import require_internal_token
from tokenbank.app.routers.common import not_implemented

router = APIRouter(tags=["internal"], dependencies=[Depends(require_internal_token)])


@router.post("/internal/policy/evaluate")
def policy_evaluate() -> dict[str, str]:
    return not_implemented("internal.policy.evaluate")


@router.post("/internal/model-gateway/execute")
def model_gateway_execute() -> dict[str, str]:
    return not_implemented("internal.model_gateway.execute")


@router.post("/internal/reports/generate")
def reports_generate() -> dict[str, str]:
    return not_implemented("internal.reports.generate")

