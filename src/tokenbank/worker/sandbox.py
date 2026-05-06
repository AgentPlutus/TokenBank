"""Per-assignment sandbox directory structure."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class AssignmentSandbox:
    root: Path
    input_dir: Path
    output_dir: Path
    tmp_dir: Path
    log_dir: Path


class WorkerSandbox:
    def __init__(self, root: Path, worker_id: str):
        self.root = root / worker_id

    def ensure_root(self) -> Path:
        self.root.mkdir(parents=True, exist_ok=True)
        return self.root

    def create_assignment(self, assignment_id: str) -> AssignmentSandbox:
        assignment_root = self.ensure_root() / "assignments" / assignment_id
        sandbox = AssignmentSandbox(
            root=assignment_root,
            input_dir=assignment_root / "input",
            output_dir=assignment_root / "output",
            tmp_dir=assignment_root / "tmp",
            log_dir=assignment_root / "logs",
        )
        for path in (
            sandbox.input_dir,
            sandbox.output_dir,
            sandbox.tmp_dir,
            sandbox.log_dir,
        ):
            path.mkdir(parents=True, exist_ok=True)
        return sandbox

