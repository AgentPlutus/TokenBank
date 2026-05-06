"""Local usage ledger repository."""

from __future__ import annotations

import json
import sqlite3
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from tokenbank.core.canonical import canonical_json_dumps, canonical_json_hash
from tokenbank.db.transactions import transaction
from tokenbank.events.outbox import OutboxEventInput, enqueue_event
from tokenbank.models.usage_ledger import UsageLedgerEntry
from tokenbank.routebook.v1_loader import load_routebook_v1_dir


class UsageLedgerRepository:
    """Record redacted local usage facts derived from persisted results."""

    def __init__(self, conn: sqlite3.Connection):
        self.conn = conn

    def record_for_work_unit(
        self,
        *,
        work_unit_id: str,
        account_snapshot_id: str | None = None,
        routebook_v1_dir: str | Path = "packs/base-routing/routebook",
    ) -> dict[str, Any]:
        context = self._completed_context(work_unit_id)
        routebook = load_routebook_v1_dir(routebook_v1_dir)
        entry = _build_usage_entry(
            context=context,
            account_snapshot_id=account_snapshot_id,
            routebook_id=routebook.routebook_id,
            routebook_version=routebook.version,
        )
        return self.upsert_entry(entry)

    def upsert_entry(self, entry: UsageLedgerEntry) -> dict[str, Any]:
        body = entry.model_dump(mode="json")
        created_at = _utc_text(entry.created_at)
        with transaction(self.conn):
            self.conn.execute(
                """
                INSERT INTO usage_ledger_entries (
                  usage_ledger_entry_id,
                  work_unit_id,
                  run_id,
                  route_plan_id,
                  result_envelope_id,
                  verifier_report_id,
                  account_snapshot_id,
                  usage_source,
                  cost_source,
                  billable_cost_micros,
                  entry_hash,
                  body_json,
                  created_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(usage_ledger_entry_id) DO UPDATE SET
                  verifier_report_id = excluded.verifier_report_id,
                  account_snapshot_id = excluded.account_snapshot_id,
                  usage_source = excluded.usage_source,
                  cost_source = excluded.cost_source,
                  billable_cost_micros = excluded.billable_cost_micros,
                  entry_hash = excluded.entry_hash,
                  body_json = excluded.body_json
                """,
                (
                    entry.usage_ledger_entry_id,
                    entry.work_unit_id,
                    entry.run_id,
                    entry.route_plan_id,
                    entry.result_envelope_id,
                    entry.verifier_report_id,
                    entry.account_snapshot_id,
                    entry.usage_source,
                    entry.cost_source,
                    entry.billable_cost_micros,
                    entry.entry_hash,
                    canonical_json_dumps(body),
                    created_at,
                ),
            )
            enqueue_event(
                self.conn,
                OutboxEventInput(
                    source="tokenbank.ledger",
                    type="usage_ledger_entry.recorded",
                    subject=f"usage_ledger_entries/{entry.usage_ledger_entry_id}",
                    run_id=entry.run_id,
                    work_unit_id=entry.work_unit_id,
                    body={
                        "usage_ledger_entry_id": entry.usage_ledger_entry_id,
                        "work_unit_id": entry.work_unit_id,
                        "run_id": entry.run_id,
                        "route_plan_id": entry.route_plan_id,
                        "result_envelope_id": entry.result_envelope_id,
                        "usage_source": entry.usage_source,
                        "cost_source": entry.cost_source,
                        "billable_cost_micros": entry.billable_cost_micros,
                        "entry_hash": entry.entry_hash,
                    },
                ),
            )
        return {"usage_ledger_entry": body, "entry_hash": entry.entry_hash}

    def list_entries(
        self,
        *,
        work_unit_id: str | None = None,
        run_id: str | None = None,
    ) -> list[dict[str, Any]]:
        where: list[str] = []
        params: list[str] = []
        if work_unit_id:
            where.append("work_unit_id = ?")
            params.append(work_unit_id)
        if run_id:
            where.append("run_id = ?")
            params.append(run_id)
        predicate = "" if not where else "WHERE " + " AND ".join(where)
        rows = self.conn.execute(
            f"""
            SELECT body_json, entry_hash, created_at
            FROM usage_ledger_entries
            {predicate}
            ORDER BY created_at DESC, usage_ledger_entry_id
            """,
            params,
        ).fetchall()
        return [
            {
                "usage_ledger_entry": json.loads(row["body_json"]),
                "entry_hash": row["entry_hash"],
                "created_at": row["created_at"],
            }
            for row in rows
        ]

    def get_entry(self, usage_ledger_entry_id: str) -> dict[str, Any] | None:
        row = self.conn.execute(
            """
            SELECT body_json, entry_hash, created_at
            FROM usage_ledger_entries
            WHERE usage_ledger_entry_id = ?
            """,
            (usage_ledger_entry_id,),
        ).fetchone()
        if row is None:
            return None
        return {
            "usage_ledger_entry": json.loads(row["body_json"]),
            "entry_hash": row["entry_hash"],
            "created_at": row["created_at"],
        }

    def _completed_context(self, work_unit_id: str) -> dict[str, Any]:
        work_unit_row = _required_row(
            self.conn,
            "SELECT * FROM work_units WHERE work_unit_id = ?",
            (work_unit_id,),
            f"work_unit not found: {work_unit_id}",
        )
        result_row = _required_row(
            self.conn,
            """
            SELECT *
            FROM result_envelopes
            WHERE work_unit_id = ?
              AND status = 'succeeded'
            ORDER BY created_at DESC
            LIMIT 1
            """,
            (work_unit_id,),
            f"succeeded result not found for work_unit: {work_unit_id}",
        )
        route_row = _required_row(
            self.conn,
            """
            SELECT *
            FROM route_plans
            WHERE work_unit_id = ?
            ORDER BY created_at DESC
            LIMIT 1
            """,
            (work_unit_id,),
            f"route_plan not found for work_unit: {work_unit_id}",
        )
        verifier_row = self.conn.execute(
            """
            SELECT *
            FROM verifier_reports
            WHERE result_envelope_id = ?
            ORDER BY created_at DESC
            LIMIT 1
            """,
            (result_row["result_envelope_id"],),
        ).fetchone()
        return {
            "work_unit_row": work_unit_row,
            "work_unit_body": json.loads(work_unit_row["body_json"]),
            "route_row": route_row,
            "route_body": json.loads(route_row["body_json"]),
            "result_row": result_row,
            "result_body": json.loads(result_row["body_json"]),
            "verifier_row": verifier_row,
            "verifier_body": (
                json.loads(verifier_row["body_json"])
                if verifier_row is not None
                else None
            ),
        }


