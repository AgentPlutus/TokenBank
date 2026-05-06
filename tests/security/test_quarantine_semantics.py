from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from tokenbank.backends.adapter import BackendExecutionContext, build_result_envelope
from tokenbank.backends.usage import make_usage_record
from tokenbank.db.bootstrap import initialize_database
from tokenbank.models.result_envelope import WorkUnitResultEnvelope
from tokenbank.scheduler.lifecycle import verifier_mutate_assignment_forbidden
from tokenbank.verifier.runner import VerifierRunner


def envelope_for(*, task_type: str, output: dict[str, Any]) -> WorkUnitResultEnvelope:
    context = BackendExecutionContext(
        work_unit_id=f"wu_{task_type}",
        run_id="run_quarantine",
        attempt_id="att_quarantine",
        assignment_id="asg_quarantine",
        backend_id="backend:test:v0",
        backend_class="local_tool",
        task_type=task_type,
        input_payload={},
    )
    usage = [
        make_usage_record(
            work_unit_id=context.work_unit_id,
            attempt_id=context.attempt_id,
            backend_id=context.backend_id,
            cost_source="zero_internal_phase0",
            cost_confidence="high",
        )
    ]
    return build_result_envelope(
        context=context,
        output=output,
        usage_records=usage,
        started_at=datetime.now(UTC),
    )


def test_verifier_cannot_mutate_assignment() -> None:
    try:
        verifier_mutate_assignment_forbidden()
    except PermissionError as exc:
        assert "cannot mutate Assignment" in str(exc)
    else:
        raise AssertionError("verifier assignment mutation should be forbidden")


def test_verifier_does_not_create_retry_attempt(tmp_path: Path) -> None:
    conn = initialize_database(tmp_path / "tokenbank.db")
    before = conn.execute("SELECT COUNT(*) FROM execution_attempts").fetchone()[0]
    envelope = envelope_for(
        task_type="url_check",
        output={"ok": False, "timed_out": True},
    )

    report = VerifierRunner.for_recipe_id("url_check_v0").run(
        result_envelope=envelope
    )
    after = conn.execute("SELECT COUNT(*) FROM execution_attempts").fetchone()[0]

    assert report.recommendation == "retry"
    assert after == before


def test_quarantine_does_not_auto_fallback() -> None:
    envelope = envelope_for(
        task_type="url_check",
        output={"ok": False, "private_ip_denied": True},
    )

    report = VerifierRunner.for_recipe_id("url_check_v0").run(
        result_envelope=envelope
    )

    assert report.recommendation == "quarantine"
    assert report.metadata["quarantine_auto_fallback"] is False


def test_accept_with_warning_not_strict_accept() -> None:
    envelope = envelope_for(
        task_type="url_check",
        output={"ok": False, "status_code": 404},
    )

    report = VerifierRunner.for_recipe_id("url_check_v0").run(
        result_envelope=envelope
    )

    assert report.recommendation == "accept_with_warning"
    assert report.recommendation != "accept"
    assert report.status == "needs_review"
