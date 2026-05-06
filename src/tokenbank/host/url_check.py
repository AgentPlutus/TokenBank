"""Minimal host adapter for VS demo vertical slices."""

from __future__ import annotations

import json
import sqlite3
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from tokenbank.backends.adapter import (
    BackendExecutionContext,
    adapter_for_backend_class,
)
from tokenbank.backends.registry import BackendRegistry
from tokenbank.capacity.registry import WorkerManifest
from tokenbank.capacity.validators import CONTROL_PLANE_GATEWAY_WORKER_ID
from tokenbank.config_runtime.loader import LoadedConfig
from tokenbank.core.canonical import canonical_json_dumps, canonical_json_hash
from tokenbank.db.transactions import transaction
from tokenbank.events.outbox import OutboxEventInput, enqueue_event
from tokenbank.models.cost_quality import HostCostQualitySummary
from tokenbank.models.host_summary import HostResultSummary
from tokenbank.models.policy_decision import PolicyDecision
from tokenbank.models.result_envelope import WorkUnitResultEnvelope
from tokenbank.models.route_plan import RouteCandidate, RoutePlan
from tokenbank.models.verifier import VerifierReport
from tokenbank.models.work_unit import WorkUnit
from tokenbank.policy.bundle import compile_policy_bundle
from tokenbank.policy.checks import evaluate_policy
from tokenbank.router.service import RouterService
from tokenbank.scheduler.scheduler import Scheduler
from tokenbank.verifier.runner import VerifierRunner

VS0_TASK_TYPE = "url_check"
VS0_VERIFIER_RECIPE_ID = "url_check_v0"
VS1A_TASK_TYPE = "dedup"
VS1A_VERIFIER_RECIPE_ID = "dedup_v0"
VS1B_TASK_TYPE = "webpage_extraction"
VS1B_VERIFIER_RECIPE_ID = "webpage_extraction_v0"
VS1C_TASK_TYPE = "topic_classification"
VS1C_VERIFIER_RECIPE_ID = "topic_classification_v0"
VS1D_TASK_TYPE = "claim_extraction"
VS1D_VERIFIER_RECIPE_ID = "claim_extraction_v0"
SUPPORTED_DEMO_TASKS = {
    VS0_TASK_TYPE: {
        "phase": "VS0",
        "run_prefix": "run_vs0",
        "work_unit_prefix": "wu_vs0",
        "task_level": "L0",
        "verifier_recipe_id": VS0_VERIFIER_RECIPE_ID,
    },
    VS1A_TASK_TYPE: {
        "phase": "VS1a",
        "run_prefix": "run_vs1a",
        "work_unit_prefix": "wu_vs1a",
        "task_level": "L1",
        "verifier_recipe_id": VS1A_VERIFIER_RECIPE_ID,
    },
    VS1B_TASK_TYPE: {
        "phase": "VS1b",
        "run_prefix": "run_vs1b",
        "work_unit_prefix": "wu_vs1b",
        "task_level": "L1",
        "verifier_recipe_id": VS1B_VERIFIER_RECIPE_ID,
    },
    VS1C_TASK_TYPE: {
        "phase": "VS1c",
        "run_prefix": "run_vs1c",
        "work_unit_prefix": "wu_vs1c",
        "task_level": "L1",
        "verifier_recipe_id": VS1C_VERIFIER_RECIPE_ID,
    },
    VS1D_TASK_TYPE: {
        "phase": "VS1d",
        "run_prefix": "run_vs1d",
        "work_unit_prefix": "wu_vs1d",
        "task_level": "L2",
        "verifier_recipe_id": VS1D_VERIFIER_RECIPE_ID,
    },
}


def submit_url_check_work_unit(
    conn: sqlite3.Connection,
    *,
    loaded_config: LoadedConfig,
    url: str,
    routebook_dir: str | Path | None = None,
) -> dict[str, Any]:
    """Create the VS0 url_check WorkUnit and schedule its first assignment."""
    return _submit_demo_work_unit(
        conn,
        loaded_config=loaded_config,
        task_type=VS0_TASK_TYPE,
        inline_input={"url": url},
        routebook_dir=routebook_dir,
    )


