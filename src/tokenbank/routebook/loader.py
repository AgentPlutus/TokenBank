"""Routebook YAML loader."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

from tokenbank.core.canonical import canonical_json_hash

REQUIRED_ROUTEBOOK_FILES = (
    "task_types.yaml",
    "task_levels.yaml",
    "backend_classes.yaml",
    "verifier_mapping.yaml",
    "fallback_rules.yaml",
    "policy_hints.yaml",
    "forbidden_routes.yaml",
)


@dataclass(frozen=True)
class LoadedRoutebook:
    root: Path
    documents: dict[str, dict[str, Any]]
    content_hashes: dict[str, str]

    @property
    def task_types(self) -> list[dict[str, Any]]:
        return list(self.documents["task_types"].get("task_types", []))

    @property
    def task_levels(self) -> dict[str, dict[str, Any]]:
        return dict(self.documents["task_levels"].get("task_levels", {}))

    @property
    def candidate_rules(self) -> list[dict[str, Any]]:
        return list(self.documents["backend_classes"].get("candidate_rules", []))

    @property
    def verifier_mapping(self) -> dict[str, str]:
        return dict(self.documents["verifier_mapping"].get("verifier_mapping", {}))

    @property
    def verifier_recipes(self) -> list[dict[str, Any]]:
        return list(self.documents["verifier_mapping"].get("verifier_recipes", []))

    @property
    def fallback_rules(self) -> list[dict[str, Any]]:
        return list(self.documents["fallback_rules"].get("fallback_rules", []))

    @property
    def policy_hints(self) -> dict[str, list[str]]:
        return dict(self.documents["policy_hints"].get("policy_hints", {}))

    @property
    def forbidden_routes(self) -> dict[str, Any]:
        return dict(self.documents["forbidden_routes"].get("forbidden_routes", {}))

    def task_type_entry(self, task_type: str) -> dict[str, Any]:
        for entry in self.task_types:
            if entry.get("task_type") == task_type:
                return entry
        raise KeyError(f"unknown task_type: {task_type}")


def load_yaml_file(path: Path) -> dict[str, Any]:
    loaded = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    if not isinstance(loaded, dict):
        raise ValueError(f"Routebook file must contain a mapping: {path}")
    return loaded


def load_routebook_dir(routebook_dir: str | Path = "routebook") -> LoadedRoutebook:
    root = Path(routebook_dir)
    documents: dict[str, dict[str, Any]] = {}
    content_hashes: dict[str, str] = {}

    for filename in REQUIRED_ROUTEBOOK_FILES:
        path = root / filename
        if not path.exists():
            raise FileNotFoundError(f"Missing required routebook file: {path}")
        document = load_yaml_file(path)
        documents[path.stem] = document
        content_hashes[filename] = canonical_json_hash(document)

    return LoadedRoutebook(
        root=root,
        documents=documents,
        content_hashes=content_hashes,
    )

