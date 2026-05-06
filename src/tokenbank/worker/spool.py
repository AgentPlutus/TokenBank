"""Completed result spool for failed submits."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from pydantic import BaseModel

from tokenbank.core.canonical import canonical_json_dumps
from tokenbank.core.tokens import assignment_lease_token_hash


class CompletedSpoolEntry(BaseModel):
    spool_id: str
    status: str = "completed"
    assignment_id: str
    worker_id: str
    lease_token_hash: str
    output: dict[str, Any]


class ResultSpool:
    def __init__(self, spool_dir: Path):
        self.spool_dir = spool_dir
        self.spool_dir.mkdir(parents=True, exist_ok=True)

    def write_completed(
        self,
        *,
        assignment_id: str,
        worker_id: str,
        lease_token: str,
        output: dict[str, Any],
    ) -> Path:
        entry = CompletedSpoolEntry(
            spool_id=f"spool_{assignment_id}",
            assignment_id=assignment_id,
            worker_id=worker_id,
            lease_token_hash=assignment_lease_token_hash(lease_token),
            output=output,
        )
        target = self.spool_dir / f"{entry.spool_id}.json"
        temp = target.with_suffix(".json.tmp")
        temp.write_text(
            canonical_json_dumps(entry.model_dump(mode="json")),
            encoding="utf-8",
        )
        temp.replace(target)
        return target

    def completed_entries(self) -> list[tuple[Path, CompletedSpoolEntry]]:
        entries: list[tuple[Path, CompletedSpoolEntry]] = []
        for path in sorted(self.spool_dir.glob("*.json")):
            payload = json.loads(path.read_text(encoding="utf-8"))
            entry = CompletedSpoolEntry.model_validate(payload)
            if entry.status == "completed":
                entries.append((path, entry))
        return entries

    def remove(self, path: Path) -> None:
        path.unlink(missing_ok=True)
