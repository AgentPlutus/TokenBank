"""Static policy bundle loader."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from tokenbank.config_runtime.loader import LoadedConfig, load_config_dir


@dataclass(frozen=True)
class PolicyBundle:
    provider_policy: dict[str, Any]
    data_policy: dict[str, Any]
    sandbox_profile: dict[str, Any]
    egress_policy: dict[str, Any]
    backend_policy: dict[str, Any]
    redaction_policy: dict[str, Any]
    runtime: dict[str, Any]
    content_hashes: dict[str, str]

    @property
    def allowed_backend_ids(self) -> set[str]:
        policy = self.backend_policy.get("backend_policy", {})
        return set(policy.get("allowed_backend_ids", []))

    @property
    def allowed_backend_classes(self) -> set[str]:
        policy = self.backend_policy.get("backend_policy", {})
        return set(policy.get("allowed_backend_classes", []))

    @property
    def forbidden_backend_classes(self) -> set[str]:
        policy = self.backend_policy.get("backend_policy", {})
        return set(policy.get("forbidden_backend_classes", []))


def compile_policy_bundle(loaded_config: LoadedConfig) -> PolicyBundle:
    docs = loaded_config.documents
    return PolicyBundle(
        provider_policy=docs["provider_policy"],
        data_policy=docs["data_policy"],
        sandbox_profile=docs["sandbox_profile"],
        egress_policy=docs["egress_policy"],
        backend_policy=docs["backend_policy"],
        redaction_policy=docs["redaction_policy"],
        runtime=docs["runtime"],
        content_hashes=loaded_config.content_hashes,
    )


def load_policy_bundle(config_dir: str | Path = "config") -> PolicyBundle:
    return compile_policy_bundle(load_config_dir(config_dir))