def submit_dedup_work_unit(
    conn: sqlite3.Connection,
    *,
    loaded_config: LoadedConfig,
    items: list[Any],
    routebook_dir: str | Path | None = None,
) -> dict[str, Any]:
    """Create the VS1a dedup WorkUnit and schedule its first assignment."""
    return _submit_demo_work_unit(
        conn,
        loaded_config=loaded_config,
        task_type=VS1A_TASK_TYPE,
        inline_input={"items": items},
        routebook_dir=routebook_dir,
    )


def submit_webpage_extraction_work_unit(
    conn: sqlite3.Connection,
    *,
    loaded_config: LoadedConfig,
    url: str,
    html: str | None = None,
    text: str | None = None,
    title: str | None = None,
    routebook_dir: str | Path | None = None,
) -> dict[str, Any]:
    """Create the VS1b webpage_extraction WorkUnit and schedule assignment."""
    inline_input: dict[str, Any] = {"url": url}
    if html is not None:
        inline_input["html"] = html
    if text is not None:
        inline_input["text"] = text
    if title is not None:
        inline_input["title"] = title
    return _submit_demo_work_unit(
        conn,
        loaded_config=loaded_config,
        task_type=VS1B_TASK_TYPE,
        inline_input=inline_input,
        routebook_dir=routebook_dir,
    )


def submit_topic_classification_work_unit(
    conn: sqlite3.Connection,
    *,
    loaded_config: LoadedConfig,
    text: str,
    allowed_labels: list[str] | None = None,
    routebook_dir: str | Path | None = None,
) -> dict[str, Any]:
    """Create the VS1c topic_classification WorkUnit and schedule assignment."""
    inline_input: dict[str, Any] = {
        "text": text,
        "allowed_labels": allowed_labels or [
            "engineering",
            "finance",
            "policy",
            "science",
            "general",
        ],
    }
    return _submit_demo_work_unit(
        conn,
        loaded_config=loaded_config,
        task_type=VS1C_TASK_TYPE,
        inline_input=inline_input,
        routebook_dir=routebook_dir,
    )


def submit_claim_extraction_work_unit(
    conn: sqlite3.Connection,
    *,
    loaded_config: LoadedConfig,
    text: str,
    source_id: str = "src_claim_1",
    entity: str | None = None,
    allowed_claim_types: list[str] | None = None,
    routebook_dir: str | Path | None = None,
) -> dict[str, Any]:
    """Create the VS1d claim_extraction WorkUnit and schedule assignment."""
    inline_input: dict[str, Any] = {
        "text": text,
        "source_id": source_id,
        "sources": [{"source_id": source_id, "text": text}],
        "allowed_claim_types": allowed_claim_types
        or ["factual", "metric", "policy", "product", "other"],
    }
    if entity is not None:
        inline_input["entity"] = entity
    return _submit_demo_work_unit(
        conn,
        loaded_config=loaded_config,
        task_type=VS1D_TASK_TYPE,
        inline_input=inline_input,
        routebook_dir=routebook_dir,
    )


def execute_control_plane_gateway_assignment_once(
    conn: sqlite3.Connection,
    *,
    assignment_id: str | None = None,
) -> dict[str, Any] | None:
    """Execute one control-plane gateway Assignment for demo model-gateway tasks."""
    scheduler = Scheduler(conn)
    assignment = (
        _assignment_by_id(conn, assignment_id)
        if assignment_id is not None
        else scheduler.poll_next_assignment(CONTROL_PLANE_GATEWAY_WORKER_ID)
    )
    if assignment is None:
        return None
    if assignment["worker_id"] != CONTROL_PLANE_GATEWAY_WORKER_ID:
        raise PermissionError("control-plane gateway can only execute own assignment")
    backend_class = _assignment_backend_class(assignment)
    if backend_class not in {"api_model_gateway", "primary_model_gateway"}:
        raise ValueError(
            "control-plane gateway run-once only supports model gateway backends"
        )

    accepted = scheduler.accept_assignment(
        assignment_id=assignment["assignment_id"],
        worker_id=CONTROL_PLANE_GATEWAY_WORKER_ID,
    )
    refreshed = _assignment_by_id(conn, assignment["assignment_id"])
    if refreshed is None:
        raise KeyError(f"assignment not found: {assignment['assignment_id']}")
    envelope = adapter_for_backend_class(backend_class).execute(
        _gateway_execution_context(refreshed)
    )
    scheduler.progress_assignment(
        assignment_id=assignment["assignment_id"],
        worker_id=CONTROL_PLANE_GATEWAY_WORKER_ID,
        lease_token=accepted["lease_token"],
        expected_lease_version=int(accepted["lease_version"]),
    )
    result = scheduler.submit_result(
        assignment_id=assignment["assignment_id"],
        worker_id=CONTROL_PLANE_GATEWAY_WORKER_ID,
        lease_token=accepted["lease_token"],
        output=envelope.output,
        result_envelope=envelope,
    )
    finalized = finalize_url_check_result(
        conn,
        result_envelope_id=result["result_envelope_id"],
    )
    if finalized is not None:
        result["verifier_report"] = finalized["verifier_report"]
        result["host_result_summary"] = finalized["host_result_summary"]
    return {
        "status": "completed",
        "worker_id": CONTROL_PLANE_GATEWAY_WORKER_ID,
        "assignment_id": assignment["assignment_id"],
        "result": result,
    }


