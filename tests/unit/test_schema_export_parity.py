from __future__ import annotations

import json
from pathlib import Path

from typer.testing import CliRunner

from tokenbank.cli.main import app
from tokenbank.schemas.export import generate_schema_documents, schema_document_text

REPO_ROOT = Path(__file__).resolve().parents[2]


def test_schema_export_parity() -> None:
    generated = generate_schema_documents()
    schema_dir = REPO_ROOT / "schemas"

    for filename, schema in generated.items():
        committed = schema_dir / filename
        assert committed.exists(), f"missing committed schema: {filename}"
        assert committed.read_text(encoding="utf-8") == schema_document_text(schema)


def test_schema_export_cli(tmp_path: Path) -> None:
    result = CliRunner().invoke(
        app,
        ["schemas", "export", "--output-dir", str(tmp_path)],
    )

    assert result.exit_code == 0
    assert "Exported" in result.output

    exported = sorted(path.name for path in tmp_path.glob("*.schema.json"))
    expected = sorted(generate_schema_documents())
    assert exported == expected

    for filename in expected:
        json.loads((tmp_path / filename).read_text(encoding="utf-8"))
