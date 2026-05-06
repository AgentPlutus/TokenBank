from __future__ import annotations

import json
from pathlib import Path

from typer.testing import CliRunner

from tokenbank.cli.main import app
from tokenbank.demo.private_capacity import PrivateCapacityDemoRunner


def test_accounts_usage_and_audit_cli(tmp_path: Path) -> None:
    db_path = tmp_path / "tokenbank.db"
    runner = CliRunner()

    account_result = runner.invoke(
        app,
        [
            "accounts",
            "snapshot",
            "--provider",
            "openai",
            "--account-label",
            "personal",
            "--secret-ref",
            "keychain:tokenbank/openai/personal",
            "--available-micros",
            "25000000",
            "--visible-models",
            "gpt-5.5,gpt-5.4",
            "--db-path",
            str(db_path),
            "--json",
        ],
    )
    assert account_result.exit_code == 0, account_result.output
    account_payload = json.loads(account_result.output)
    account_snapshot_id = account_payload["account_snapshot"]["account_snapshot_id"]
    assert account_payload["account_snapshot"]["raw_secret_present"] is False
    assert account_payload["snapshot_hash"]

    demo = PrivateCapacityDemoRunner(db_path=db_path).run(task="url_check")
    work_unit_id = demo["submissions"]["url_check"]["work_unit_id"]

    usage_result = runner.invoke(
        app,
        [
            "usage",
            "record",
            "--work-unit-id",
            work_unit_id,
            "--account-snapshot-id",
            account_snapshot_id,
            "--db-path",
            str(db_path),
            "--json",
        ],
    )
    assert usage_result.exit_code == 0, usage_result.output
    usage_payload = json.loads(usage_result.output)
    usage_entry = usage_payload["usage_ledger_entry"]
    assert usage_entry["usage_source"] == "estimate"
    assert usage_entry["cost_source"] == "not_applicable"
    assert usage_entry["entry_hash"]
    assert usage_entry["account_snapshot_id"] == account_snapshot_id

    ledger_result = runner.invoke(
        app,
        [
            "usage",
            "ledger",
            "--work-unit-id",
            work_unit_id,
            "--db-path",
            str(db_path),
            "--json",
        ],
    )
    assert ledger_result.exit_code == 0, ledger_result.output
    ledger_payload = json.loads(ledger_result.output)
    assert ledger_payload["entry_count"] == 1

    receipt_result = runner.invoke(
        app,
        [
            "audit",
            "receipt",
            "--work-unit-id",
            work_unit_id,
            "--db-path",
            str(db_path),
            "--json",
        ],
    )
    assert receipt_result.exit_code == 0, receipt_result.output
    receipt_payload = json.loads(receipt_result.output)
    receipt = receipt_payload["audit_receipt"]
    assert receipt["work_unit_id"] == work_unit_id
    assert receipt["receipt_hash"]
    assert receipt["usage_ledger_entry_hash"] == usage_entry["entry_hash"]
    assert receipt["redaction_profile"] == "ids_and_hashes_only"
    serialized_receipt = json.dumps(receipt, sort_keys=True)
    assert '"output":' not in serialized_receipt
    assert "https://example.com/status" not in serialized_receipt

    receipt_list_result = runner.invoke(
        app,
        [
            "audit",
            "list",
            "--work-unit-id",
            work_unit_id,
            "--db-path",
            str(db_path),
            "--json",
        ],
    )
    assert receipt_list_result.exit_code == 0, receipt_list_result.output
    receipt_list_payload = json.loads(receipt_list_result.output)
    assert receipt_list_payload["receipt_count"] == 1