def _submit_demo_work_unit(
    conn: sqlite3.Connection,
    *,
    loaded_config: LoadedConfig,
    task_type: str,
    inline_input: dict[str, Any],
    routebook_dir: str | Path | None = None,
) -> dict[str, Any]:
    config = SUPPORTED_DEMO_TASKS[task_type]
    routebook_root = (
        Path(routebook_dir)
        if routebook_dir
        else loaded_config.root.parent / "routebook"
    )
    now = _utc_now()
    run_id = f"{config['run_prefix']}_{uuid.uuid4().hex}"
    work_unit = WorkUnit(
        work_unit_id=f"{config['work_unit_prefix']}_{uuid.uuid4().hex}",
        run_id=run_id,
        task_type=task_type,
        task_level=config["task_level"],
        status="submitted",
        data_labels=["public_url"],
        inline_input=inline_input,
        max_cost_micros=0,
        created_at=now,
        updated_at=now,
    )
    _persist_run_and_work_unit(conn, work_unit, phase=config["phase"])

    route_plan = RouterService.from_dirs(
        config_dir=loaded_config.root,
        routebook_dir=routebook_root,
    ).plan_route(work_unit.model_dump(mode="json"))
    _persist_route_plan(conn, route_plan)

    selected_candidate = _selected_candidate(route_plan)
    policy_decision = _evaluate_vs0_policy(
        conn,
        loaded_config=loaded_config,
        work_unit=work_unit,
        route_plan=route_plan,
        selected_candidate=selected_candidate,
    )
    _persist_policy_decision(conn, policy_decision)
    if policy_decision.decision != "approved":
        raise ValueError(f"{task_type} WorkUnit denied by policy")

    worker_id = _candidate_worker_id(selected_candidate)
    scheduler = Scheduler(conn)
    attempt_id = scheduler.create_attempt(
        work_unit_id=work_unit.work_unit_id,
        route_plan_id=route_plan.route_plan_id,
        policy_decision_id=policy_decision.policy_decision_id,
    )
    assignment_id = scheduler.create_assignment(
        attempt_id=attempt_id,
        worker_id=worker_id,
        capacity_node_id=selected_candidate.capacity_node_id,
        backend_id=selected_candidate.backend_id,
        backend_class=selected_candidate.backend_class,
        effective_constraints={
            "input": work_unit.inline_input,
            "run_id": work_unit.run_id,
            "task_type": work_unit.task_type,
            "task_level": work_unit.task_level,
            "backend_class": selected_candidate.backend_class,
            "route_plan_id": route_plan.route_plan_id,
            "policy_decision_id": policy_decision.policy_decision_id,
            "verifier_recipe_id": route_plan.verifier_recipe_id,
            "policy": policy_decision.effective_constraints,
        },
    )
    return {
        "status": "submitted",
        "run_id": work_unit.run_id,
        "work_unit_id": work_unit.work_unit_id,
        "route_plan_id": route_plan.route_plan_id,
        "policy_decision_id": policy_decision.policy_decision_id,
        "attempt_id": attempt_id,
        "assignment_id": assignment_id,
        "worker_id": worker_id,
        "capacity_node_id": selected_candidate.capacity_node_id,
        "backend_id": selected_candidate.backend_id,
        "backend_class": selected_candidate.backend_class,
        "verifier_recipe_id": route_plan.verifier_recipe_id,
    }


