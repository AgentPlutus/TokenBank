from __future__ import annotations

import pytest
from pydantic import ValidationError

from tokenbank.accounts import build_manual_account_snapshot
from tokenbank.models.account_snapshot import AccountSnapshot


def test_account_snapshot_allows_local_secret_ref() -> None:
    snapshot = build_manual_account_snapshot(
        provider="openai",
        account_label="personal",
        secret_ref="keychain:tokenbank/openai/personal",
        available_micros=1000000,
        visible_models=["gpt-5.5"],
    )

    assert snapshot.raw_secret_present is False
    assert snapshot.secret_ref_status == "present"
    assert snapshot.balance is not None
    assert snapshot.balance.source == "manual"


def test_account_snapshot_rejects_raw_secret_marker() -> None:
    with pytest.raises(ValidationError):
        AccountSnapshot(
            account_snapshot_id="acct_bad",
            provider="openai",
            account_label="personal",
            status="configured",
            secret_ref="keychain:tokenbank/sk-thisisrawsecret",
            secret_ref_status="present",
            raw_secret_present=False,
        )


def test_account_snapshot_rejects_raw_secret_flag() -> None:
    with pytest.raises(ValidationError):
        AccountSnapshot(
            account_snapshot_id="acct_bad",
            provider="openai",
            account_label="personal",
            status="configured",
            secret_ref="keychain:tokenbank/openai/personal",
            secret_ref_status="present",
            raw_secret_present=True,
        )
