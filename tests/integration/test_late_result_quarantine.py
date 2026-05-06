from __future__ import annotations

from pathlib import Path

from tests.integration.test_scheduler_assignment import scheduler_fixture


def test_late_result_quarantine(tmp_path: Path) -> None:
    conn, scheduler, attempt_id, assignment_id = scheduler_fixture(tmp_path)
    accepted = scheduler.accept_assignment(
        assignment_id=assignment_id,
        worker_id="wrk_1",
    )
    newer_attempt_id = scheduler.schedule_retry(attempt_id)

    result = scheduler.submit_result(
        assignment_id=assignment_id,
        worker_id="wrk_1",
        lease_token=accepted["lease_token"],
        output={"reachable": True},
    )

    assert newer_attempt_id != attempt_id
    assert result["status"] == "quarantined"
    result_row = conn.execute(
        "SELECT status FROM result_envelopes WHERE result_envelope_id = ?",
        (result["result_envelope_id"],),
    ).fetchone()
    assert result_row["status"] == "quarantined"
    assert conn.execute("SELECT COUNT(*) FROM result_quarantine").fetchone()[0] == 1
    assignment = conn.execute(
        "SELECT status FROM assignments WHERE assignment_id = ?",
        (assignment_id,),
    ).fetchone()
    assert assignment["status"] == "quarantined"
    events = {
        row["type"]
        for row in conn.execute("SELECT type FROM event_outbox").fetchall()
    }
    assert "result.quarantined" in events