def finalize_url_check_result(
    conn: sqlite3.Connection,
    *,
    result_envelope_id: str,
) -> dict[str, Any] | None:
    """Finalize supported demo-task results and create a HostResultSummary."""
    envelope_row = conn.execute(
        """
        SELECT body_json
        FROM result_envelopes
        WHERE result_envelope_id = ?
        """,
        (result_envelope_id,),
    ).fetchone()
    if envelope_row is None:
        return None

    try:
        envelope = WorkUnitResultEnvelope.model_validate_json(envelope_row["body_json"])
    except ValueError:
        return None
    context = _load_supported_context(conn, envelope.work_unit_id)
    if context is None:
        return None

    work_unit, route_plan, policy_decision = context
    report = VerifierRunner.for_recipe_id(route_plan.verifier_recipe_id).run(
        result_envelope=envelope,
        work_unit=work_unit.model_dump(mode="json"),
        policy_decision=policy_decision.model_dump(mode="json"),
    )
    _persist_verifier_report(conn, report)
    summary = _build_host_summary(
        work_unit=work_unit,
        envelope=envelope,
        report=report,
    )
    _persist_host_result_summary(conn, summary)
    return {
        "verifier_report": report.model_dump(mode="json"),
        "host_result_summary": summary.model_dump(mode="json"),
    }


def get_host_result_summary(
    conn: sqlite3.Connection,
    *,
    work_unit_id: str,
) -> HostResultSummary | None:
    row = conn.execute(
        """
        SELECT body_json
        FROM host_result_summaries
        WHERE work_unit_id = ?
        ORDER BY created_at DESC
        LIMIT 1
        """,
        (work_unit_id,),
    ).fetchone()
    if row is not None:
        return HostResultSummary.model_validate_json(row["body_json"])

    result_row = conn.execute(
        """
        SELECT result_envelope_id
        FROM result_envelopes
        WHERE work_unit_id = ?
        ORDER BY created_at DESC
        LIMIT 1
        """,
        (work_unit_id,),
    ).fetchone()
    if result_row is None:
        return None
    finalized = finalize_url_check_result(
        conn,
        result_envelope_id=result_row["result_envelope_id"],
    )
    if finalized is None:
        return None
    return HostResultSummary.model_validate(finalized["host_result_summary"])


def get_work_unit_status(
    conn: sqlite3.Connection,
    *,
    work_unit_id: str,
) -> dict[str, Any] | None:
    row = conn.execute(
        """
        SELECT work_unit_id, run_id, status, task_type, task_level, body_json
        FROM work_units
        WHERE work_unit_id = ?
        """,
        (work_unit_id,),
    ).fetchone()
    return None if row is None else dict(row)


def _persist_run_and_work_unit(
    conn: sqlite3.Connection,
    work_unit: WorkUnit,
    *,
    phase: str,
) -> None:
    now = _utc_text(work_unit.created_at)
    run_body = {
        "run_id": work_unit.run_id,
        "source": f"host.{work_unit.task_type}",
        "task_type": work_unit.task_type,
        "phase": phase,
    }
    work_unit_body = work_unit.model_dump(mode="json")
    with transaction(conn):
        conn.execute(
            """
            INSERT INTO runs (run_id, status, body_json, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?)
            """,
            (
                work_unit.run_id,
                "submitted",
                canonical_json_dumps(run_body),
                now,
                now,
            ),
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
            (
                work_unit.work_unit_id,
                work_unit.run_id,
                work_unit.status,
                work_unit.task_type,
                work_unit.task_level,
                canonical_json_dumps(work_unit_body),
                now,
                now,
            ),
        )
        enqueue_event(
            conn,
            OutboxEventInput(
                source="tokenbank.host",
                type="run.created",
                subject=f"runs/{work_unit.run_id}",
                run_id=work_unit.run_id,
                body=run_body,
            ),
        )
        enqueue_event(
            conn,
            OutboxEventInput(
                source="tokenbank.host",
                type="work_unit.created",
                subject=f"work_units/{work_unit.work_unit_id}",
                run_id=work_unit.run_id,
                work_unit_id=work_unit.work_unit_id,
                body=work_unit_body,
            ),
        )


