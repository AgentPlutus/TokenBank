"""Local account snapshot registry."""

from __future__ import annotations

import json
import sqlite3
from datetime import UTC, datetime
from typing import Any

from tokenbank.core.canonical import canonical_json_dumps, canonical_json_hash
from tokenbank.db.transactions import transaction
from tokenbank.events.outbox import OutboxEventInput, enqueue_event
from tokenbank.models.account_snapshot import (
    AccountSnapshot,
    AccountSnapshotStatus,
    BalanceSnapshot,
    BalanceSnapshotSource,
    RateLimitSnapshot,
)


class AccountRegistry:
    """Persist host-local account state without raw provider credentials."""

    def __init__(self, conn: sqlite3.Connection):
        self.conn = conn

    def upsert_snapshot(self, snapshot: AccountSnapshot) -> dict[str, Any]:
        """Create or update one account snapshot and emit an outbox event."""
        body = snapshot.model_dump(mode="json")
        snapshot_hash = canonical_json_hash(body)
        captured_at = _utc_text(snapshot.captured_at)
        with transaction(self.conn):
            self.conn.execute(
                """
                INSERT INTO account_snapshots (
                  account_snapshot_id,
                  provider,
                  account_label,
                  status,
                  secret_ref,
                  snapshot_hash,
                  body_json,
                  created_at,
                  updated_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(account_snapshot_id) DO UPDATE SET
                  provider = excluded.provider,
                  account_label = excluded.account_label,
                  status = excluded.status,
                  secret_ref = excluded.secret_ref,
                  snapshot_hash = excluded.snapshot_hash,
                  body_json = excluded.body_json,
                  updated_at = excluded.updated_at
                """,
                (
                    snapshot.account_snapshot_id,
                    snapshot.provider,
                    snapshot.account_label,
                    snapshot.status,
                    snapshot.secret_ref,
                    snapshot_hash,
                    canonical_json_dumps(body),
                    captured_at,
                    captured_at,
                ),
            )
            enqueue_event(
                self.conn,
                OutboxEventInput(
                    source="tokenbank.accounts",
                    type="account_snapshot.upserted",
                    subject=f"account_snapshots/{snapshot.account_snapshot_id}",
                    body={
                        "account_snapshot_id": snapshot.account_snapshot_id,
                        "provider": snapshot.provider,
                        "account_label": snapshot.account_label,
                        "status": snapshot.status,
                        "secret_ref_status": snapshot.secret_ref_status,
                        "snapshot_hash": snapshot_hash,
                    },
                ),
            )
        return {
            "account_snapshot": body,
            "snapshot_hash": snapshot_hash,
        }

    def get_snapshot(self, account_snapshot_id: str) -> dict[str, Any] | None:
        row = self.conn.execute(
            """
            SELECT body_json, snapshot_hash, created_at, updated_at
            FROM account_snapshots
            WHERE account_snapshot_id = ?
            """,
            (account_snapshot_id,),
        ).fetchone()
        return None if row is None else _snapshot_response(row)

    def list_snapshots(
        self,
        *,
        provider: str | None = None,
        status: str | None = None,
    ) -> list[dict[str, Any]]:
        where: list[str] = []
        params: list[str] = []
        if provider:
            where.append("provider = ?")
            params.append(provider)
        if status:
            where.append("status = ?")
            params.append(status)
        predicate = "" if not where else "WHERE " + " AND ".join(where)
        rows = self.conn.execute(
            f"""
            SELECT body_json, snapshot_hash, created_at, updated_at
            FROM account_snapshots
            {predicate}
            ORDER BY provider, account_label, updated_at DESC
            """,
            params,
        ).fetchall()
        return [_snapshot_response(row) for row in rows]

    def refresh_local(self) -> dict[str, Any]:
        """Return local snapshots; WP-LEDGER1 performs no provider API calls."""
        snapshots = self.list_snapshots()
        return {
            "status": "ok",
            "provider_calls_executed": False,
            "snapshot_count": len(snapshots),
            "snapshots": snapshots,
            "caveats": [
                "WP-LEDGER1 refresh is local-only; provider API balance sync "
                "is deferred."
            ],
        }


def build_manual_account_snapshot(
    *,
    provider: str,
    account_label: str,
    secret_ref: str | None,
    status: AccountSnapshotStatus = "configured",
    balance_source: BalanceSnapshotSource = "manual",
    available_micros: int | None = None,
    monthly_spend_micros: int | None = None,
    monthly_budget_micros: int | None = None,
    requests_per_minute: int | None = None,
    tokens_per_minute: int | None = None,
    visible_models: list[str] | None = None,
) -> AccountSnapshot:
    seed = {
        "provider": provider,
        "account_label": account_label,
        "secret_ref": secret_ref or "none:",
    }
    snapshot_id = f"acct_{canonical_json_hash(seed)[:24]}"
    has_balance = any(
        value is not None
        for value in (available_micros, monthly_spend_micros, monthly_budget_micros)
    )
    has_rate_limits = requests_per_minute is not None or tokens_per_minute is not None
    return AccountSnapshot(
        account_snapshot_id=snapshot_id,
        provider=provider,
        account_label=account_label,
        status=status,
        secret_ref=secret_ref,
        secret_ref_status="present" if secret_ref else "missing",
        raw_secret_present=False,
        balance=BalanceSnapshot(
            source=balance_source,
            available_micros=available_micros,
            monthly_spend_micros=monthly_spend_micros,
            monthly_budget_micros=monthly_budget_micros,
            confidence=0.7 if balance_source == "manual" else 0.8,
        )
        if has_balance
        else None,
        rate_limits=RateLimitSnapshot(
            requests_per_minute=requests_per_minute,
            tokens_per_minute=tokens_per_minute,
            source="manual",
        )
        if has_rate_limits
        else None,
        visible_models=visible_models or [],
        reason_codes=["manual_local_snapshot"],
    )


def _snapshot_response(row: sqlite3.Row) -> dict[str, Any]:
    return {
        "account_snapshot": json.loads(row["body_json"]),
        "snapshot_hash": row["snapshot_hash"],
        "created_at": row["created_at"],
        "updated_at": row["updated_at"],
    }


def _utc_text(value: datetime | None = None) -> str:
    current = value or datetime.now(UTC)
    normalized = current.astimezone(UTC) if current.tzinfo else current
    return normalized.isoformat().replace("+00:00", "Z")
