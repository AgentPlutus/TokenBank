"""Internal verifier endpoint skeleton."""

from __future__ import annotations

from fastapi import APIRouter, Depends

from tokenbank.app.deps import require_internal_token
from tokenbank.app.routers.common import not_implemented

router = APIRouter(tags=["internal"], dependencies=[Depends(require_internal_token)])


@router.post("/internal/verifier/run")
def verifier_run() -> dict[str, str]:
    return not_implemented("internal.verifier.run")

