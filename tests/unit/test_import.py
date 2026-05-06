from __future__ import annotations

from pathlib import Path

from typer.testing import CliRunner

import tokenbank
from tokenbank.cli.main import app

REPO_ROOT = Path(__file__).resolve().parents[2]


def test_import() -> None:
    assert tokenbank.PRODUCT_NAME == "TokenBank"
    assert tokenbank.PHASE_0_NAME == "Private Agent Capacity Network"
    assert tokenbank.__version__


def test_cli_help() -> None:
    result = CliRunner().invoke(app, ["--help"])

    assert result.exit_code == 0
    assert "Private Agent Capacity Network" in result.output
    assert "VS0" in result.output
    assert "url_check" in result.output
    assert "VS1a" in result.output
    assert "dedup" in result.output
    assert "VS1b" in result.output
    assert "webpage_extraction" in result.output
    assert "VS1c" in result.output
    assert "topic_classification" in result.output
    assert "VS1d" in result.output
    assert "claim_extraction" in result.output
    assert "end-to-end" in result.output


def test_docs_private_capacity_terms() -> None:
    docs = [
        REPO_ROOT / "README.md",
        REPO_ROOT / "docs" / "PRIVATE_AGENT_CAPACITY_NETWORK.md",
    ]

    for doc in docs:
        content = doc.read_text(encoding="utf-8")
        assert "Private Agent Capacity Network" in content
        assert "Local Agent Farm" not in content


def test_no_proxy_endpoint_stub() -> None:
    source_text = "\n".join(
        path.read_text(encoding="utf-8")
        for path in (REPO_ROOT / "src").rglob("*.py")
    )

    forbidden_endpoint_markers = [
        '@app.post("/v1/chat/completions"',
        '@app.route("/v1/chat/completions"',
        '"/v1/chat/completions"',
        "'/v1/chat/completions'",
    ]

    for marker in forbidden_endpoint_markers:
        assert marker not in source_text
