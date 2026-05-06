from __future__ import annotations

import shutil
from pathlib import Path

import pytest

from tokenbank.routebook.v1_loader import load_routebook_v1_dir

REPO_ROOT = Path(__file__).resolve().parents[2]


def test_routebook_v1_loader_reads_manifest_and_ontology() -> None:
    loaded = load_routebook_v1_dir(REPO_ROOT / "packs/base-routing/routebook")

    assert loaded.routebook_id == "tokenbank.base"
    assert loaded.version == "1.0.0"
    assert set(loaded.content_hashes) == {"routebook.yaml", "ontology.yaml"}
    assert "code" in loaded.task_families
    assert "strong_reasoning" in loaded.capability_tags
    assert "claim_extraction" in loaded.ontology["task_type_defaults"]


def test_routebook_v1_loader_rejects_missing_required_file(tmp_path: Path) -> None:
    target = tmp_path / "routebook"
    shutil.copytree(REPO_ROOT / "packs/base-routing/routebook", target)
    (target / "ontology.yaml").unlink()

    with pytest.raises(FileNotFoundError):
        load_routebook_v1_dir(target)
