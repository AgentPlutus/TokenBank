"""Canonical serialization, normalization, and hashing helpers."""

from __future__ import annotations

import hashlib
import json
import posixpath
import re
import unicodedata
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any
from urllib.parse import parse_qsl, quote, urlencode, urlsplit, urlunsplit

from pydantic import BaseModel


def _json_default(value: Any) -> str:
    if isinstance(value, datetime):
        normalized = value.astimezone(UTC) if value.tzinfo else value
        return normalized.isoformat().replace("+00:00", "Z")
    if isinstance(value, date):
        return value.isoformat()
    if isinstance(value, Path):
        return str(value)
    raise TypeError(f"Object of type {type(value).__name__} is not JSON serializable")


def _jsonable(value: Any) -> Any:
    if isinstance(value, BaseModel):
        return value.model_dump(mode="json", exclude_none=False)
    return value


def canonical_json_dumps(value: Any) -> str:
    """Return deterministic, compact JSON for a JSON-compatible value."""
    return json.dumps(
        _jsonable(value),
        allow_nan=False,
        default=_json_default,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    )


def canonical_json_hash(value: Any) -> str:
    """Return a SHA-256 hash of canonical JSON."""
    return hashlib.sha256(canonical_json_dumps(value).encode("utf-8")).hexdigest()


def canonical_url(url: str) -> str:
    """Normalize a URL for deterministic comparison and hashing."""
    parts = urlsplit(url.strip())
    scheme = parts.scheme.lower()
    hostname = (parts.hostname or "").lower()
    port = parts.port

    include_port = port is not None and not (
        (scheme == "http" and port == 80) or (scheme == "https" and port == 443)
    )
    netloc = hostname if not include_port else f"{hostname}:{port}"

    raw_path = parts.path or "/"
    normalized_path = posixpath.normpath(raw_path)
    if raw_path.endswith("/") and not normalized_path.endswith("/"):
        normalized_path += "/"
    if not normalized_path.startswith("/"):
        normalized_path = f"/{normalized_path}"
    path = quote(normalized_path, safe="/:@%")

    query_pairs = parse_qsl(parts.query, keep_blank_values=True)
    query = urlencode(sorted(query_pairs), doseq=True)

    return urlunsplit((scheme, netloc, path, query, ""))


_WHITESPACE_RE = re.compile(r"\s+")


def normalized_text(text: str) -> str:
    """Normalize Unicode and collapse whitespace without changing case."""
    normalized = unicodedata.normalize("NFKC", text)
    return _WHITESPACE_RE.sub(" ", normalized).strip()


def normalized_text_hash(text: str) -> str:
    """Return a SHA-256 hash of normalized text."""
    return hashlib.sha256(normalized_text(text).encode("utf-8")).hexdigest()


def _hash_bytes(domain: str, payload: bytes) -> str:
    digest = hashlib.sha256()
    digest.update(domain.encode("utf-8"))
    digest.update(b"\0")
    digest.update(payload)
    return digest.hexdigest()


def artifact_hash(content: bytes | str | Path) -> str:
    """Hash artifact content with a domain separator."""
    if isinstance(content, Path):
        payload = content.read_bytes()
    elif isinstance(content, bytes):
        payload = content
    else:
        payload = content.encode("utf-8")
    return _hash_bytes("tokenbank.artifact.v1", payload)


def dataset_hash(items: list[Any]) -> str:
    """Hash an ordered dataset using canonical JSON."""
    return canonical_json_hash({"dataset": items, "kind": "tokenbank.dataset.v1"})


def output_hash(output: Any) -> str:
    """Hash backend output using canonical JSON."""
    return canonical_json_hash({"kind": "tokenbank.output.v1", "output": output})


def result_hash(result: Any) -> str:
    """Hash a result envelope or result payload using canonical JSON."""
    return canonical_json_hash({"kind": "tokenbank.result.v1", "result": result})
