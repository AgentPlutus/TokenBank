"""Local-first dashboard data and HTML rendering."""

from __future__ import annotations

import json
import sqlite3
from datetime import UTC, datetime
from html import escape
from typing import Any

from tokenbank.accounts import AccountRegistry
from tokenbank.audit import AuditReceiptRepository
from tokenbank.capacity.discovery import discover_capacity_nodes
from tokenbank.core.canonical import canonical_json_hash
from tokenbank.core.redaction import redact_sensitive_value
from tokenbank.ledger import UsageLedgerRepository

DASHBOARD_REDACTION_PROFILE = "local_dashboard_v1"


def dashboard_snapshot(
    conn: sqlite3.Connection,
    *,
    limit: int = 50,
) -> dict[str, Any]:
    """Build a redacted local dashboard snapshot from control-plane state."""
    accounts = [
        _redacted_account_snapshot(item)
        for item in AccountRegistry(conn).list_snapshots()
    ][:limit]
    usage_entries = [
        _redacted_usage_entry(item)
        for item in UsageLedgerRepository(conn).list_entries()
    ][:limit]
    audit_receipts = [
        _redacted_audit_receipt(item)
        for item in AuditReceiptRepository(conn).list_receipts()
    ][:limit]
    route_audits = _route_audits(conn, limit=limit)
    capacity_nodes = discover_capacity_nodes(conn)
    snapshot = {
        "status": "ok",
        "dashboard": "local_usage_account_audit",
        "redaction_profile": DASHBOARD_REDACTION_PROFILE,
        "generated_at": _utc_text(),
        "summary": _summary(
            accounts=accounts,
            usage_entries=usage_entries,
            audit_receipts=audit_receipts,
            capacity_nodes=capacity_nodes,
        ),
        "accounts": accounts,
        "usage_ledger": usage_entries,
        "route_audits": route_audits,
        "audit_receipts": audit_receipts,
        "capacity_health": _capacity_health(capacity_nodes),
        "privacy_boundary": {
            "local_first": True,
            "cloud_upload_required": False,
            "raw_credentials_rendered": False,
            "raw_prompts_rendered": False,
            "raw_outputs_rendered": False,
            "redacted_export_supported": True,
            "reason_codes": [
                "dashboard_reads_local_control_plane_state",
                "credential_refs_reduced_to_kind_and_status",
                "receipts_render_ids_and_hashes_only",
            ],
        },
    }
    return _redact_secret_like_strings(snapshot)


def dashboard_export(conn: sqlite3.Connection, *, limit: int = 50) -> dict[str, Any]:
    """Return a user-controlled redacted dashboard export."""
    snapshot = dashboard_snapshot(conn, limit=limit)
    payload = {
        "status": "ok",
        "export_type": "tokenbank.local_dashboard_redacted.v1",
        "redaction_profile": DASHBOARD_REDACTION_PROFILE,
        "snapshot": snapshot,
    }
    payload["export_hash"] = canonical_json_hash(payload)
    return payload


def render_dashboard_html(snapshot: dict[str, Any]) -> str:
    """Render a dependency-free local dashboard HTML page."""
    summary = snapshot["summary"]
    account_rows = "".join(_account_row(account) for account in snapshot["accounts"])
    usage_rows = "".join(_usage_row(entry) for entry in snapshot["usage_ledger"])
    route_rows = "".join(_route_row(route) for route in snapshot["route_audits"])
    receipt_rows = "".join(_receipt_row(item) for item in snapshot["audit_receipts"])
    capacity_rows = "".join(_capacity_row(item) for item in snapshot["capacity_health"])
    return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>TokenBank Local Dashboard</title>
  <style>{_CSS}</style>