def _persist_route_plan(conn: sqlite3.Connection, route_plan: RoutePlan) -> None:
    body = route_plan.model_dump(mode="json")
    created_at = _utc_text(route_plan.created_at)
    with transaction(conn):
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
            ON CONFLICT(route_plan_id) DO UPDATE SET
              status = excluded.status,
              body_json = excluded.body_json
            """,
            (
                route_plan.route_plan_id,
                route_plan.work_unit_id,
                "planned",
                canonical_json_dumps(body),
                created_at,
            ),
        )
        enqueue_event(
            conn,
            OutboxEventInput(
                source="tokenbank.router",
                type="route_plan.created",
                subject=f"route_plans/{route_plan.route_plan_id}",
                work_unit_id=route_plan.work_unit_id,
                body=body,
            ),
        )


def _evaluate_vs0_policy(
    conn: sqlite3.Connection,
    *,
    loaded_config: LoadedConfig,
    work_unit: WorkUnit,
    route_plan: RoutePlan,
    selected_candidate: RouteCandidate,
) -> PolicyDecision:
    backend_manifest = BackendRegistry.from_config(loaded_config).get(
        selected_candidate.backend_id
    )
    worker_manifest = _worker_manifest(
        conn,
        loaded_config=loaded_config,
        worker_id=_candidate_worker_id(selected_candidate),
    )
    route_payload = route_plan.model_dump(mode="json")
    route_payload["backend_id"] = selected_candidate.backend_id
    route_payload["backend_class"] = selected_candidate.backend_class
    return evaluate_policy(
        work_unit=work_unit.model_dump(mode="json"),
        route_plan=route_payload,
        worker_manifest=worker_manifest.model_dump(mode="json"),
        backend_manifest=backend_manifest.model_dump(mode="json"),
        policy_bundle=compile_policy_bundle(loaded_config),
    )


def _persist_policy_decision(
    conn: sqlite3.Connection,
    policy_decision: PolicyDecision,
) -> None:
    body = policy_decision.model_dump(mode="json")
    created_at = _utc_text(policy_decision.decided_at)
    with transaction(conn):
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
            ON CONFLICT(policy_decision_id) DO UPDATE SET
              decision = excluded.decision,
              body_json = excluded.body_json
            """,
            (
                policy_decision.policy_decision_id,
                policy_decision.work_unit_id,
                policy_decision.route_plan_id,
                policy_decision.decision,
                canonical_json_dumps(body),
                created_at,
            ),
        )
        enqueue_event(
            conn,
            OutboxEventInput(
                source="tokenbank.policy",
                type="policy_decision.created",
                subject=f"policy_decisions/{policy_decision.policy_decision_id}",
                work_unit_id=policy_decision.work_unit_id,
                body=body,
            ),
        )


def _persist_verifier_report(
    conn: sqlite3.Connection,
    report: VerifierReport,
) -> None:
    body = report.model_dump(mode="json")
    created_at = _utc_text(report.created_at)
    with transaction(conn):
        conn.execute(
            """
            INSERT INTO verifier_reports (
              verifier_report_id,
              work_unit_id,
              result_envelope_id,
              status,
              recommendation,
              body_json,
              created_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(verifier_report_id) DO UPDATE SET
              status = excluded.status,
              recommendation = excluded.recommendation,
              body_json = excluded.body_json
            """,
            (
                report.verifier_report_id,
                report.work_unit_id,
                report.result_envelope_id,
                report.status,
                report.recommendation,
                canonical_json_dumps(body),
                created_at,
            ),
        )
        for index, check in enumerate(report.checks):
            check_body = check.model_dump(mode="json")
            check_result_id = "vcr_" + canonical_json_hash(
                {
                    "verifier_report_id": report.verifier_report_id,
                    "index": index,
                    "name": check.name,
                }
            )[:24]
            conn.execute(
                """
                INSERT INTO verifier_check_results (
                  check_result_id,
                  verifier_report_id,
                  status,
                  body_json,
                  created_at
                )
                VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(check_result_id) DO UPDATE SET
                  status = excluded.status,
                  body_json = excluded.body_json
                """,
                (
                    check_result_id,
                    report.verifier_report_id,
                    check.status,
                    canonical_json_dumps(check_body),
                    created_at,
                ),
            )
        enqueue_event(
            conn,
            OutboxEventInput(
                source="tokenbank.verifier",
                type="verifier_report.created",
                subject=f"verifier_reports/{report.verifier_report_id}",
                work_unit_id=report.work_unit_id,
                body=body,
            ),
        )


