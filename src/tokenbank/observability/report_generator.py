"""Derived CostQualityReport generation."""

from __future__ import annotations

import json
import sqlite3
from datetime import UTC, datetime
from typing import Any

from tokenbank.core.canonical import canonical_json_hash
from tokenbank.observability.baseline import resolve_baseline
from tokenbank.observability.cost_accounting import (
    cost_caveats,
    effective_cost_micros,
    host_cost_quality_summary,
    primary_model_fallback_cost,
)
from tokenbank.observability.metrics import (
    backend_task_worker_summaries,
    capacity_node_summaries,
    summarize_totals,
)
from tokenbank.observability.reproducibility import reproducibility_metadata
from tokenbank.observability.sql_queries import (
    event_summary_for_run,
    result_rows_for_run,
)
from tokenbank.policy.redaction import redact_token_prefixes


def generate_cost_quality_report(
    conn: sqlite3.Connection,
    *,
    run_id: str,
    baseline_mode: str = "none",
) -> dict[str, Any]:
    rows = _completed_rows(result_rows_for_run(conn, run_id))
    estimated_total = sum(
        _non_negative_int(row["result_body"].get("cost_estimate_micros"))
        for row in rows
    )
    baseline = resolve_baseline(
        conn,
        run_id=run_id,
        baseline_mode=baseline_mode,
        estimated_cost_micros=estimated_total,
    )
    totals = summarize_totals(rows)
    observed_cost = int(totals["cost_micros"])
    saving_ratio_bps = baseline.saving_ratio_bps(observed_cost)
    event_summary = event_summary_for_run(conn, run_id)
    caveats = _report_caveats(rows, baseline.caveats)
    report = {
        "report_type": "cost_quality_report",
        "cost_quality_report_id": _report_id(run_id, rows, baseline.mode),
        "run_id": run_id,
        "generated_at": _utc_now_text(),
        "baseline": {
            "baseline_mode": baseline.mode,
            "baseline_cost_micros": baseline.baseline_cost_micros,
            "saving_ratio_bps": saving_ratio_bps,
            "saving_claimed": saving_ratio_bps is not None,
            "caveats": list(baseline.caveats),
        },
        "totals": {
            **totals,
            "primary_model_fallback_cost_micros": primary_model_fallback_cost(rows),
        },
        "host_cost_quality_summaries": [
            _host_summary(row, baseline.mode, baseline.baseline_cost_micros)
            for row in rows
        ],
        "capacity_node_summaries": capacity_node_summaries(rows),
        "summaries": backend_task_worker_summaries(rows),
        "event_summary": event_summary,
        "reproducibility": reproducibility_metadata(
            run_id=run_id,
            rows=rows,
            event_summary=event_summary,
        ),
        "caveats": caveats,
    }
    return redact_report(report)


def generate_capacity_report(
    conn: sqlite3.Connection,
    *,
    run_id: str,
) -> dict[str, Any]:
    rows = _completed_rows(result_rows_for_run(conn, run_id))
    report = {
        "report_type": "capacity_performance_report",
        "run_id": run_id,
        "generated_at": _utc_now_text(),
        "capacity_node_summaries": capacity_node_summaries(rows),
        "event_summary": event_summary_for_run(conn, run_id),
    }
    return redact_report(report)


def redact_report(report: dict[str, Any]) -> dict[str, Any]:
    serialized = json.dumps(report, sort_keys=True)
    redacted = redact_token_prefixes(serialized)
    redacted = _redact_secret_like(redacted)
    return json.loads(redacted)


def _host_summary(
    row: dict[str, Any],
    baseline_mode: str,
    baseline_cost_micros: int | None,
) -> dict[str, Any]:
    cost = effective_cost_micros(row["result_body"])
    saving_ratio_bps = None
    if baseline_mode != "none" and baseline_cost_micros:
        saving_ratio_bps = int(
            (baseline_cost_micros - cost) * 10_000 / baseline_cost_micros
        )
    summary = host_cost_quality_summary(
        result_body=row["result_body"],
        verifier_body=row["verifier_body"],
        baseline_mode=baseline_mode,
        baseline_cost_micros=baseline_cost_micros,
        saving_ratio_bps=saving_ratio_bps,
    )
    return {
        "work_unit_id": row["work_unit_id"],
        "task_type": row["task_type"],
        "backend_class": row["result_body"].get("backend_class"),
        "backend_id": row["result_body"].get("backend_id"),
        "worker_id": row["result_body"].get("worker_id") or row.get("worker_id"),
        "capacity_node_id": row["result_body"].get("capacity_node_id")
        or row.get("capacity_node_id"),
        "verifier_status": row["verifier_status"],
        "verifier_recommendation": row["recommendation"],
        "result_envelope_id": row["result_envelope_id"],
        "output_hash": row["output_hash"],
        "result_hash": row["result_hash"],
        "cost_summary": summary.model_dump(mode="json"),
    }


def _completed_rows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [
        row
        for row in rows
        if row.get("result_envelope_id") and row.get("verifier_report_id")
    ]


def _report_caveats(
    rows: list[dict[str, Any]],
    baseline_caveats: tuple[str, ...],
) -> list[str]:
    caveats: list[str] = list(baseline_caveats)
    for row in rows:
        for caveat in cost_caveats(row["result_body"]):
            if caveat not in caveats:
                caveats.append(caveat)
    if any(row["result_body"].get("cost_source") == "estimated" for row in rows):
        caveat = (
            "estimated_only cost fields are reported separately from measured cost."
        )
        if caveat not in caveats:
            caveats.append(caveat)
    return caveats


def _report_id(
    run_id: str,
    rows: list[dict[str, Any]],
    baseline_mode: str,
) -> str:
    return "cqr_" + canonical_json_hash(
        {
            "run_id": run_id,
            "baseline_mode": baseline_mode,
            "result_envelope_ids": [
                row["result_envelope_id"]
                for row in rows
                if row.get("result_envelope_id")
            ],
        }
    )[:24]


def _redact_secret_like(serialized: str) -> str:
    import re

    redacted = re.sub(r"sk-[A-Za-z0-9_-]+", "[REDACTED_SECRET]", serialized)
    redacted = re.sub(
        r"(?i)(bearer\s+)[A-Za-z0-9._-]+",
        r"\1[REDACTED_SECRET]",
        redacted,
    )
    return redacted


def _non_negative_int(value: Any) -> int:
    if isinstance(value, bool):
        return 0
    if isinstance(value, int) and value >= 0:
        return value
    return 0


def _utc_now_text() -> str:
    return datetime.now(UTC).isoformat().replace("+00:00", "Z")