</head>
<body>
  <header class="topbar">
    <div>
      <p class="eyebrow">TokenBank Phase 0</p>
      <h1>Local Usage Account Audit</h1>
    </div>
    <div class="status">
      <span>Local-first</span>
      <span>Redacted</span>
      <span>{_text(snapshot["generated_at"])}</span>
    </div>
  </header>
  <main>
    <section class="metrics" aria-label="Summary">
      {_metric("Accounts", summary["account_count"])}
      {_metric("Configured", summary["configured_account_count"])}
      {_metric("Usage Rows", summary["usage_entry_count"])}
      {_metric("Receipts", summary["audit_receipt_count"])}
      {_metric("Billable Micros", summary["billable_cost_micros"])}
      {_metric("Provider Micros", summary["provider_reported_cost_micros"])}
    </section>
    <section class="band two">
      <article>
        <h2>Accounts</h2>
        <table>
          <thead><tr><th>Provider</th><th>Label</th><th>Status</th>
          <th>Secret Ref</th><th>Balance</th><th>Source</th>
          <th>Models</th></tr></thead>
          <tbody>{account_rows or _empty_row(7)}</tbody>
        </table>
      </article>
      <article>
        <h2>Capacity Health</h2>
        <table>
          <thead><tr><th>Node</th><th>Type</th><th>Status</th><th>Backend</th><th>Tasks</th></tr></thead>
          <tbody>{capacity_rows or _empty_row(5)}</tbody>
        </table>
      </article>
    </section>
    <section class="band">
      <article>
        <h2>Usage Ledger</h2>
        <table>
          <thead><tr><th>WorkUnit</th><th>RoutePlan</th><th>Usage</th><th>Cost</th><th>Backend</th><th>Verifier</th></tr></thead>
          <tbody>{usage_rows or _empty_row(6)}</tbody>
        </table>
      </article>
    </section>
    <section class="band">
      <article>
        <h2>Route Audit</h2>
        <table>
          <thead><tr><th>WorkUnit</th><th>Task</th><th>Status</th>
          <th>Selected Backend</th><th>Verifier</th><th>Receipt</th></tr></thead>
          <tbody>{route_rows or _empty_row(6)}</tbody>
        </table>
      </article>
    </section>
    <section class="band">
      <article>
        <h2>Audit Receipts</h2>
        <table>
          <thead><tr><th>Receipt</th><th>WorkUnit</th><th>Status</th>
          <th>Result Hash</th><th>Receipt Hash</th></tr></thead>
          <tbody>{receipt_rows or _empty_row(5)}</tbody>
        </table>
      </article>
    </section>
    <section class="privacy">
      <h2>Privacy Boundary</h2>
      <p>Dashboard responses are generated from local control-plane state.
      Raw credentials, raw prompts, and raw outputs are not rendered.</p>
      <a href="/export.json">Download redacted export</a>
    </section>
  </main>