def _build_usage_entry(
    *,
    context: dict[str, Any],
    account_snapshot_id: str | None,
    routebook_id: str,
    routebook_version: str,
) -> UsageLedgerEntry:
    work_unit_body = context["work_unit_body"]
    result_body = context["result_body"]
    route_body = context["route_body"]
    verifier_body = context["verifier_body"]
    usage_records = [
        item for item in result_body.get("usage_records", []) if isinstance(item, dict)
    ]
    input_units = sum(
        _non_negative_int(item.get("input_units")) for item in usage_records
    )
    output_units = sum(
        _non_negative_int(item.get("output_units")) for item in usage_records
    )
    estimated_cost = max(
        _non_negative_int(result_body.get("cost_estimate_micros")),
        sum(
            _non_negative_int(item.get("estimated_cost_micros"))
            for item in usage_records
        ),
    )
    actual_cost = max(
        _non_negative_int(result_body.get("actual_cost_micros")),
        sum(
            _non_negative_int(item.get("actual_cost_micros"))
            for item in usage_records
        ),
    )
    provider_reported = actual_cost > 0 or any(
        item.get("cost_source") == "measured" for item in usage_records
    )
    usage_source = "provider_response" if provider_reported else "estimate"
    cost_source = (
        "provider_reported"
        if provider_reported
        else "estimated"
        if estimated_cost > 0
        else "not_applicable"
    )
    route_plan_id = str(context["route_row"]["route_plan_id"])
    result_envelope_id = str(context["result_row"]["result_envelope_id"])
    verifier_report_id = (
        str(context["verifier_row"]["verifier_report_id"])
        if context["verifier_row"] is not None
        else None
    )
    seed = {
        "work_unit_id": work_unit_body["work_unit_id"],
        "result_envelope_id": result_envelope_id,
        "verifier_report_id": verifier_report_id,
        "account_snapshot_id": account_snapshot_id,
    }
    entry_id = "ule_" + canonical_json_hash(seed)[:24]
    payload_without_hash = {
        "usage_ledger_entry_id": entry_id,
        "work_unit_id": work_unit_body["work_unit_id"],
        "run_id": work_unit_body["run_id"],
        "route_plan_id": route_plan_id,
        "result_envelope_id": result_envelope_id,
        "verifier_report_id": verifier_report_id,
        "account_snapshot_id": account_snapshot_id,
        "routebook_id": routebook_id,
        "routebook_version": routebook_version,
        "capacity_node_id": result_body.get("capacity_node_id"),
        "capacity_profile_id": _capacity_profile_id(result_body, route_body),
        "backend_id": result_body.get("backend_id"),
        "provider_id": result_body.get("provider_id"),
        "model_id": result_body.get("model_id"),
        "estimated_input_tokens": input_units,
        "estimated_output_tokens": output_units,
        "estimated_total_tokens": input_units + output_units,
        "reported_input_tokens": input_units if provider_reported else None,
        "reported_output_tokens": output_units if provider_reported else None,
        "reported_total_tokens": input_units + output_units
        if provider_reported
        else None,
        "estimated_cost_micros": estimated_cost,
        "reported_cost_micros": actual_cost if provider_reported else None,
        "billable_cost_micros": actual_cost if provider_reported else estimated_cost,
        "usage_source": usage_source,
        "cost_source": cost_source,
        "verifier_recommendation": (
            verifier_body.get("recommendation")
            if isinstance(verifier_body, dict)
            else None
        ),
    }
    entry_hash = canonical_json_hash(payload_without_hash)
    return UsageLedgerEntry(
        **payload_without_hash,
        entry_hash=entry_hash,
    )


