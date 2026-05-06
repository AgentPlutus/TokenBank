from __future__ import annotations

import re
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
PUBLIC_DOCS = [
    REPO_ROOT / "docs" / "PRIVATE_AGENT_CAPACITY_NETWORK.md",
    REPO_ROOT / "docs" / "CAPABILITY_NODES.md",
    REPO_ROOT / "docs" / "WORKLOAD_SOURCES.md",
    REPO_ROOT / "docs" / "XRADAR_BATCH_ADAPTER.md",
    REPO_ROOT / "docs" / "SECURITY_MODEL.md",
    REPO_ROOT / "docs" / "MCP_SERVER.md",
    REPO_ROOT / "docs" / "PUBLIC_ALPHA_PACKAGE.md",
    REPO_ROOT / "docs" / "TESTING.md",
]
PUBLIC_EXAMPLES = [
    REPO_ROOT / "examples" / "openclaw_skill" / "SKILL.md",
    REPO_ROOT / "examples" / "claude_code" / "mcp_config.md",
    REPO_ROOT / "examples" / "codex_cli" / "config.toml",
    REPO_ROOT / "examples" / "aider" / "cli_recipe.md",
]


def test_docs_private_capacity_terms_present() -> None:
    for path in PUBLIC_DOCS:
        content = path.read_text(encoding="utf-8")
        assert "Private Agent Capacity Network" in content


def test_docs_no_active_local_agent_farm_product_framing() -> None:
    public_text = _public_text()

    assert "Local Agent Farm" not in public_text


def test_docs_no_active_seller_yield_marketplace_language() -> None:
    public_text = _public_text()

    assert "AI plan yield is Phase 2+ strategy" in public_text
    assert "is not active in Phase 0/1" in public_text
    assert "does not implement seller mode" in public_text
    assert "seller earnings" not in public_text
    assert "active yield" not in public_text
    assert "marketplace for sellers" not in public_text


def test_docs_no_network_layer_claim() -> None:
    public_text = _public_text()

    assert "Tailscale analogy is architecture-only" in public_text
    assert "does not implement network-layer connectivity" in public_text
    assert "does not implement P2P networking" in public_text


def test_docs_no_model_proxy_claim() -> None:
    public_text = _public_text()

    assert "not an OpenAI-compatible model proxy" in public_text
    assert "does not expose an OpenAI-compatible model proxy" in public_text
    assert "chat completions" in public_text


def test_docs_xradar_optional_language() -> None:
    public_text = _public_text()

    assert "x-radar is optional workload source" in public_text
    assert "not a multi-agent dependency" in public_text
    assert "not required for the core private capacity demo" in public_text


def test_public_alpha_docs_include_caveats() -> None:
    content = (REPO_ROOT / "docs" / "PUBLIC_ALPHA_PACKAGE.md").read_text(
        encoding="utf-8"
    )

    assert "Public alpha is not active in Phase 0" in content
    assert "Any red gate failure blocks alpha packaging" in content
    assert "does not store user OAuth tokens" in content


def test_examples_do_not_request_raw_credentials() -> None:
    text = "\n".join(path.read_text(encoding="utf-8") for path in PUBLIC_EXAMPLES)

    assert not re.search(r"sk-[A-Za-z0-9_-]{8,}", text)
    assert "api_key =" not in text
    assert "oauth_token =" not in text
    assert "cookie =" not in text
    assert "Do not configure OAuth tokens" in text


def _public_text() -> str:
    return "\n".join(path.read_text(encoding="utf-8") for path in PUBLIC_DOCS)