def _build_host_summary(
    *,
    work_unit: WorkUnit,
    envelope: WorkUnitResultEnvelope,
    report: VerifierReport,
) -> HostResultSummary:
    warnings = [
        check.message
        for check in report.checks
        if check.status == "needs_review"
    ]
    caveats = []
    if envelope.cost_source == "zero_internal_phase0":
        caveats.append(
            f"Phase 0 local {work_unit.task_type} uses "
            "zero_internal_phase0 cost accounting."
        )
    return HostResultSummary(
        work_unit_id=work_unit.work_unit_id,
        run_id=work_unit.run_id,
        status=_summary_status(envelope, report),
        task_type=work_unit.task_type,
        task_level=work_unit.task_level,
        verifier_status=report.status,
        verifier_recommendation=report.recommendation,
        result_summary=_result_summary(envelope.output),
        duration_ms=envelope.duration_ms,
        backend_class=envelope.backend_class or _default_backend_class(work_unit),
        backend_id=envelope.backend_id or _default_backend_id(work_unit),
        worker_id=envelope.worker_id or "unknown_worker",
        capacity_node_id=envelope.capacity_node_id or "unknown_capacity_node",
        cost_summary=HostCostQualitySummary(
            estimated_cost_micros=envelope.cost_estimate_micros,
            actual_cost_micros=envelope.actual_cost_micros,
            cost_source=envelope.cost_source,
            cost_confidence=envelope.cost_confidence,
            local_zero_cost_caveat=caveats[0] if caveats else None,
            verifier_passed=report.status in {"passed", "needs_review"},
            quality_status=(
                "passed"
                if report.status == "passed"
                else "needs_review"
                if report.status == "needs_review"
                else "failed"
            ),
            audit_status=(
                "quarantined"
                if report.recommendation == "quarantine"
                else "warning"
                if warnings
                else "clean"
            ),
            caveats=caveats,
        ),
        warnings=warnings,
        caveats=caveats,
        quarantine_status=(
            "quarantined" if report.recommendation == "quarantine" else "none"
        ),
        trace_ref=envelope.result_envelope_id,
    )


def _persist_host_result_summary(
    conn: sqlite3.Connection,
    summary: HostResultSummary,
) -> None:
    body = summary.model_dump(mode="json")
    summary_id = "hrs_" + canonical_json_hash(
        {
            "work_unit_id": summary.work_unit_id,
            "trace_ref": summary.trace_ref,
            "recommendation": summary.verifier_recommendation,
        }
    )[:24]
    with transaction(conn):
        conn.execute(
            """
            INSERT INTO host_result_summaries (
              host_result_summary_id,
              work_unit_id,
              run_id,
              body_json,
              created_at
            )
            VALUES (?, ?, ?, ?, ?)
            ON CONFLICT(host_result_summary_id) DO UPDATE SET
              body_json = excluded.body_json
            """,
            (
                summary_id,
                summary.work_unit_id,
                summary.run_id,
                canonical_json_dumps(body),
                _utc_text(summary.generated_at),
            ),
        )
        enqueue_event(
            conn,
            OutboxEventInput(
                source="tokenbank.host",
                type="host_result_summary.created",
                subject=f"host_result_summaries/{summary_id}",
                run_id=summary.run_id,
                work_unit_id=summary.work_unit_id,
                body=body,
            ),
        )


def _load_supported_context(
    conn: sqlite3.Connection,
    work_unit_id: str,
) -> tuple[WorkUnit, RoutePlan, PolicyDecision] | None:
    work_unit_row = conn.execute(
        "SELECT body_json FROM work_units WHERE work_unit_id = ?",
        (work_unit_id,),
    ).fetchone()
    route_plan_row = conn.execute(
        """
        SELECT body_json
        FROM route_plans
        WHERE work_unit_id = ?
        ORDER BY created_at DESC
        LIMIT 1
        """,
        (work_unit_id,),
    ).fetchone()
    policy_row = conn.execute(
        """
        SELECT body_json
        FROM policy_decisions
        WHERE work_unit_id = ?
        ORDER BY created_at DESC
        LIMIT 1
        """,
        (work_unit_id,),
    ).fetchone()
    if work_unit_row is None or route_plan_row is None or policy_row is None:
        return None
    work_unit_payload = _json_object(work_unit_row["body_json"])
    route_plan_payload = _json_object(route_plan_row["body_json"])
    policy_payload = _json_object(policy_row["body_json"])
    task_type = work_unit_payload.get("task_type")
    if task_type not in SUPPORTED_DEMO_TASKS:
        return None
    expected_recipe_id = SUPPORTED_DEMO_TASKS[task_type]["verifier_recipe_id"]
    if route_plan_payload.get("verifier_recipe_id") != expected_recipe_id:
        return None
    return (
        WorkUnit.model_validate(work_unit_payload),
        RoutePlan.model_validate(route_plan_payload),
        PolicyDecision.model_validate(policy_payload),
    )