</body>
</html>
"""


def _summary(
    *,
    accounts: list[dict[str, Any]],
    usage_entries: list[dict[str, Any]],
    audit_receipts: list[dict[str, Any]],
    capacity_nodes: list[dict[str, Any]],
) -> dict[str, Any]:
    return {
        "account_count": len(accounts),
        "configured_account_count": sum(
            1 for account in accounts if account.get("status") == "configured"
        ),
        "usage_entry_count": len(usage_entries),
        "audit_receipt_count": len(audit_receipts),
        "capacity_node_count": len(capacity_nodes),
        "billable_cost_micros": sum(
            _int(entry.get("billable_cost_micros")) for entry in usage_entries
        ),
        "estimated_cost_micros": sum(
            _int(entry.get("estimated_cost_micros")) for entry in usage_entries
        ),
        "provider_reported_cost_micros": sum(
            _int(entry.get("reported_cost_micros")) for entry in usage_entries
        ),
    }


def _redacted_account_snapshot(item: dict[str, Any]) -> dict[str, Any]:
    account = dict(item["account_snapshot"])
    secret_ref = account.pop("secret_ref", None)
    account["secret_ref_present"] = bool(secret_ref)
    account["secret_ref_kind"] = _secret_ref_kind(secret_ref)
    account["snapshot_hash"] = item["snapshot_hash"]
    return account


def _redacted_usage_entry(item: dict[str, Any]) -> dict[str, Any]:
    entry = dict(item["usage_ledger_entry"])
    entry["entry_hash"] = item["entry_hash"]
    return entry


def _redacted_audit_receipt(item: dict[str, Any]) -> dict[str, Any]:
    receipt = dict(item["audit_receipt"])
    receipt["receipt_hash"] = item["receipt_hash"]
    return receipt


def _route_audits(conn: sqlite3.Connection, *, limit: int) -> list[dict[str, Any]]:
    rows = conn.execute(
        """
        SELECT
          wu.work_unit_id,
          wu.run_id,
          wu.status,
          wu.task_type,
          wu.task_level,
          rp.route_plan_id,
          rp.body_json AS route_body_json,
          re.result_envelope_id,
          vr.verifier_report_id,
          vr.recommendation AS verifier_recommendation,
          ar.audit_receipt_id,
          ar.receipt_hash
        FROM work_units wu
        LEFT JOIN route_plans rp
          ON rp.work_unit_id = wu.work_unit_id
        LEFT JOIN result_envelopes re
          ON re.work_unit_id = wu.work_unit_id
        LEFT JOIN verifier_reports vr
          ON vr.result_envelope_id = re.result_envelope_id
        LEFT JOIN audit_receipts ar
          ON ar.result_envelope_id = re.result_envelope_id
        ORDER BY wu.created_at DESC
        LIMIT ?
        """,
        (limit,),
    ).fetchall()
    audits: list[dict[str, Any]] = []
    for row in rows:
        route_body = _json_object(row["route_body_json"])
        selected = _selected_candidate(route_body)
        audits.append(
            {
                "work_unit_id": row["work_unit_id"],
                "run_id": row["run_id"],
                "status": row["status"],
                "task_type": row["task_type"],
                "task_level": row["task_level"],
                "route_plan_id": row["route_plan_id"],
                "route_plan_hash": canonical_json_hash(route_body)
                if route_body
                else None,
                "selected_candidate_id": route_body.get("selected_candidate_id"),
                "selected_backend_id": selected.get("backend_id"),
                "selected_backend_class": selected.get("backend_class"),
                "selected_capacity_node_id": selected.get("capacity_node_id"),
                "verifier_report_id": row["verifier_report_id"],
                "verifier_recommendation": row["verifier_recommendation"],
                "audit_receipt_id": row["audit_receipt_id"],
                "receipt_hash": row["receipt_hash"],
            }
        )
    return audits


def _capacity_health(capacity_nodes: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [
        {
            "capacity_node_id": node["capacity_node_id"],
            "node_type": node["node_type"],
            "status": node["status"],
            "backend_id": node.get("backend_id"),
            "backend_classes": node.get("backend_classes", []),
            "task_types": node.get("task_types", []),
            "health": node.get("health", {}),
            "manifest_hash": node.get("manifest_hash"),
        }
        for node in capacity_nodes
    ]


def _selected_candidate(route_body: dict[str, Any]) -> dict[str, Any]:
    selected_id = route_body.get("selected_candidate_id")
    for candidate in route_body.get("candidates", []):
        if (
            isinstance(candidate, dict)
            and candidate.get("route_candidate_id") == selected_id
        ):
            return candidate
    return {}


def _secret_ref_kind(value: Any) -> str | None:
    if not isinstance(value, str) or ":" not in value:
        return None
    return value.split(":", 1)[0]


def _json_object(value: Any) -> dict[str, Any]:
    if not isinstance(value, str) or not value:
        return {}
    parsed = json.loads(value)
    return parsed if isinstance(parsed, dict) else {}


def _redact_secret_like_strings(value: Any) -> Any:
    if isinstance(value, dict):
        return {
            key: _redact_secret_like_strings(nested)
            for key, nested in value.items()
        }
    if isinstance(value, list):
        return [_redact_secret_like_strings(item) for item in value]
    if isinstance(value, str):
        return redact_sensitive_value(value)
    return value


def _account_row(account: dict[str, Any]) -> str:
    balance = account.get("balance") or {}
    return (
        "<tr>"
        f"<td>{_text(account.get('provider'))}</td>"
        f"<td>{_text(account.get('account_label'))}</td>"
        f"<td>{_badge(account.get('status'))}</td>"
        f"<td>{_text(account.get('secret_ref_kind') or 'none')} / "
        f"{_text(account.get('secret_ref_status'))}</td>"
        f"<td>{_text(balance.get('available_micros'))}</td>"
        f"<td>{_text(balance.get('source'))} "
        f"({_text(balance.get('confidence'))})</td>"
        f"<td>{_text(', '.join(account.get('visible_models') or []))}</td>"
        "</tr>"
    )


def _usage_row(entry: dict[str, Any]) -> str:
    return (
        "<tr>"
        f"<td>{_code(entry.get('work_unit_id'))}</td>"
        f"<td>{_code(entry.get('route_plan_id'))}</td>"
        f"<td>{_text(entry.get('usage_source'))}: "
        f"{_text(entry.get('estimated_total_tokens'))}</td>"
        f"<td>{_text(entry.get('cost_source'))}: "
        f"{_text(entry.get('billable_cost_micros'))}</td>"
        f"<td>{_text(entry.get('backend_id'))}</td>"
        f"<td>{_text(entry.get('verifier_recommendation'))}</td>"
        "</tr>"
    )


def _route_row(route: dict[str, Any]) -> str:
    return (
        "<tr>"
        f"<td>{_code(route.get('work_unit_id'))}</td>"
        f"<td>{_text(route.get('task_type'))} / {_text(route.get('task_level'))}</td>"
        f"<td>{_badge(route.get('status'))}</td>"
        f"<td>{_text(route.get('selected_backend_id'))}</td>"
        f"<td>{_text(route.get('verifier_recommendation'))}</td>"
        f"<td>{_hash(route.get('receipt_hash'))}</td>"
        "</tr>"
    )


def _receipt_row(receipt: dict[str, Any]) -> str:
    return (
        "<tr>"
        f"<td>{_code(receipt.get('audit_receipt_id'))}</td>"
        f"<td>{_code(receipt.get('work_unit_id'))}</td>"
        f"<td>{_badge(receipt.get('status'))}</td>"
        f"<td>{_hash(receipt.get('result_hash'))}</td>"
        f"<td>{_hash(receipt.get('receipt_hash'))}</td>"
        "</tr>"
    )


def _capacity_row(item: dict[str, Any]) -> str:
    return (
        "<tr>"
        f"<td>{_code(item.get('capacity_node_id'))}</td>"
        f"<td>{_text(item.get('node_type'))}</td>"
        f"<td>{_badge(item.get('status'))}</td>"
        f"<td>{_text(item.get('backend_id'))}</td>"
        f"<td>{_text(', '.join(item.get('task_types') or []))}</td>"
        "</tr>"
    )


def _metric(label: str, value: Any) -> str:
    return (
        '<article class="metric">'
        f"<span>{_text(label)}</span>"
        f"<strong>{_text(value)}</strong>"
        "</article>"
    )


def _empty_row(colspan: int) -> str:
    return f'<tr><td colspan="{colspan}" class="empty">No local data yet.</td></tr>'


def _badge(value: Any) -> str:
    return f'<span class="badge">{_text(value)}</span>'


def _code(value: Any) -> str:
    return f"<code>{_text(value)}</code>"


def _hash(value: Any) -> str:
    text = "" if value is None else str(value)
    return f"<code>{escape(text[:12])}</code>" if text else ""


def _text(value: Any) -> str:
    if value is None:
        return ""
    return escape(str(value))


def _int(value: Any) -> int:
    if isinstance(value, bool):
        return 0
    if isinstance(value, int) and value >= 0:
        return value
    return 0


def _utc_text() -> str:
    return datetime.now(UTC).isoformat().replace("+00:00", "Z")


_CSS = """
:root {
  color-scheme: light;
  --page: #f7f8fa;
  --surface: #ffffff;
  --surface-subtle: #f8fafc;
  --border: #dfe3ea;
  --border-subtle: #edf0f4;
  --text: #1c2430;
  --text-muted: #617086;
  --text-soft: #526175;
  --accent: #075985;
  font-family: Inter, ui-sans-serif, system-ui, -apple-system,
    BlinkMacSystemFont, "Segoe UI", sans-serif;
  background: var(--page);
  color: var(--text);
}
body {
  margin: 0;
  min-width: 320px;
}
.topbar {
  display: flex;
  align-items: flex-end;
  justify-content: space-between;
  gap: 24px;
  padding: 28px 32px 18px;
  background: var(--surface);
  border-bottom: 1px solid var(--border);
}
.eyebrow {
  margin: 0 0 4px;
  color: var(--text-muted);
  font-size: 12px;
  font-weight: 700;
  letter-spacing: 0;
  text-transform: uppercase;
}
h1, h2 {
  margin: 0;
  letter-spacing: 0;
}
h1 {
  font-size: 28px;
  line-height: 1.15;
}
h2 {
  font-size: 16px;
  margin-bottom: 12px;
}
.status {
  display: flex;
  flex-wrap: wrap;
  justify-content: flex-end;
  gap: 8px;
}
.status span, .badge {
  border: 1px solid #cbd3df;
  background: var(--surface-subtle);
  border-radius: 999px;
  padding: 4px 8px;
  color: #344258;
  font-size: 12px;
  white-space: nowrap;
}
main {
  padding: 18px 32px 32px;
}
.metrics {
  display: grid;
  grid-template-columns: repeat(6, minmax(120px, 1fr));
  gap: 10px;
  margin-bottom: 16px;
}
.metric, article, .privacy {
  background: var(--surface);
  border: 1px solid var(--border);
  border-radius: 8px;
}
.metric {
  padding: 14px 16px;
}
.metric span {
  display: block;
  color: var(--text-muted);
  font-size: 12px;
}
.metric strong {
  display: block;
  margin-top: 4px;
  font-size: 22px;
}
.band {
  display: grid;
  gap: 16px;
  margin-bottom: 16px;
}
.band.two {
  grid-template-columns: minmax(0, 1fr) minmax(0, 1fr);
}
article, .privacy {
  overflow: hidden;
  padding: 16px;
}
table {
  width: 100%;
  border-collapse: collapse;
  table-layout: fixed;
}
th, td {
  border-top: 1px solid var(--border-subtle);
  padding: 9px 8px;
  text-align: left;
  vertical-align: top;
  font-size: 13px;
  overflow-wrap: anywhere;
}
th {
  color: var(--text-muted);
  font-size: 11px;
  text-transform: uppercase;
  letter-spacing: 0;
}
code {
  font-family: "SFMono-Regular", Consolas, monospace;
  font-size: 12px;
}
.empty {
  color: #7c8798;
}
.privacy {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 16px;
}
.privacy p {
  margin: 6px 0 0;
  color: var(--text-soft);
}
.privacy a {
  color: var(--accent);
  font-weight: 700;
  text-decoration: none;
}
@media (max-width: 920px) {
  .topbar, .privacy {
    display: block;
  }
  .status {
    justify-content: flex-start;
    margin-top: 12px;
  }
  main, .topbar {
    padding-left: 16px;
    padding-right: 16px;
  }
  .metrics, .band.two {
    grid-template-columns: 1fr;
  }
}
"""
