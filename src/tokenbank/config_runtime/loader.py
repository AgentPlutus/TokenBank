"""YAML config loader with deterministic content hashes."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

from tokenbank.config_runtime.runtime_mode import RuntimeMode
from tokenbank.core.canonical import canonical_json_hash

REQUIRED_CONFIG_FILES = (
    "provider_policy.yaml",
    "data_policy.yaml",
    "sandbox_profile.yaml",
    "egress_policy.yaml",
    "backend_policy.yaml",
    "redaction_policy.yaml",
    "backend_registry.yaml",
    "capacity_registry.yaml",
    "runtime.yaml",
)


@dataclass(frozen=True)
class LoadedConfig:
    root: Path
    documents: dict[str, dict[str, Any]]
    content_hashes: dict[str, str]

    @property
    def runtime_mode(self) -> RuntimeMode:
        runtime = self.documents["runtime"].get("runtime", {})
        return RuntimeMode(runtime.get("runtime_mode", RuntimeMode.DEMO.value))


def load_yaml_file(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as handle:
        loaded = yaml.safe_load(handle) or {}
    if not isinstance(loaded, dict):
        raise ValueError(f"Config file must contain a mapping: {path}")
    return loaded


def load_config_dir(config_dir: str | Path = "config") -> LoadedConfig:
    root = Path(config_dir)
    documents: dict[str, dict[str, Any]] = {}
    content_hashes: dict[str, str] = {}

    for filename in REQUIRED_CONFIG_FILES:
        path = root / filename
        if not path.exists():
            raise FileNotFoundError(f"Missing required config file: {path}")
        document = load_yaml_file(path)
        key = path.stem
        documents[key] = document
        content_hashes[filename] = canonical_json_hash(document)

    pricing_dir = root / "pricing"
    pricing_docs: list[dict[str, Any]] = []
    if pricing_dir.exists():
        for path in sorted(pricing_dir.glob("*.yaml")):
            document = load_yaml_file(path)
            pricing_docs.append(document)
            content_hashes[f"pricing/{path.name}"] = canonical_json_hash(document)
    documents["pricing"] = {"documents": pricing_docs}

    return LoadedConfig(root=root, documents=documents, content_hashes=content_hashes)
