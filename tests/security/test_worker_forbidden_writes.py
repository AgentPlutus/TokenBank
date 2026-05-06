from __future__ import annotations

from pathlib import Path

import pytest

from tests.integration.test_scheduler_assignment import scheduler_fixture
from tokenbank.scheduler.lifecycle import (
    scheduler_mutate_verifier_report_forbidden,
    update_work_unit_status,
    verifier_mutate_assignment_forbidden,
)
from tokenbank.worker.executor import LocalToolExecutor
from tokenbank.worker.logs import redact_worker_log
from tokenbank.worker.sandbox import WorkerSandbox

REPO_ROOT = Path(__file__).resolve().parents[2]


def worker_sources() -> str:
    return "\n".join(
        path.read_text(encoding="utf-8")
        for path in sorted((REPO_ROOT / "src/tokenbank/worker").glob("*.py"))
    )


def test_worker_cannot_update_work_unit(tmp_path: Path) -> None:
    conn, _, _, _ = scheduler_fixture(tmp_path)

    with pytest.raises(PermissionError):
        update_work_unit_status(
            conn,
            work_unit_id="wu_001",
            status="succeeded",
            actor="worker",
        )


def test_worker_forbidden_write_surfaces_are_not_imported() -> None:
    source = worker_sources()

    assert "tokenbank.db" not in source
    assert "sqlite3" not in source
    assert "work_units" not in source
    assert "verifier_reports" not in source
    assert "policy_decisions" not in source


def test_worker_does_not_call_api_model_provider(tmp_path: Path) -> None:
    sandbox = WorkerSandbox(tmp_path / "sandbox", "wrk_1").create_assignment("asg_1")

    with pytest.raises(PermissionError):
        LocalToolExecutor().execute(
            assignment={
                "assignment_id": "asg_1",
                "backend_id": "backend:api_model_gateway:l1_structured",
            },
            sandbox=sandbox,
        )


def test_worker_redacts_logs() -> None:
    redacted = redact_worker_log(
        "Authorization: Bearer tbk_w_secret worker_token: tbk_w_secret "
        "lease=tbk_l_secret api_key=sk-secret"
    )

    assert "tbk_w_secret" not in redacted
    assert "tbk_l_secret" not in redacted
    assert "sk-secret" not in redacted
    assert "[REDACTED" in redacted


def test_worker_cannot_write_verifier_or_policy_state() -> None:
    with pytest.raises(PermissionError):
        verifier_mutate_assignment_forbidden()
    with pytest.raises(PermissionError):
        scheduler_mutate_verifier_report_forbidden()
