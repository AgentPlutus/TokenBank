"""Deterministic JSON Schema export for P0 DTOs."""

from __future__ import annotations

import json
from pathlib import Path

from pydantic import BaseModel

from tokenbank.models import (
    Assignment,
    BackendError,
    BackendHealth,
    BackendManifest,
    CapacityNode,
    CapacityNodeHealth,
    CapacityProfile,
    ExecutionAttempt,
    HostCostQualitySummary,
    HostResultSummary,
    PolicyDecision,
    RouteCandidate,
    RouteDecisionTrace,
    RoutePlan,
    TaskAnalysisReport,
    TaskProfile,
    UsageRecord,
    VerifierReport,
    WorkUnit,
    WorkUnitResultEnvelope,
)

SCHEMA_MODELS: tuple[tuple[str, type[BaseModel]], ...] = (
    ("work_unit", WorkUnit),
    ("work_unit_result_envelope", WorkUnitResultEnvelope),
    ("capacity_node", CapacityNode),
    ("capacity_node_health", CapacityNodeHealth),
    ("capacity_profile", CapacityProfile),
    ("route_plan", RoutePlan),
    ("route_candidate", RouteCandidate),
    ("route_decision_trace", RouteDecisionTrace),
    ("task_analysis_report", TaskAnalysisReport),
    ("task_profile", TaskProfile),
    ("policy_decision", PolicyDecision),
    ("execution_attempt", ExecutionAttempt),
    ("assignment", Assignment),
    ("backend_manifest", BackendManifest),
    ("backend_health", BackendHealth),
    ("usage_record", UsageRecord),
    ("backend_error", BackendError),
    ("verifier_report", VerifierReport),
    ("host_result_summary", HostResultSummary),
    ("host_cost_quality_summary", HostCostQualitySummary),
)


def schema_filename(schema_name: str) -> str:
    return f"{schema_name}.schema.json"


def generate_schema_documents() -> dict[str, dict]:
    documents: dict[str, dict] = {}
    for schema_name, model in SCHEMA_MODELS:
        schema = model.model_json_schema(ref_template="#/$defs/{model}")
        schema["$schema"] = "https://json-schema.org/draft/2020-12/schema"
        documents[schema_filename(schema_name)] = schema
    return documents


def schema_document_text(schema: dict) -> str:
    return f"{json.dumps(schema, indent=2, sort_keys=True)}\n"


def export_schema_files(output_dir: Path = Path("schemas")) -> list[Path]:
    output_dir.mkdir(parents=True, exist_ok=True)
    written: list[Path] = []
    for filename, schema in generate_schema_documents().items():
        target = output_dir / filename
        target.write_text(schema_document_text(schema), encoding="utf-8")
        written.append(target)
    return written
