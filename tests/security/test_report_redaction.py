from __future__ import annotations

import json
from pathlib import Path

from tokenbank.core.canonical import canonical_json_dumps
from tokenbank.db.bootstrap import initialize_database
from tokenbank.events.outbox import OutboxEventInput, enqueue_event
from tokenbank.observability.report_generator import generate_cost_quality_report


def test_report_has_no_raw_secret(tmp_path: Path) -> None:
    conn = initialize_database(tmp_path / "report_redaction.db")
    now = "2026-05-04T00:00:00Z"
    secret = "sk-test-secret-token"
    host_token = "tbk_h_secret_report_token"
    run_id = "run_report_secret"
    work_unit_id = "wu_report_secret"
    attempt_id = "att_report_secret"
    assignment_id = "asg_report_secret"
    result_envelope_id = "res_report_secret"
    verifier_report_id = "vr_report_secret"
    result_body = {
        "result_envelope_id": result_envelope_id,
        "work_unit_id": work_unit_id,
        "run_id": run_id,
        "attempt_id": attempt_id,
        "assignment_id": assignment_id,
        "status": "succeeded",
        "backend_id": "backend:url_check:v0",
        "backend_class": "local_tool",
        "worker_id": "wrk_secret",
        "capacity_node_id": "capnode:worker:wrk_secret",
        "output_hash": "a" * 64,
        "result_hash": "b" * 64,
        "cost_estimate_micros": 0,
        "actual_cost_micros": 0,
        "cost_source": "zero_internal_phase0",
        "cost_confidence": "high",
        "duration_ms": 1,
        "redacted_logs": [f"raw secret should not leak {secret}"],
        "errors": [],
    }
    verifier_body = {
        "verifier_report_id": verifier_report_id,
        "work_unit_id": work_unit_id,
        "result_envelope_id": result_envelope_id,
        "status": "passed",
        "recommendation": "accept",
    }
    conn.execute(
        "INSERT INTO runs VALUES (?, ?, ?, ?, ?)",
        (run_id, "succeeded", "{}", now, now),
    )
    conn.execute(
        "INSERT INTO work_units VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
        (work_unit_id, run_id, "succeeded", "url_check", "L1", "{}", now, now),
    )
    conn.execute(
        "INSERT INTO route_plans VALUES (?, ?, ?, ?, ?)",
        ("rp_report_secret", work_unit_id, "planned", "{}", now),
    )
    conn.execute(
        "INSERT INTO policy_decisions VALUES (?, ?, ?, ?, ?, ?)",
        (
            "pd_report_secret",
            work_unit_id,
            "rp_report_secret",
            "approved",
            "{}",
            now,
        ),
    )
    conn.execute(
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
            "rp_report_secret",
            "pd_report_secret",
            "succeeded",
            "{}",
            now,
            1,
        ),
    )
    conn.execute(
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
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            assignment_id,
            attempt_id,
            work_unit_id,
            "wrk_secret",
            "completed",
            "{}",
            now,
            "capnode:worker:wrk_secret",
            "backend:url_check:v0",
            "{}",
            now,
            now,
        ),
    )
    conn.execute(
        "INSERT INTO result_envelopes VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (
            result_envelope_id,
            work_unit_id,
            attempt_id,
            assignment_id,
            "succeeded",
            "a" * 64,
            "b" * 64,
            canonical_json_dumps(result_body),
            now,
        ),
    )
    conn.execute(
        "INSERT INTO verifier_reports VALUES (?, ?, ?, ?, ?, ?, ?)",
        (
            verifier_report_id,
            work_unit_id,
            result_envelope_id,
            "passed",
            "accept",
            canonical_json_dumps(verifier_body),
            now,
        ),
    )
    enqueue_event(
        conn,
        OutboxEventInput(
            source="tokenbank.test",
            type="secret.test",
            subject="secrets/test",
            run_id=run_id,
            work_unit_id=work_unit_id,
            body={"secret": secret, "token": host_token},
        ),
    )
    conn.commit()

    report = generate_cost_quality_report(conn, run_id=run_id)
    serialized = json.dumps(report, sort_keys=True)

    assert secret not in serialized
    assert host_token not in serialized
    assert "redacted_logs" not in serialized
