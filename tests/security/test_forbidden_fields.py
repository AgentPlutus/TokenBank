from __future__ import annotations

import pytest

from tokenbank.policy.extensions import lint_extension_keys
from tokenbank.policy.redaction import redact_token_prefixes


@pytest.mark.parametrize(
    "payload",
    [
        {"extensions": {"seller_listing": True}},
        {"extensions": {"marketplace": {"enabled": True}}},
        {"extensions": {"payment_terms": "none"}},
        {"extensions": {"payout_target": "none"}},
        {"extensions": {"settlement_plan": "none"}},
        {"extensions": {"yield_hint": "none"}},
        {"extensions": {"account_pool": "none"}},
        {"extensions": {"oauth_proxy": "none"}},
        {"extensions": {"credential_broker": "none"}},
    ],
)
def test_forbidden_extension_keys_are_linted(payload: dict) -> None:
    issues = lint_extension_keys(payload)

    assert issues


def test_token_prefix_redaction_patterns() -> None:
    text = "host=tbk_h_abc123 worker=tbk_w_def456 internal=tbk_i_ghi789"

    redacted = redact_token_prefixes(text)

    assert "tbk_h_" not in redacted
    assert "tbk_w_" not in redacted
    assert "tbk_i_" not in redacted
    assert redacted.count("[REDACTED_TOKEN]") == 3

