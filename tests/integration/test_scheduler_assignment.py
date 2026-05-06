from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from tokenbank.capacity.registry import WorkerManifest, rebuild_capacity_nodes
from tokenbank.core.canonical import canonical_json_dumps
from tokenbank.db.bootstrap import initialize_database
from tokenbank.scheduler.lease import LeaseConflictError
from tokenbank.scheduler.lifecycle import (
    scheduler_mutate_verifier_report_forbidden,
    update_work_unit_status,
    verifier_mutate_assignment_forbidden,
)
from tokenbank.scheduler.scheduler import Scheduler


def seed_work_unit(conn: sqlite3.Connection) -> None:
    now = "2026-05-04T00:00:00Z"
    conn.execute(
        """
        INSERT INTO runs (run_id, status, body_json, created_at, updated_at)
        VALUES (?, ?, ?, ?, ?)
        """,
        ("run_001", "created", "{}", now, now),
    )
    conn.execute(
        """
        INSERT INTO work_units (
          work_unit_id,
          run_id,
          status,
          task_type,
          task_level,
          body_json,
          created_at,
          updated_at
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """,
        ("wu_001", "run_001", "queued", "url_check", "L1", "{}", now, now),
    )
    conn.execute(
        """
        INSERT INTO route_plans (
          route_plan_id,
          work_unit_id,
          status,
          body_json,
          created_at
        )
        VALUES (?, ?, ?, ?, ?)
        """,
        ("rp_001", "wu_001", "validated", "{}", now),
    )
    conn.execute(
        """
        INSERT INTO policy_decisions (
          policy_decision_id,
          work_unit_id,
          route_plan_id,
          decision,
          body_json,
          created_at
        )
        VALUES (?, ?, ?, ?, ?, ?)
        """,
        ("pd_001", "wu_001", "rp_001", "approved", "{}", now),
    )
    conn.execute(
        """
        INSERT INTO worker_manifests (
          worker_id,
          manifest_hash,
          body_json,
          created_at,
          updated_at
        )
        VALUES (?, ?, ?, ?, ?)
        """,
        (
            "wrk_1",
            "worker_hash",
            canonical_json_dumps({"worker_id": "wrk_1"}),
            now,
            now,
        ),
    )
    conn.commit()


def scheduler_fixture(tmp_path: Path, *, assign: bool = True):
    conn = initialize_database(tmp_path / "tokenbank.db")
    seed_work_unit(conn)
    scheduler = Scheduler(conn)
    attempt_id = scheduler.create_attempt(
        work_unit_id="wu_001",
        route_plan_id="rp_001",
        policy_decision_id="pd_001",
    )
    assignment_id = None
    if assign:
        assignment_id = scheduler.create_assignment(
            attempt_id=attempt_id,
            worker_id="wrk_1",
            capacity_node_id="capnode:worker:wrk_1",
            backend_id="backend:url_check:v0",
        )
    return conn, scheduler, attempt_id, assignment_id


def test_assignment_own_worker_only(tmp_path: Path) -> None:
    _, scheduler, _, assignment_id = scheduler_fixture(tmp_path)

    assert scheduler.poll_next_assignment("wrk_2") is None
    with pytest.raises(PermissionError):
        scheduler.accept_assignment(
            assignment_id=assignment_id,
            worker_id="wrk_2",
        )


def test_assign_next_work_creates_concrete_assignment(tmp_path: Path) -> None:
    conn, scheduler, _, _ = scheduler_fixture(tmp_path, assign=False)
    rebuild_capacity_nodes(
        conn,
        worker_manifests=[
            WorkerManifest(
                worker_id="wrk_1",
                identity="worker 1",
                capabilities=["url_check"],
                allowed_task_types=["url_check"],
                backend_ids=["backend:url_check:v0"],
                backend_classes=["local_tool"],
            )
        ],
        backend_manifests=[],
    )

    assignment_id = scheduler.assign_next_work("wrk_1")

    row = conn.execute(
        "SELECT worker_id, backend_id FROM assignments WHERE assignment_id = ?",
        (assignment_id,),
    ).fetchone()
    assert row["worker_id"] == "wrk_1"
    assert row["backend_id"] == "backend:url_check:v0"


def test_accept_lease_conflict(tmp_path: Path) -> None:
    conn, scheduler, _, assignment_id = scheduler_fixture(tmp_path)

    with pytest.raises(LeaseConflictError):
        scheduler.accept_assignment(
            assignment_id=assignment_id,
            worker_id="wrk_1",
            expected_lease_version=1,
        )

    accepted = scheduler.accept_assignment(
        assignment_id=assignment_id,
        worker_id="wrk_1",
    )
    raw_token = accepted["lease_token"]
    row = conn.execute(
        "SELECT lease_token_hash, lease_token_prefix, body_json FROM assignments"
    ).fetchone()
    assert raw_token not in row["lease_token_hash"]
    assert raw_token not in row["lease_token_prefix"]
    assert raw_token not in row["body_json"]


