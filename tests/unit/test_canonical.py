from __future__ import annotations

from pathlib import Path

from tokenbank.core.canonical import (
    artifact_hash,
    canonical_json_dumps,
    canonical_json_hash,
    canonical_url,
    dataset_hash,
    normalized_text,
    normalized_text_hash,
    output_hash,
    result_hash,
)


def test_canonical_json_is_order_independent() -> None:
    left = {"b": [2, 1], "a": {"z": True, "m": None}}
    right = {"a": {"m": None, "z": True}, "b": [2, 1]}

    assert canonical_json_dumps(left) == '{"a":{"m":null,"z":true},"b":[2,1]}'
    assert canonical_json_hash(left) == canonical_json_hash(right)


def test_canonical_url_normalizes_scheme_host_port_path_query_and_fragment() -> None:
    assert (
        canonical_url("HTTPS://Example.COM:443/a/../b/?z=9&a=1#frag")
        == "https://example.com/b/?a=1&z=9"
    )


def test_normalized_text_hash_collapses_unicode_and_whitespace() -> None:
    left = "Ａgent\n\n capacity\t network"
    right = "Agent capacity network"

    assert normalized_text(left) == right
    assert normalized_text_hash(left) == normalized_text_hash(right)


def test_domain_hash_helpers_are_deterministic(tmp_path: Path) -> None:
    artifact = tmp_path / "artifact.txt"
    artifact.write_text("capacity", encoding="utf-8")

    assert artifact_hash(artifact) == artifact_hash(b"capacity")
    assert dataset_hash([{"url": "https://example.com", "ok": True}]) == dataset_hash(
        [{"ok": True, "url": "https://example.com"}]
    )
    assert output_hash({"b": 2, "a": 1}) == output_hash({"a": 1, "b": 2})
    assert result_hash({"status": "ok"}) != output_hash({"status": "ok"})