def _worker_manifest(
    conn: sqlite3.Connection,
    *,
    loaded_config: LoadedConfig,
    worker_id: str,
):
    workers_by_id = {
        worker.worker_id: worker
        for worker in _worker_manifests_from_config(loaded_config)
    }
    for worker in _stored_worker_manifests(conn):
        workers_by_id[worker.worker_id] = worker
    try:
        return workers_by_id[worker_id]
    except KeyError as exc:
        raise ValueError(f"unknown worker_id for demo route: {worker_id}") from exc


def _worker_manifests_from_config(config: LoadedConfig) -> list[WorkerManifest]:
    workers = config.documents["capacity_registry"].get("capacity_registry", {}).get(
        "worker_manifests",
        [],
    )
    return [
        WorkerManifest(
            worker_id=worker["worker_id"],
            identity=worker.get("identity", worker["worker_id"]),
            capabilities=worker.get("allowed_task_types", []),
            allowed_task_types=worker.get("allowed_task_types", []),
            allowed_data_labels=worker.get("allowed_data_labels", ["public_url"]),
            allowed_privacy_levels=worker.get("allowed_privacy_levels", ["private"]),
            execution_location=worker.get("execution_location", "windows_worker"),
            trust_level=worker.get("trust_level", "trusted_private"),
            backend_ids=worker.get("backend_ids", []),
            backend_classes=worker.get("backend_classes", ["local_tool"]),
            health_status=worker.get("health_status", "healthy"),
            manifest_hash=worker.get("manifest_hash"),
        )
        for worker in workers
    ]


def _stored_worker_manifests(conn: sqlite3.Connection) -> list[WorkerManifest]:
    rows = conn.execute(
        "SELECT body_json FROM worker_manifests ORDER BY worker_id"
    ).fetchall()
    return [
        WorkerManifest.model_validate_json(row["body_json"])
        for row in rows
    ]


def _selected_candidate(route_plan: RoutePlan) -> RouteCandidate:
    for candidate in route_plan.candidates:
        if candidate.route_candidate_id == route_plan.selected_candidate_id:
            return candidate
    raise ValueError("RoutePlan selected candidate is missing")


def _candidate_worker_id(candidate: RouteCandidate) -> str:
    worker_id = candidate.worker_selector.get("worker_id")
    if not isinstance(worker_id, str) or not worker_id:
        raise ValueError("demo task route requires a concrete worker_id")
    return worker_id


def _summary_status(
    envelope: WorkUnitResultEnvelope,
    report: VerifierReport,
) -> str:
    if report.recommendation == "quarantine" or envelope.status == "quarantined":
        return "quarantined"
    if report.recommendation in {"accept", "accept_with_warning"}:
        return "succeeded"
    if envelope.status == "failed":
        return "failed"
    return "failed"


def _result_summary(output: dict[str, Any]) -> str:
    claims = output.get("claims")
    if isinstance(claims, list) and claims:
        return f"claim_extraction accepted {len(claims)} claim(s)"
    label = output.get("label")
    confidence = output.get("confidence")
    if isinstance(label, str) and isinstance(confidence, int | float):
        return f"topic_classification accepted {label} at {confidence:.2f}"
    extracted = output.get("extracted")
    if isinstance(extracted, dict):
        title = extracted.get("title")
        if isinstance(title, str) and title:
            return f"webpage_extraction accepted {title}"
        url = extracted.get("url") or output.get("url")
        if isinstance(url, str) and url:
            return f"webpage_extraction accepted {url}"
        return "webpage_extraction accepted extracted content"
    if "unique_items" in output and isinstance(output.get("duplicate_count"), int):
        duplicate_count = output["duplicate_count"]
        unique_count = len(output["unique_items"])
        return (
            f"dedup accepted {unique_count} unique items "
            f"with {duplicate_count} duplicates"
        )
    url = output.get("url") or output.get("final_url")
    if output.get("ok") is True and isinstance(url, str):
        return f"url_check accepted {url}"
    if isinstance(url, str):
        return f"url_check completed with warnings for {url}"
    return "url_check completed"