def _capacity_profile_id(
    result_body: dict[str, Any],
    route_body: dict[str, Any],
) -> str | None:
    capacity_node_id = result_body.get("capacity_node_id")
    if not isinstance(capacity_node_id, str) or not capacity_node_id:
        selected_id = route_body.get("selected_candidate_id")
        for candidate in route_body.get("candidates", []):
            if (
                isinstance(candidate, dict)
                and candidate.get("route_candidate_id") == selected_id
            ):
                capacity_node_id = candidate.get("capacity_node_id")
                break
    backend_id = result_body.get("backend_id")
    if not isinstance(backend_id, str) or not backend_id:
        return None
    return "cp_" + canonical_json_hash(
        {"capacity_node_id": capacity_node_id, "backend_id": backend_id}
    )[:24]


def _required_row(
    conn: sqlite3.Connection,
    sql: str,
    params: tuple[Any, ...],
    message: str,
) -> sqlite3.Row:
    row = conn.execute(sql, params).fetchone()
    if row is None:
        raise KeyError(message)
    return row


def _utc_text(value: datetime | None = None) -> str:
    current = value or datetime.now(UTC)
    normalized = current.astimezone(UTC) if current.tzinfo else current
    return normalized.isoformat().replace("+00:00", "Z")


def _non_negative_int(value: Any) -> int:
    if isinstance(value, bool):
        return 0
    if isinstance(value, int) and value >= 0:
        return value
    return 0
