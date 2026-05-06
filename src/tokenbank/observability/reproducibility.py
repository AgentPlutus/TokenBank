"""Metadata-only reproducibility bundle for reports."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from tokenbank.core.canonical import canonical_json_hash


def reproducibility_metadata(
    *,
    run_id: str,
    rows: list[dict[str, Any]],
    event_summary: dict[str, Any],
) -> dict[str, Any]:
    object_refs = [
        {
            "work_unit_id": row.get("work_unit_id"),
            "attempt_id": row.get("attempt_id"),
            "assignment_id": row.get("assignment_id"),
            "result_envelope_id": row.get("result_envelope_id"),
            "verifier_report_id": row.get("verifier_report_id"),
            "output_hash": row.get("output_hash"),
            "result_hash": row.get("result_hash"),
        }
        for row in rows
    ]
    payload = {
        "run_id": run_id,
        "object_refs": object_refs,
        "event_count": event_summary.get("event_count", 0),
    }
    return {
        "metadata_only": True,
        "generated_at": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
        "source_tables": [
            "work_units",
            "assignments",
            "result_envelopes",
            "verifier_reports",
            "event_outbox",
        ],
        "object_refs": object_refs,
        "reproducibility_hash": canonical_json_hash(payload),
    }