def _default_backend_class(work_unit: WorkUnit) -> str:
    if work_unit.task_type in {VS1C_TASK_TYPE, VS1D_TASK_TYPE}:
        return "api_model_gateway"
    if work_unit.task_type == VS1B_TASK_TYPE:
        return "browser_fetch"
    if work_unit.task_type == VS1A_TASK_TYPE:
        return "local_script"
    return "local_tool"


def _default_backend_id(work_unit: WorkUnit) -> str:
    if work_unit.task_type == VS1D_TASK_TYPE:
        return "backend:claim_extraction:api_gateway:v0"
    if work_unit.task_type == VS1C_TASK_TYPE:
        return "backend:topic_classification:api_gateway:v0"
    if work_unit.task_type == VS1B_TASK_TYPE:
        return "backend:webpage_extraction:browser_fetch:v0"
    if work_unit.task_type == VS1A_TASK_TYPE:
        return "backend:dedup:local_script:v0"
    return "backend:url_check:v0"


def _json_object(value: str) -> dict[str, Any]:
    loaded = json.loads(value)
    return loaded if isinstance(loaded, dict) else {}


def _utc_now() -> datetime:
    return datetime.now(UTC)


def _utc_text(value: datetime) -> str:
    return value.isoformat().replace("+00:00", "Z")


def _assignment_by_id(
    conn: sqlite3.Connection,
    assignment_id: str,
) -> dict[str, Any] | None:
    row = conn.execute(
        "SELECT * FROM assignments WHERE assignment_id = ?",
        (assignment_id,),
    ).fetchone()
    if row is None:
        return None
    assignment = dict(row)
    assignment["body"] = _json_object(assignment.get("body_json") or "{}")
    assignment["effective_constraints"] = _json_object(
        assignment.get("effective_constraints_json") or "{}"
    )
    return assignment


def _assignment_backend_class(assignment: dict[str, Any]) -> str:
    body = assignment.get("body")
    effective_constraints = assignment.get("effective_constraints")
    if isinstance(body, dict) and isinstance(body.get("backend_class"), str):
        return body["backend_class"]
    if (
        isinstance(effective_constraints, dict)
        and isinstance(effective_constraints.get("backend_class"), str)
    ):
        return effective_constraints["backend_class"]
    backend_id = str(assignment.get("backend_id") or "")
    if "api_gateway" in backend_id:
        return "api_model_gateway"
    return str(assignment.get("backend_class") or "")


def _gateway_execution_context(
    assignment: dict[str, Any],
) -> BackendExecutionContext:
    effective_constraints = assignment.get("effective_constraints")
    if not isinstance(effective_constraints, dict):
        effective_constraints = {}
    body = assignment.get("body")
    if not isinstance(body, dict):
        body = {}
    input_payload = effective_constraints.get("input")
    if not isinstance(input_payload, dict):
        input_payload = {}
    task_type = str(effective_constraints.get("task_type") or body.get("task_type"))
    return BackendExecutionContext(
        work_unit_id=str(assignment["work_unit_id"]),
        run_id=str(effective_constraints.get("run_id") or body.get("run_id")),
        attempt_id=str(assignment["attempt_id"]),
        assignment_id=str(assignment["assignment_id"]),
        backend_id=str(assignment["backend_id"]),
        backend_class=_assignment_backend_class(assignment),
        task_type=task_type,
        input_payload=input_payload,
        effective_constraints=effective_constraints,
        worker_id=CONTROL_PLANE_GATEWAY_WORKER_ID,
        capacity_node_id=f"capnode:worker:{CONTROL_PLANE_GATEWAY_WORKER_ID}",
        provider_id="provider:p0_deterministic_stub",
        model_id=_gateway_model_id(task_type),
    )


def _gateway_model_id(task_type: str) -> str:
    if task_type == VS1D_TASK_TYPE:
        return "model:p0_claim_stub"
    return "model:p0_topic_stub"