def test_progress_refreshes_lease(tmp_path: Path) -> None:
    conn, scheduler, _, assignment_id = scheduler_fixture(tmp_path)
    accepted = scheduler.accept_assignment(
        assignment_id=assignment_id,
        worker_id="wrk_1",
        lease_duration_ms=1_000,
    )
    before = conn.execute(
        "SELECT lease_expires_at FROM assignments WHERE assignment_id = ?",
        (assignment_id,),
    ).fetchone()["lease_expires_at"]

    progressed = scheduler.progress_assignment(
        assignment_id=assignment_id,
        worker_id="wrk_1",
        lease_token=accepted["lease_token"],
        expected_lease_version=accepted["lease_version"],
        lease_duration_ms=60_000,
    )

    after = conn.execute(
        """
        SELECT lease_expires_at, lease_version
        FROM assignments
        WHERE assignment_id = ?
        """,
        (assignment_id,),
    ).fetchone()
    assert progressed["lease_version"] == 2
    assert after["lease_version"] == 2
    assert after["lease_expires_at"] > before


def test_heartbeat_not_lease_refresh(tmp_path: Path) -> None:
    conn, scheduler, _, assignment_id = scheduler_fixture(tmp_path)
    scheduler.accept_assignment(assignment_id=assignment_id, worker_id="wrk_1")
    before = conn.execute(
        "SELECT lease_expires_at FROM assignments WHERE assignment_id = ?",
        (assignment_id,),
    ).fetchone()["lease_expires_at"]

    scheduler.record_worker_heartbeat("wrk_1")

    after = conn.execute(
        "SELECT lease_expires_at FROM assignments WHERE assignment_id = ?",
        (assignment_id,),
    ).fetchone()["lease_expires_at"]
    assert after == before


def test_retry_new_attempt_id(tmp_path: Path) -> None:
    conn, scheduler, attempt_id, _ = scheduler_fixture(tmp_path)

    retry_attempt_id = scheduler.schedule_retry(attempt_id)

    assert retry_attempt_id != attempt_id
    numbers = [
        row["attempt_number"]
        for row in conn.execute(
            "SELECT attempt_number FROM execution_attempts ORDER BY attempt_number"
        ).fetchall()
    ]
    assert numbers == [1, 2]


def test_fallback_new_attempt_id(tmp_path: Path) -> None:
    conn, scheduler, attempt_id, _ = scheduler_fixture(tmp_path)

    fallback_attempt_id = scheduler.schedule_fallback(attempt_id)

    assert fallback_attempt_id != attempt_id
    row = conn.execute(
        "SELECT status, attempt_number FROM execution_attempts WHERE attempt_id = ?",
        (fallback_attempt_id,),
    ).fetchone()
    assert row["status"] == "scheduled"
    assert row["attempt_number"] == 2


def test_transition_has_event_outbox_record(tmp_path: Path) -> None:
    conn, scheduler, _, assignment_id = scheduler_fixture(tmp_path)
    accepted = scheduler.accept_assignment(
        assignment_id=assignment_id,
        worker_id="wrk_1",
    )
    scheduler.progress_assignment(
        assignment_id=assignment_id,
        worker_id="wrk_1",
        lease_token=accepted["lease_token"],
        expected_lease_version=accepted["lease_version"],
    )

    event_types = {
        row["type"]
        for row in conn.execute("SELECT type FROM event_outbox").fetchall()
    }
    assert {
        "attempt.created",
        "assignment.created",
        "assignment.accepted",
        "assignment.progress",
        "work_unit.assigned",
        "work_unit.running",
    }.issubset(event_types)


def test_worker_cannot_update_work_unit(tmp_path: Path) -> None:
    conn, _, _, _ = scheduler_fixture(tmp_path)

    with pytest.raises(PermissionError):
        update_work_unit_status(
            conn,
            work_unit_id="wu_001",
            status="succeeded",
            actor="worker",
        )


def test_verifier_cannot_mutate_assignment() -> None:
    with pytest.raises(PermissionError):
        verifier_mutate_assignment_forbidden()


def test_scheduler_cannot_modify_verifier_report() -> None:
    with pytest.raises(PermissionError):
        scheduler_mutate_verifier_report_forbidden()
