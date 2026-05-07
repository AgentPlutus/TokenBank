from __future__ import annotations

import json
from pathlib import Path

from fastapi.testclient import TestClient
from typer.testing import CliRunner

from tokenbank.cli.main import app
from tokenbank.dashboard.app import create_dashboard_app
from tokenbank.db.bootstrap import initialize_database
from tokenbank.demo.private_capacity import PrivateCapacityDemoRunner
from tokenbank.host_adapter import HostAdapterCore

REPO_ROOT = Path(__file__).resolve().parents[2]
HOST_HEADERS = {"Authorization": "Bearer tbk_h_dashboard"}
SECRET_REF = "keychain:tokenbank/openai/personal"


def test_dashboard_snapshot_redacts_secret_refs_and_payloads(
    tmp_path: Path,
) -> None:
    db_path, work_unit_id = _seed_dashboard_db(tmp_path)
    conn = initialize_database(db_path)
    try:
        from tokenbank.dashboard.views import dashboard_snapshot

        snapshot = dashboard_snapshot(conn)
    finally:
        conn.close()

    serialized = json.dumps(snapshot, sort_keys=True)
    assert snapshot["summary"]["account_count"] == 1
    assert snapshot["summary"]["usage_entry_count"] == 1
    assert snapshot["summary"]["audit_receipt_count"] == 1
    assert snapshot["accounts"][0]["secret_ref_kind"] == "keychain"
    assert snapshot["accounts"][0]["secret_ref_status"] == "present"
    assert SECRET_REF not in serialized
    assert "https://example.com/status" not in serialized
    assert '"output":' not in serialized
    assert work_unit_id in serialized


def test_dashboard_api_requires_host_auth_and_returns_redacted_data(
    tmp_path: Path,
) -> None:
    db_path, _work_unit_id = _seed_dashboard_db(tmp_path)
    api = create_dashboard_app(config_dir=REPO_ROOT / "config", db_path=db_path)
    with TestClient(api) as client:
        html = client.get("/")
        summary = client.get("/summary.json")
        export = client.get("/export.json")

    assert html.status_code == 200
    assert "Local Usage Account Audit" in html.text
    assert SECRET_REF not in html.text
    assert summary.status_code == 200
    assert summary.json()["redaction_profile"] == "local_dashboard_v1"
    assert export.status_code == 200
    assert export.json()["export_hash"]


def test_control_plane_dashboard_router_is_host_authenticated(
    tmp_path: Path,
) -> None:
    db_path, _work_unit_id = _seed_dashboard_db(tmp_path)
    from tokenbank.app.api import create_app

    api = create_app(config_dir=REPO_ROOT / "config", db_path=db_path)
    with TestClient(api) as client:
        unauthenticated = client.get("/v0/dashboard/summary")
        authenticated = client.get("/v0/dashboard/summary", headers=HOST_HEADERS)

    assert unauthenticated.status_code == 401
    assert authenticated.status_code == 200
    assert authenticated.json()["summary"]["audit_receipt_count"] == 1
    assert SECRET_REF not in json.dumps(authenticated.json(), sort_keys=True)


def test_dashboard_cli_summary_and_export(tmp_path: Path) -> None:
    db_path, _work_unit_id = _seed_dashboard_db(tmp_path)
    export_path = tmp_path / "dashboard_export.json"
    runner = CliRunner()

    summary_result = runner.invoke(
        app,
        [
            "dashboard",
            "summary",
            "--db-path",
            str(db_path),
            "--json",
        ],
    )
    export_result = runner.invoke(
        app,
        [
            "dashboard",
            "export",
            "--db-path",
            str(db_path),
            "--output",
            str(export_path),
            "--json",
        ],
    )

    assert summary_result.exit_code == 0, summary_result.output
    assert json.loads(summary_result.output)["summary"]["usage_entry_count"] == 1
    assert export_result.exit_code == 0, export_result.output
    assert export_path.exists()
    assert SECRET_REF not in export_path.read_text(encoding="utf-8")


def _seed_dashboard_db(tmp_path: Path) -> tuple[Path, str]:
    db_path = tmp_path / "tokenbank.db"
    core = HostAdapterCore(config_dir=REPO_ROOT / "config", db_path=db_path)
    account = core.upsert_manual_account_snapshot(
        provider="openai",
        account_label="personal",
        secret_ref=SECRET_REF,
        available_micros=25000000,
        visible_models=["gpt-5.5"],
    )
    account_snapshot_id = account["account_snapshot"]["account_snapshot_id"]
    demo = PrivateCapacityDemoRunner(
        config_dir=REPO_ROOT / "config",
        db_path=db_path,
    ).run(task="url_check")
    work_unit_id = demo["submissions"]["url_check"]["work_unit_id"]
    core.record_usage_ledger_entry(
        work_unit_id=work_unit_id,
        account_snapshot_id=account_snapshot_id,
    )
    core.create_audit_receipt(
        work_unit_id=work_unit_id,
        account_snapshot_id=account_snapshot_id,
    )
    return db_path, work_unit_id
