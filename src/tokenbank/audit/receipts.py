"""Hash-backed audit receipts."""

from __future__ import annotations

import json
import sqlite3
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from tokenbank.core.canonical import canonical_json_dumps, canonical_json_hash
from tokenbank.db.transactions import transaction
from tokenbank.events.outbox import OutboxEventInput, enqueue_event
from tokenbank.ledger.usage import UsageLedgerRepository
from tokenbank.models.audit_receipt import AuditReceipt
from tokenbank.models.common import VerifierRecommendation
from tokenbank.routebook.v1_loader import load_routebook_v1_dir

ACCEPTED_RECOMMENDATIONS: set[VerifierRecommendation] = {
    "accept",
    "accept_with_warning",
}


class AuditReceiptRepository:
    """Create redacted audit receipts for accepted WorkUnit results."""

    def __init__(self, conn: sqlite3.Connection):
        self.conn = conn

    def create_for_work_unit(
        self,
        *,
        work_unit_id: str,
        usage_ledger_entry_id: str | None = None,
        account_snapshot_id: str | None = None,
        routebook_v1_dir: str | Path = "packs/base-routing/routebook",
    ) -> dict[str, Any]:
        context = self._accepted_context(work_unit_id)
        usage_entry = self._ensure_usage_entry(
            work_unit_id=work_unit_id,
            usage_ledger_entry_id=usage_ledger_entry_id,
            account_snapshot_id=account_snapshot_id,
            routebook_v1_dir=routebook_v1_dir,
        )
        routebook = load_routebook_v1_dir(routebook_v1_dir)
        existing_id = _receipt_id(
            result_envelope_id=context["result_row"]["result_envelope_id"],
            usage_ledger_entry_id=(
                usage_entry["usage_ledger_entry"]["usage_ledger_entry_id"]
                if usage_entry is not None
                else None
            ),
        )
        existing = self.get_receipt(existing_id)
        if existing is not None:
            return existing

        receipt = _build_receipt(
            context=context,
            usage_entry=usage_entry,
            previous_receipt_hash=self._previous_receipt_hash(
                result_envelope_id=context["result_row"]["result_envelope_id"]
            ),
            routebook_id=routebook.routebook_id,
            routebook_version=routebook.version,
        )
        return self.insert_receipt(receipt)

    def insert_receipt(self, receipt: AuditReceipt) -> dict[str, Any]:
        body = receipt.model_dump(mode="json")
        created_at = _utc_text(receipt.created_at)
        with transaction(self.conn):
            self.conn.execute(
                """
                INSERT INTO audit_receipts (
                  audit_receipt_id,
                  work_unit_id,
                  run_id,
                  route_plan_id,
                  result_envelope_id,
                  verifier_report_id,
                  usage_ledger_entry_id,
                  receipt_hash,
                  previous_receipt_hash,
                  body_json,
                  created_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    receipt.audit_receipt_id,
                    receipt.work_unit_id,
                    receipt.run_id,
                    receipt.route_plan_id,
                    receipt.result_envelope_id,
                    receipt.verifier_report_id,
                    receipt.usage_ledger_entry_id,
                    receipt.receipt_hash,
                    receipt.previous_receipt_hash,
                    canonical_json_dumps(body),
                    created_at,
                ),
            )
            enqueue_event(
                self.conn,
                OutboxEventInput(
                    source="tokenbank.audit",
                    type="audit_receipt.created",
                    subject=f"audit_receipts/{receipt.audit_receipt_id}",
                    run_id=receipt.run_id,
                    work_unit_id=receipt.work_unit_id,
                    assignment_id=receipt.assignment_id,
                    body={
                        "audit_receipt_id": receipt.audit_receipt_id,
                        "work_unit_id": receipt.work_unit_id,
                        "run_id": receipt.run_id,
                        "route_plan_id": receipt.route_plan_id,
                        "result_envelope_id": receipt.result_envelope_id,
                        "verifier_report_id": receipt.verifier_report_id,
                        "usage_ledger_entry_id": receipt.usage_ledger_entry_id,
                        "receipt_hash": receipt.receipt_hash,
                        "previous_receipt_hash": receipt.previous_receipt_hash,
                        "redaction_profile": receipt.redaction_profile,
                    },
                ),
            )
        return {"audit_receipt": body, "receipt_hash": receipt.receipt_hash}

    def get_receipt(self, audit_receipt_id: str) -> dict[str, Any] | None:
        row = self.conn.execute(
            """
            SELECT body_json, receipt_hash, created_at
            FROM audit_receipts
            WHERE audit_receipt_id = ?
            """,
            (audit_receipt_id,),
        ).fetchone()
        if row is None:
            return None
        return {
            "audit_receipt": json.loads(row["body_json"]),
            "receipt_hash": row["receipt_hash"],
            "created_at": row["created_at"],
        }

    def list_receipts(
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
            SELECT body_json, receipt_hash, created_at
            FROM audit_receipts
            {predicate}
            ORDER BY created_at DESC, audit_receipt_id
            """,
            params,
        ).fetchall()
        return [
            {
                "audit_receipt": json.loads(row["body_json"]),
                "receipt_hash": row["receipt_hash"],
                "created_at": row["created_at"],
            }
            for row in rows
        ]

    def _accepted_context(self, work_unit_id: str) -> dict[str, Any]:
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
        verifier_row = _required_row(
            self.conn,
            """
            SELECT *
            FROM verifier_reports
            WHERE result_envelope_id = ?
            ORDER BY created_at DESC
            LIMIT 1
            """,
            (result_row["result_envelope_id"],),
            f"verifier report not found for work_unit: {work_unit_id}",
        )
        verifier_body = json.loads(verifier_row["body_json"])
        recommendation = verifier_body.get("recommendation")
        if recommendation not in ACCEPTED_RECOMMENDATIONS:
            raise ValueError(
                "audit receipt requires verifier recommendation accept "
                "or accept_with_warning"
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
        assignment_row = _required_row(
            self.conn,
            """
            SELECT *
            FROM assignments
            WHERE assignment_id = ?
            LIMIT 1
            """,
            (result_row["assignment_id"],),
            f"assignment not found for work_unit: {work_unit_id}",
        )
        return {
            "work_unit_row": work_unit_row,
            "work_unit_body": json.loads(work_unit_row["body_json"]),
            "route_row": route_row,
            "route_body": json.loads(route_row["body_json"]),
            "assignment_row": assignment_row,
            "assignment_body": json.loads(assignment_row["body_json"]),
            "result_row": result_row,
            "result_body": json.loads(result_row["body_json"]),
            "verifier_row": verifier_row,
            "verifier_body": verifier_body,
        }

    def _ensure_usage_entry(
        self,
        *,
        work_unit_id: str,
        usage_ledger_entry_id: str | None,
        account_snapshot_id: str | None,
        routebook_v1_dir: str | Path,
    ) -> dict[str, Any] | None:
        ledger = UsageLedgerRepository(self.conn)
        if usage_ledger_entry_id is not None:
            entry = ledger.get_entry(usage_ledger_entry_id)
            if entry is None:
                raise KeyError(f"usage ledger entry not found: {usage_ledger_entry_id}")
            return entry
        entries = ledger.list_entries(work_unit_id=work_unit_id)
        if entries:
            latest = entries[0]
            latest_account = latest["usage_ledger_entry"].get("account_snapshot_id")
            if account_snapshot_id is None or latest_account == account_snapshot_id:
                return latest
        return ledger.record_for_work_unit(
            work_unit_id=work_unit_id,
            account_snapshot_id=account_snapshot_id,
            routebook_v1_dir=routebook_v1_dir,
        )

    def _previous_receipt_hash(self, *, result_envelope_id: str) -> str | None:
        row = self.conn.execute(
            """
            SELECT receipt_hash
            FROM audit_receipts
            WHERE result_envelope_id != ?
            ORDER BY created_at DESC
            LIMIT 1
            """,
            (result_envelope_id,),
        ).fetchone()
        return None if row is None else str(row["receipt_hash"])


def _build_receipt(
    *,
    context: dict[str, Any],
    usage_entry: dict[str, Any] | None,
    previous_receipt_hash: str | None,
    routebook_id: str,
    routebook_version: str,
) -> AuditReceipt:
    work_unit_body = context["work_unit_body"]
    route_body = context["route_body"]
    assignment_body = context["assignment_body"]
    result_body = context["result_body"]
    verifier_body = context["verifier_body"]
    usage_body = usage_entry["usage_ledger_entry"] if usage_entry is not None else None
    audit_receipt_id = _receipt_id(
        result_envelope_id=result_body["result_envelope_id"],
        usage_ledger_entry_id=(
            usage_body["usage_ledger_entry_id"] if usage_body is not None else None
        ),
    )
    recommendation = verifier_body["recommendation"]
    status = "accepted" if recommendation == "accept" else "accepted_with_warning"
    payload_without_hash = {
        "audit_receipt_id": audit_receipt_id,
        "work_unit_id": work_unit_body["work_unit_id"],
        "run_id": work_unit_body["run_id"],
        "route_plan_id": route_body["route_plan_id"],
        "assignment_id": assignment_body["assignment_id"],
        "result_envelope_id": result_body["result_envelope_id"],
        "verifier_report_id": verifier_body["verifier_report_id"],
        "usage_ledger_entry_id": (
            usage_body["usage_ledger_entry_id"] if usage_body is not None else None
        ),
        "routebook_id": routebook_id,
        "routebook_version": routebook_version,
        "status": status,
        "work_unit_hash": canonical_json_hash(work_unit_body),
        "route_plan_hash": canonical_json_hash(route_body),
        "assignment_hash": canonical_json_hash(assignment_body),
        "result_hash": result_body["result_hash"],
        "result_envelope_hash": canonical_json_hash(result_body),
        "verifier_report_hash": canonical_json_hash(verifier_body),
        "usage_ledger_entry_hash": (
            usage_body["entry_hash"] if usage_body is not None else None
        ),
        "task_analysis_hash": None,
        "task_profile_hash": None,
        "previous_receipt_hash": previous_receipt_hash,
        "redaction_profile": "ids_and_hashes_only",
        "reason_codes": [
            "hash_chain_work_unit_to_verifier_report",
            "raw_input_output_and_credentials_excluded",
        ],
    }
    receipt_hash = canonical_json_hash(payload_without_hash)
    return AuditReceipt(
        **payload_without_hash,
        receipt_hash=receipt_hash,
    )


def _receipt_id(
    *,
    result_envelope_id: str,
    usage_ledger_entry_id: str | None,
) -> str:
    return "ar_" + canonical_json_hash(
        {
            "result_envelope_id": result_envelope_id,
            "usage_ledger_entry_id": usage_ledger_entry_id,
        }
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
