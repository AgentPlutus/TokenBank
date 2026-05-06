"""Worker YAML config loader."""

from __future__ import annotations

from pathlib import Path

import yaml
from pydantic import BaseModel, Field, PositiveFloat


class WorkerConfig(BaseModel):
    worker_id: str
    control_plane_url: str = "http://127.0.0.1:8765"
    worker_token: str
    capabilities: list[str] = Field(default_factory=lambda: ["url_check"])
    backend_ids: list[str] = Field(default_factory=lambda: ["backend:url_check:v0"])
    backend_classes: list[str] = Field(default_factory=lambda: ["local_tool"])
    allowed_task_types: list[str] = Field(default_factory=lambda: ["url_check"])
    allowed_data_labels: list[str] = Field(default_factory=lambda: ["public_url"])
    allowed_privacy_levels: list[str] = Field(default_factory=lambda: ["private"])
    sandbox_root: Path = Path(".tokenbank/worker/sandbox")
    spool_dir: Path = Path(".tokenbank/worker/spool")
    heartbeat_interval_seconds: PositiveFloat = 10
    poll_interval_seconds: PositiveFloat = 2
    progress_interval_seconds: PositiveFloat = 15
    request_timeout_seconds: PositiveFloat = 10

    def manifest_payload(self) -> dict:
        return {
            "worker_id": self.worker_id,
            "identity": self.worker_id,
            "capabilities": self.capabilities,
            "allowed_task_types": self.allowed_task_types,
            "allowed_data_labels": self.allowed_data_labels,
            "allowed_privacy_levels": self.allowed_privacy_levels,
            "execution_location": "windows_worker",
            "trust_level": "trusted_private",
            "backend_ids": self.backend_ids,
            "backend_classes": self.backend_classes,
            "health_status": "healthy",
        }


def load_worker_config(path: str | Path) -> WorkerConfig:
    config_path = Path(path)
    payload = yaml.safe_load(config_path.read_text(encoding="utf-8")) or {}
    if "worker" in payload:
        payload = payload["worker"]
    return WorkerConfig.model_validate(payload)

