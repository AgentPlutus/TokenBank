from __future__ import annotations

import subprocess
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]

REQUIRED_PUBLIC_FILES = [
    ".github/workflows/ci.yml",
    "CONTRIBUTING.md",
    "LICENSE",
    "SECURITY.md",
]

INTERNAL_TRACKED_PREFIXES = [
    "DR Prompt/",
    "DR Results/",
    "docs/research/",
    "handoffs/",
]

INTERNAL_TRACKED_FILES = {
    "AGENTS.md",
    "DR0B.md",
    "docs/ROUTEBOOK_V1_INTELLIGENT_ROUTING_PLAN.md",
    "TOKENBANK_COMMERCIAL_STRATEGY_V2_AI_PLAN_YIELD.md",
    "TOKENBANK_PHASE_0_PRIVATE_AGENT_CAPACITY_NETWORK_IMPLEMENTATION_PLAN_FINAL.md",
    "TOKENBANK_ROUND_0_TOKENBANK_DIRECTION_AND_PLAN_CALIBRATION.md",
    "TOKENBANK_SERIAL_DR_RESEARCH_PLAN.md",
    "TokenBank_项目说明_v3.md",
}

FORBIDDEN_PUBLIC_REFERENCES = [
    "DR Prompt/",
    "DR Results/",
    "docs/research/",
    "handoffs/",
    "docs/ROUTEBOOK_V1_INTELLIGENT_ROUTING_PLAN.md",
    "DR0B.md",
    "TOKENBANK_COMMERCIAL_STRATEGY_V2_AI_PLAN_YIELD.md",
    "TOKENBANK_PHASE_0_PRIVATE_AGENT_CAPACITY_NETWORK_IMPLEMENTATION_PLAN_FINAL.md",
    "TOKENBANK_ROUND_0_TOKENBANK_DIRECTION_AND_PLAN_CALIBRATION.md",
    "TOKENBANK_SERIAL_DR_RESEARCH_PLAN.md",
    "TokenBank_项目说明_v3.md",
]

TEXT_SUFFIXES = {".json", ".md", ".py", ".toml", ".txt", ".yaml", ".yml"}
REFERENCE_SCAN_EXCLUDES = {
    ".gitignore",
    "tests/unit/test_public_repo_hygiene.py",
}


def test_required_public_repo_files_exist() -> None:
    for relative_path in REQUIRED_PUBLIC_FILES:
        assert (REPO_ROOT / relative_path).is_file(), relative_path


def test_internal_planning_files_are_not_tracked() -> None:
    tracked_files = set(_tracked_files())

    for path in INTERNAL_TRACKED_FILES:
        assert path not in tracked_files

    for tracked_file in tracked_files:
        assert not any(
            tracked_file.startswith(prefix) for prefix in INTERNAL_TRACKED_PREFIXES
        ), tracked_file


def test_public_text_files_do_not_reference_internal_materials() -> None:
    offenders: list[str] = []

    for relative_path in _tracked_files():
        if relative_path in REFERENCE_SCAN_EXCLUDES:
            continue
        path = REPO_ROOT / relative_path
        if path.suffix not in TEXT_SUFFIXES:
            continue
        content = path.read_text(encoding="utf-8")
        for forbidden in FORBIDDEN_PUBLIC_REFERENCES:
            if forbidden in content:
                offenders.append(f"{relative_path}: {forbidden}")

    assert offenders == []


def test_internal_materials_are_ignored_when_present_locally() -> None:
    ignore_targets = [
        "AGENTS.md",
        "DR Results/DR1 SCHEMA_AND_ARCHITECTURE_LOCK.md",
        "docs/research/AGENT_HARNESS_BENCHMARK_2026-05-06.md",
        "TOKENBANK_PHASE_0_PRIVATE_AGENT_CAPACITY_NETWORK_IMPLEMENTATION_PLAN_FINAL.md",
    ]
    result = subprocess.run(
        ["git", "check-ignore", "--stdin"],
        cwd=REPO_ROOT,
        input="\n".join(ignore_targets),
        text=True,
        capture_output=True,
        check=True,
    )

    ignored = set(result.stdout.splitlines())
    assert ignored == set(ignore_targets)


def _tracked_files() -> list[str]:
    result = subprocess.run(
        ["git", "ls-files"],
        cwd=REPO_ROOT,
        text=True,
        capture_output=True,
        check=True,
    )
    return result.stdout.splitlines()
