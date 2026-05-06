"""Routebook V1 package loader."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from tokenbank.core.canonical import canonical_json_hash
from tokenbank.routebook.loader import load_yaml_file

REQUIRED_ROUTEBOOK_V1_FILES = (
    "routebook.yaml",
    "ontology.yaml",
    "scoring.yaml",
)


@dataclass(frozen=True)
class LoadedRoutebookV1:
    root: Path
    manifest: dict[str, Any]
    ontology: dict[str, Any]
    documents: dict[str, dict[str, Any]]
    content_hashes: dict[str, str]

    @property
    def routebook_id(self) -> str:
        return str(self.manifest["routebook_id"])

    @property
    def version(self) -> str:
        return str(self.manifest["version"])

    @property
    def capability_tags(self) -> dict[str, Any]:
        return dict(self.ontology.get("capability_tags", {}))

    @property
    def task_families(self) -> dict[str, Any]:
        return dict(self.ontology.get("task_families", {}))

    @property
    def scoring(self) -> dict[str, Any]:
        return dict(self.documents["scoring"])


def load_routebook_v1_dir(
    routebook_v1_dir: str | Path = "packs/base-routing/routebook",
) -> LoadedRoutebookV1:
    root = Path(routebook_v1_dir)
    documents: dict[str, dict[str, Any]] = {}
    content_hashes: dict[str, str] = {}

    for filename in REQUIRED_ROUTEBOOK_V1_FILES:
        path = root / filename
        if not path.exists():
            raise FileNotFoundError(f"Missing required Routebook V1 file: {path}")
        document = load_yaml_file(path)
        documents[path.stem] = document
        content_hashes[filename] = canonical_json_hash(document)

    manifest = documents["routebook"]
    ontology = documents["ontology"]
    _validate_manifest(manifest)
    _validate_ontology(ontology)
    _validate_scoring(documents["scoring"])
    return LoadedRoutebookV1(
        root=root,
        manifest=manifest,
        ontology=ontology,
        documents=documents,
        content_hashes=content_hashes,
    )


def _validate_manifest(manifest: dict[str, Any]) -> None:
    for key in ("routebook_id", "version", "ontology_version"):
        value = manifest.get(key)
        if not isinstance(value, str) or not value:
            raise ValueError(f"Routebook V1 manifest requires non-empty {key}")


def _validate_ontology(ontology: dict[str, Any]) -> None:
    for key in ("task_families", "capability_tags", "quality_tiers"):
        value = ontology.get(key)
        if not isinstance(value, dict) or not value:
            raise ValueError(f"Routebook V1 ontology requires non-empty {key}")


def _validate_scoring(scoring: dict[str, Any]) -> None:
    for key in ("scorer_id", "version", "selection_policy"):
        value = scoring.get(key)
        if not isinstance(value, str) or not value:
            raise ValueError(f"Routebook V1 scoring requires non-empty {key}")
    weights = scoring.get("score_weights")
    if not isinstance(weights, dict) or not weights:
        raise ValueError("Routebook V1 scoring requires non-empty score_weights")
    for component, weight in weights.items():
        if not isinstance(component, str) or not component:
            raise ValueError("Routebook V1 scoring component names must be strings")
        if not isinstance(weight, int | float) or weight < 0:
            raise ValueError("Routebook V1 scoring weights must be non-negative")
    hard_filters = scoring.get("hard_filters")
    if not isinstance(hard_filters, list) or not hard_filters:
        raise ValueError("Routebook V1 scoring requires hard_filters")
