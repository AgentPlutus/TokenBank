"""Scheduler and assignment state transitions."""

from __future__ import annotations

import sqlite3
import uuid
from typing import Any

from tokenbank.core.canonical import canonical_json_dumps, output_hash, result_hash
from tokenbank.db.transactions import transaction
from tokenbank.events.outbox import OutboxEventInput, enqueue_event
from tokenbank.models.result_envelope import WorkUnitResultEnvelope
from tokenbank.scheduler.lease import (
    LeaseConflictError,
    conditional_assignment_update,
    lease_expiry,
    lease_token_hash,
    lease_token_prefix,
    new_lease_token,
    utc_text,
    verify_lease_token,
    verify_lease_token_hash,
)
from tokenbank.scheduler.lifecycle import update_work_unit_status
from tokenbank.scheduler.retry_fallback import next_attempt_number

DEFAULT_LEASE_DURATION_MS = 30_000


class Scheduler:
    """Minimal WP5 scheduler state machine."""

    def __init__(self, conn: sqlite3.Connection):
        self.conn = conn

    def create_attempt(
        self,
        *,
        work_unit_id: str,
        route_plan_id: str,
        policy_decision_id: str,
        status: str = "created",
        event_type: str = "attempt.created",
    ) -> str:
        attempt_id = f"att_{uuid.uuid4().hex}"
        attempt_number = next_attempt_number(self.conn, work_unit_id)
        now = utc_text()
        body = {
            "attempt_id": attempt_id,
            "work_unit_id": work_unit_id,
            "route_plan_id": route_plan_id,
            "policy_decision_id": policy_decision_id,
            "attempt_number": attempt_number,
            "status": status,
            "created_at": now,
        }
        with transaction(self.conn):
            self.conn.execute(
                """
                INSERT INTO execution_attempts (
                  attempt_id,
                  work_unit_id,
                  route_plan_id,
                  policy_decision_id,
                  status,
                  body_json,
                  created_at,
                  attempt_number
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    attempt_id,
                    work_unit_id,
                    route_plan_id,
                    policy_decision_id,
                    status,
                    canonical_json_dumps(body),
                    now,
                    attempt_number,
                ),
            )
            enqueue_event(
                self.conn,
                OutboxEventInput(
                    source="tokenbank.scheduler",
                    type=event_type,
                    subject=f"attempts/{attempt_id}",
                    work_unit_id=work_unit_id,
                    attempt_id=attempt_id,
                    body=body,
                ),
            )
        return attempt_id

    def create_assignment(
        self,
        *,
        attempt_id: str,
        worker_id: str,
        capacity_node_id: str,
        backend_id: str,
        backend_class: str | None = None,
        effective_constraints: dict[str, Any] | None = None,
    ) -> str:
        attempt = self._attempt(attempt_id)
        assignment_id = f"asg_{uuid.uuid4().hex}"
        now = utc_text()
        constraints = effective_constraints or {}
        body = {
            "assignment_id": assignment_id,
            "attempt_id": attempt_id,
            "work_unit_id": attempt["work_unit_id"],
            "worker_id": worker_id,
            "capacity_node_id": capacity_node_id,
            "backend_id": backend_id,
            "backend_class": backend_class,
            "status": "created",
            "lease_version": 0,
            "effective_constraints": constraints,
            "assigned_at": now,
        }
        with transaction(self.conn):
            self.conn.execute(
                """
                INSERT INTO assignments (
                  assignment_id,
                  attempt_id,
                  work_unit_id,
                  worker_id,
                  status,
                  body_json,
                  created_at,
                  capacity_node_id,
                  backend_id,
                  effective_constraints_json,
                  assigned_at,
                  updated_at
                )
                VALUES (?, ?, ?, ?, 'created', ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    assignment_id,
                    attempt_id,
                    attempt["work_unit_id"],
                    worker_id,
                    canonical_json_dumps(body),
                    now,
                    capacity_node_id,
                    backend_id,
                    canonical_json_dumps(constraints),
                    now,
                    now,
                ),
            )
            self.conn.execute(
                """
                UPDATE execution_attempts
                SET status = 'assigned'
                WHERE attempt_id = ?
                """,
                (attempt_id,),
            )
            update_work_unit_status(
                self.conn,
                work_unit_id=attempt["work_unit_id"],
                status="assigned",
                actor="scheduler",
                event_type="work_unit.assigned",
            )
            enqueue_event(
                self.conn,
                OutboxEventInput(
                    source="tokenbank.scheduler",
                    type="assignment.created",
                    subject=f"assignments/{assignment_id}",
                    work_unit_id=attempt["work_unit_id"],
                    attempt_id=attempt_id,
                    assignment_id=assignment_id,
                    body=body,
                ),
            )
        return assignment_id

    def assign_next_work(self, worker_id: str) -> str | None:
        row = self.conn.execute(
            """
            SELECT capacity_node_id, backend_ids_json
            FROM capacity_nodes
            WHERE worker_id = ?
            ORDER BY capacity_node_id
            LIMIT 1
            """,
            (worker_id,),
        ).fetchone()
        if row is None:
            return None
        attempt = self.conn.execute(
            """
            SELECT attempt_id
            FROM execution_attempts
            WHERE status IN ('created', 'scheduled')
            ORDER BY created_at, attempt_number
            LIMIT 1
            """
        ).fetchone()
        if attempt is None:
            return None
        import json

        backend_ids = json.loads(row["backend_ids_json"])
        if not backend_ids:
            return None
        return self.create_assignment(
            attempt_id=attempt["attempt_id"],
            worker_id=worker_id,
            capacity_node_id=row["capacity_node_id"],
            backend_id=backend_ids[0],
        )

    def poll_next_assignment(self, worker_id: str) -> dict[str, Any] | None:
        row = self.conn.execute(
            """
            SELECT *
            FROM assignments
            WHERE worker_id = ?
              AND status = 'created'
            ORDER BY assigned_at, created_at
            LIMIT 1
            """,
            (worker_id,),
        ).fetchone()
        if row is None:
            return None
        assignment = dict(row)
        assignment["body"] = _decode_json_object(assignment.get("body_json"))
        assignment["effective_constraints"] = _decode_json_object(
            assignment.get("effective_constraints_json")
        )
        body = assignment["body"]
        if "backend_class" not in assignment and isinstance(body, dict):
            assignment["backend_class"] = body.get("backend_class")
        return assignment

    def accept_assignment(
        self,
        *,
        assignment_id: str,
        worker_id: str,
        expected_lease_version: int = 0,
        lease_duration_ms: int = DEFAULT_LEASE_DURATION_MS,
    ) -> dict[str, Any]:
        assignment = self._assignment_for_worker(assignment_id, worker_id)
        if assignment["status"] != "created":
            raise LeaseConflictError("assignment is not in created status")
        raw_token = new_lease_token()
        token_hash = lease_token_hash(raw_token)
        expires_at = lease_expiry(lease_duration_ms)
        now = utc_text()
        with transaction(self.conn):
            updated = conditional_assignment_update(
                self.conn,
                assignment_id=assignment_id,
                expected_lease_version=expected_lease_version,
                status="accepted",
                lease_expires_at=expires_at,
                lease_token_hash_value=token_hash,
                lease_token_prefix_value=lease_token_prefix(raw_token),
                accepted_at=now,
            )
            self.conn.execute(
                """
                UPDATE execution_attempts
                SET status = 'running',
                    started_at = COALESCE(started_at, ?)
                WHERE attempt_id = ?
                """,
                (now, assignment["attempt_id"]),
            )
            update_work_unit_status(
                self.conn,
                work_unit_id=assignment["work_unit_id"],
                status="running",
                actor="scheduler",
                event_type="work_unit.running",
            )
            enqueue_event(
                self.conn,
                OutboxEventInput(
                    source="tokenbank.scheduler",
                    type="assignment.accepted",
                    subject=f"assignments/{assignment_id}",
                    work_unit_id=assignment["work_unit_id"],
                    attempt_id=assignment["attempt_id"],
                    assignment_id=assignment_id,
                    body={
                        "assignment_id": assignment_id,
                        "worker_id": worker_id,
                        "lease_version": updated["lease_version"],
                        "lease_token_prefix": lease_token_prefix(raw_token),
                    },
                ),
            )
        return {
            "assignment_id": assignment_id,
            "lease_token": raw_token,
            "lease_version": updated["lease_version"],
            "lease_expires_at": expires_at,
        }

    def reject_assignment(
        self,
        *,
        assignment_id: str,
        worker_id: str,
    ) -> dict[str, Any]:
        assignment = self._assignment_for_worker(assignment_id, worker_id)
        now = utc_text()
        with transaction(self.conn):
            self.conn.execute(
                """
                UPDATE assignments
                SET status = 'rejected',
                    updated_at = ?
                WHERE assignment_id = ?
                """,
                (now, assignment_id),
            )
            self.conn.execute(
                """
                UPDATE execution_attempts
                SET status = 'failed',
                    completed_at = ?
                WHERE attempt_id = ?
                """,
                (now, assignment["attempt_id"]),
            )
            enqueue_event(
                self.conn,
                OutboxEventInput(
                    source="tokenbank.scheduler",
                    type="assignment.rejected",
                    subject=f"assignments/{assignment_id}",
                    work_unit_id=assignment["work_unit_id"],
                    attempt_id=assignment["attempt_id"],
                    assignment_id=assignment_id,
                    body={"assignment_id": assignment_id, "worker_id": worker_id},
                ),
            )
        return {"assignment_id": assignment_id, "status": "rejected"}

    def progress_assignment(
        self,
        *,
        assignment_id: str,
        worker_id: str,
        lease_token: str,
        expected_lease_version: int,
        lease_duration_ms: int = DEFAULT_LEASE_DURATION_MS,
    ) -> dict[str, Any]:
        assignment = self._assignment_for_worker(assignment_id, worker_id)
        verify_lease_token(assignment["lease_token_hash"], lease_token)
        expires_at = lease_expiry(lease_duration_ms)
        with transaction(self.conn):
            updated = conditional_assignment_update(
                self.conn,
                assignment_id=assignment_id,
                expected_lease_version=expected_lease_version,
                status="running",
                lease_expires_at=expires_at,
            )
            enqueue_event(
                self.conn,
                OutboxEventInput(
                    source="tokenbank.scheduler",
                    type="assignment.progress",
                    subject=f"assignments/{assignment_id}",
                    work_unit_id=assignment["work_unit_id"],
                    attempt_id=assignment["attempt_id"],
                    assignment_id=assignment_id,
                    body={
                        "assignment_id": assignment_id,
                        "worker_id": worker_id,
                        "lease_version": updated["lease_version"],
                    },
                ),
            )
        return {
            "assignment_id": assignment_id,
            "status": "running",
            "lease_version": updated["lease_version"],
            "lease_expires_at": expires_at,
        }

    def record_worker_heartbeat(self, worker_id: str, status: str = "healthy") -> None:
        now = utc_text()
        with transaction(self.conn):
            self.conn.execute(
                """
                INSERT INTO worker_health_snapshots (
                  snapshot_id,
                  worker_id,
                  status,
                  body_json,
                  captured_at
                )
                VALUES (?, ?, ?, ?, ?)
                """,
                (
                    f"whs_{uuid.uuid4().hex}",
                    worker_id,
                    status,
                    canonical_json_dumps({"worker_id": worker_id, "status": status}),
                    now,
                ),
            )
            enqueue_event(
                self.conn,
                OutboxEventInput(
                    source="tokenbank.scheduler",
                    type="worker.heartbeat",
                    subject=f"workers/{worker_id}",
                    body={"worker_id": worker_id, "status": status},
                ),
            )

    def submit_result(
        self,
        *,
        assignment_id: str,
        worker_id: str,
        lease_token: str | None = None,
        lease_token_hash_value: str | None = None,
        output: dict[str, Any],
        result_envelope: dict[str, Any] | WorkUnitResultEnvelope | None = None,
    ) -> dict[str, Any]:
        assignment = self._assignment_for_worker(assignment_id, worker_id)
        if lease_token_hash_value is not None:
            verify_lease_token_hash(
                assignment["lease_token_hash"],
                lease_token_hash_value,
            )
        else:
            verify_lease_token(assignment["lease_token_hash"], lease_token)
        attempt = self._attempt(assignment["attempt_id"])
        late = self._newer_attempt_exists(
            attempt["work_unit_id"],
            int(attempt["attempt_number"]),
        )
        envelope = _coerce_result_envelope(result_envelope)
        if envelope is not None:
            _validate_result_envelope_for_assignment(envelope, assignment)
            output = envelope.output
            out_hash = envelope.output_hash
            res_hash = envelope.result_hash
            result_envelope_id = envelope.result_envelope_id
            status = "quarantined" if late else envelope.status
            body = envelope.model_dump(mode="json")
            if late:
                body["status"] = "quarantined"
        else:
            out_hash = output_hash(output)
            res_hash = result_hash(
                {
                    "attempt_id": assignment["attempt_id"],
                    "assignment_id": assignment_id,
                    "backend_id": assignment["backend_id"],
                    "output_hash": out_hash,
                    "status": "quarantined" if late else "succeeded",
                    "usage_summary": {},
                }
            )
            result_envelope_id = f"res_{uuid.uuid4().hex}"
            status = "quarantined" if late else "succeeded"
            body = {
                "result_envelope_id": result_envelope_id,
                "work_unit_id": assignment["work_unit_id"],
                "attempt_id": assignment["attempt_id"],
                "assignment_id": assignment_id,
                "status": status,
                "output": output,
                "output_hash": out_hash,
                "result_hash": res_hash,
            }
        now = utc_text()
        with transaction(self.conn):
            self.conn.execute(
                """
                INSERT INTO result_envelopes (
                  result_envelope_id,
                  work_unit_id,
                  attempt_id,
                  assignment_id,
                  status,
                  output_hash,
                  result_hash,
                  body_json,
                  created_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    result_envelope_id,
                    assignment["work_unit_id"],
                    assignment["attempt_id"],
                    assignment_id,
                    status,
                    out_hash,
                    res_hash,
                    canonical_json_dumps(body),
                    now,
                ),
            )
            if late:
                self._quarantine_late_result(
                    assignment=assignment,
                    result_envelope_id=result_envelope_id,
                    body=body,
                )
                event_type = "result.quarantined"
            else:
                self.conn.execute(
                    """
                    UPDATE assignments
                    SET status = 'completed',
                        completed_at = ?,
                        updated_at = ?
                    WHERE assignment_id = ?
                    """,
                    (now, now, assignment_id),
                )
                self.conn.execute(
                    """
                    UPDATE execution_attempts
                    SET status = 'succeeded',
                        completed_at = ?
                    WHERE attempt_id = ?
                    """,
                    (now, assignment["attempt_id"]),
                )
                update_work_unit_status(
                    self.conn,
                    work_unit_id=assignment["work_unit_id"],
                    status="succeeded",
                    actor="scheduler",
                    event_type="work_unit.succeeded",
                )
                enqueue_event(
                    self.conn,
                    OutboxEventInput(
                        source="tokenbank.scheduler",
                        type="assignment.completed",
                        subject=f"assignments/{assignment_id}",
                        work_unit_id=assignment["work_unit_id"],
                        attempt_id=assignment["attempt_id"],
                        assignment_id=assignment_id,
                        body={"assignment_id": assignment_id, "status": "completed"},
                    ),
                )
                event_type = "result.submitted"

            enqueue_event(
                self.conn,
                OutboxEventInput(
                    source="tokenbank.scheduler",
                    type=event_type,
                    subject=f"results/{result_envelope_id}",
                    work_unit_id=assignment["work_unit_id"],
                    attempt_id=assignment["attempt_id"],
                    assignment_id=assignment_id,
                    body=body,
                ),
            )
        return {
            "status": status,
            "result_envelope_id": result_envelope_id,
            "output_hash": out_hash,
            "result_hash": res_hash,
        }

    def schedule_retry(self, attempt_id: str) -> str:
        attempt = self._attempt(attempt_id)
        return self.create_attempt(
            work_unit_id=attempt["work_unit_id"],
            route_plan_id=attempt["route_plan_id"],
            policy_decision_id=attempt["policy_decision_id"],
            status="scheduled",
            event_type="scheduler.retry_scheduled",
        )

    def schedule_fallback(self, attempt_id: str) -> str:
        attempt = self._attempt(attempt_id)
        return self.create_attempt(
            work_unit_id=attempt["work_unit_id"],
            route_plan_id=attempt["route_plan_id"],
            policy_decision_id=attempt["policy_decision_id"],
            status="scheduled",
            event_type="scheduler.fallback_scheduled",
        )

    def _quarantine_late_result(
        self,
        *,
        assignment: sqlite3.Row,
        result_envelope_id: str,
        body: dict[str, Any],
    ) -> None:
        now = utc_text()
        self.conn.execute(
            """
            UPDATE assignments
            SET status = 'quarantined',
                completed_at = ?,
                updated_at = ?
            WHERE assignment_id = ?
            """,
            (now, now, assignment["assignment_id"]),
        )
        self.conn.execute(
            """
            UPDATE execution_attempts
            SET status = 'quarantined',
                completed_at = ?
            WHERE attempt_id = ?
            """,
            (now, assignment["attempt_id"]),
        )
        self.conn.execute(
            """
            INSERT INTO result_quarantine (
              quarantine_id,
              result_envelope_id,
              work_unit_id,
              attempt_id,
              assignment_id,
              reason,
              body_json,
              created_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                f"quar_{uuid.uuid4().hex}",
                result_envelope_id,
                assignment["work_unit_id"],
                assignment["attempt_id"],
                assignment["assignment_id"],
                "newer_attempt_exists",
                canonical_json_dumps(body),
                now,
            ),
        )

    def _newer_attempt_exists(self, work_unit_id: str, attempt_number: int) -> bool:
        row = self.conn.execute(
            """
            SELECT 1
            FROM execution_attempts
            WHERE work_unit_id = ?
              AND attempt_number > ?
            LIMIT 1
            """,
            (work_unit_id, attempt_number),
        ).fetchone()
        return row is not None

    def _assignment_for_worker(self, assignment_id: str, worker_id: str) -> sqlite3.Row:
        row = self.conn.execute(
            "SELECT * FROM assignments WHERE assignment_id = ?",
            (assignment_id,),
        ).fetchone()
        if row is None:
            raise KeyError(f"assignment not found: {assignment_id}")
        if row["worker_id"] != worker_id:
            raise PermissionError("worker can only access own assignment")
        return row

    def _attempt(self, attempt_id: str) -> sqlite3.Row:
        row = self.conn.execute(
            "SELECT * FROM execution_attempts WHERE attempt_id = ?",
            (attempt_id,),
        ).fetchone()
        if row is None:
            raise KeyError(f"attempt not found: {attempt_id}")
        return row


def _decode_json_object(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return value
    if not isinstance(value, str) or not value:
        return {}
    import json

    decoded = json.loads(value)
    return decoded if isinstance(decoded, dict) else {}


def _coerce_result_envelope(
    value: dict[str, Any] | WorkUnitResultEnvelope | None,
) -> WorkUnitResultEnvelope | None:
    if value is None:
        return None
    if isinstance(value, WorkUnitResultEnvelope):
        return value
    return WorkUnitResultEnvelope.model_validate(value)


def _validate_result_envelope_for_assignment(
    envelope: WorkUnitResultEnvelope,
    assignment: sqlite3.Row,
) -> None:
    expected = {
        "work_unit_id": assignment["work_unit_id"],
        "attempt_id": assignment["attempt_id"],
        "assignment_id": assignment["assignment_id"],
    }
    observed = {
        "work_unit_id": envelope.work_unit_id,
        "attempt_id": envelope.attempt_id,
        "assignment_id": envelope.assignment_id,
    }
    if observed != expected:
        raise PermissionError("result envelope does not match assignment lease")
    if envelope.worker_id is not None and envelope.worker_id != assignment["worker_id"]:
        raise PermissionError("result envelope worker_id does not match assignment")
