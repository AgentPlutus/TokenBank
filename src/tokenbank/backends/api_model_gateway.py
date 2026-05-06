"""Control-plane API model gateway adapter scaffold."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from tokenbank.backends.adapter import BackendExecutionContext, build_result_envelope
from tokenbank.backends.errors import normalize_backend_error
from tokenbank.backends.structured_output import repair_structured_output_stub
from tokenbank.backends.usage import make_usage_record
from tokenbank.capacity.validators import CONTROL_PLANE_GATEWAY_WORKER_ID
from tokenbank.models.result_envelope import WorkUnitResultEnvelope

CONTROL_PLANE_GATEWAY_NODE_ID = f"capnode:worker:{CONTROL_PLANE_GATEWAY_WORKER_ID}"


class APIModelGatewayAdapter:
    backend_class = "api_model_gateway"
    provider_protocol = "openai_compatible_single_provider"

    def execute(self, context: BackendExecutionContext) -> WorkUnitResultEnvelope:
        started_at = datetime.now(UTC)
        usage = [
            make_usage_record(
                work_unit_id=context.work_unit_id,
                attempt_id=context.attempt_id,
                backend_id=context.backend_id,
                estimated_cost_micros=1000,
                actual_cost_micros=0,
                cost_source="estimated",
                cost_confidence="low",
            )
        ]
        boundary_error = _control_plane_boundary_error(context)
        if boundary_error is not None:
            return build_result_envelope(
                context=context,
                output={"ok": False, "reason": boundary_error.error_code},
                usage_records=usage,
                started_at=started_at,
                status="failed",
                errors=[boundary_error],
                provider_id=context.provider_id,
                model_id=context.model_id,
            )
        if context.task_type == "topic_classification":
            return build_result_envelope(
                context=context,
                output=_classify_topic_stub(context.input_payload),
                usage_records=usage,
                started_at=started_at,
                provider_id=context.provider_id,
                model_id=context.model_id or "model:p0_topic_stub",
                redacted_logs=[
                    "api_model_gateway deterministic topic stub completed "
                    "on control plane"
                ],
            )
        if context.task_type == "claim_extraction":
            return build_result_envelope(
                context=context,
                output=_extract_claims_stub(context.input_payload),
                usage_records=usage,
                started_at=started_at,
                provider_id=context.provider_id,
                model_id=context.model_id or "model:p0_claim_stub",
                redacted_logs=[
                    "api_model_gateway deterministic claim stub completed "
                    "on control plane"
                ],
            )
        if not context.provider_token:
            error = normalize_backend_error(
                error_code="api_model_gateway.credentials_missing",
                error_message="API model gateway provider credential is not configured",
                retryable=False,
                fallbackable=True,
                details={"provider_id": context.provider_id or "default"},
            )
            return build_result_envelope(
                context=context,
                output={"ok": False, "reason": "credentials_missing"},
                usage_records=usage,
                started_at=started_at,
                status="failed",
                errors=[error],
                provider_id=context.provider_id,
                model_id=context.model_id,
                redacted_logs=["api_model_gateway credential lookup failed"],
            )

        output = repair_structured_output_stub(
            {
                "ok": True,
                "gateway": "api_model_gateway",
                "structured_output": {},
                "provider_call_executed": False,
                "control_plane_only": True,
            }
        )
        return build_result_envelope(
            context=context,
            output=output,
            usage_records=usage,
            started_at=started_at,
            provider_id=context.provider_id,
            model_id=context.model_id,
            redacted_logs=["api_model_gateway scaffold completed on control plane"],
        )


def _control_plane_boundary_error(context: BackendExecutionContext):
    if context.worker_id != CONTROL_PLANE_GATEWAY_WORKER_ID:
        return normalize_backend_error(
            error_code="api_model_gateway.worker_direct_denied",
            error_message="API model gateway must run through control-plane gateway",
            retryable=False,
            fallbackable=False,
            details={"worker_id": context.worker_id},
        )
    if context.capacity_node_id != CONTROL_PLANE_GATEWAY_NODE_ID:
        return normalize_backend_error(
            error_code="api_model_gateway.capacity_node_denied",
            error_message=(
                "API model gateway capacity node must be control-plane gateway"
            ),
            retryable=False,
            fallbackable=False,
            details={"capacity_node_id": context.capacity_node_id},
        )
    return None


DEFAULT_TOPIC_LABELS = [
    "engineering",
    "finance",
    "policy",
    "science",
    "general",
]
DEFAULT_CLAIM_TYPES = [
    "factual",
    "metric",
    "policy",
    "product",
    "other",
]


def _classify_topic_stub(payload: dict[str, Any]) -> dict[str, Any]:
    labels = _allowed_labels(payload)
    text = str(payload.get("text") or payload.get("content") or "").lower()
    keyword_map = [
        ("engineering", ("api", "code", "software", "database", "worker")),
        ("finance", ("cost", "revenue", "budget", "price", "market")),
        ("policy", ("policy", "regulation", "compliance", "governance")),
        ("science", ("research", "experiment", "paper", "science", "evidence")),
    ]
    selected = labels[0]
    confidence = 0.72
    for label, keywords in keyword_map:
        if label in labels and any(keyword in text for keyword in keywords):
            selected = label
            confidence = 0.88
            break
    return {
        "ok": True,
        "label": selected,
        "confidence": confidence,
        "allowed_labels": labels,
        "gateway": "api_model_gateway",
        "provider_call_executed": False,
        "control_plane_only": True,
        "deterministic_stub": True,
    }


def _allowed_labels(payload: dict[str, Any]) -> list[str]:
    value = payload.get("allowed_labels")
    if isinstance(value, list):
        labels = [
            item
            for item in value
            if isinstance(item, str) and item
        ]
        if labels:
            return labels
    return list(DEFAULT_TOPIC_LABELS)


def _extract_claims_stub(payload: dict[str, Any]) -> dict[str, Any]:
    source_id, text = _claim_source(payload)
    allowed_claim_types = _allowed_claim_types(payload)
    claim_type = _claim_type(text, allowed_claim_types)
    claim_text = _first_sentence(text)
    return {
        "ok": True,
        "claims": [
            {
                "claim_text": claim_text,
                "entity": _claim_entity(payload, claim_text),
                "claim_type": claim_type,
                "confidence": 0.86,
                "source_post_refs": [source_id],
                "evidence_hint": claim_text,
            }
        ],
        "source_ids": [source_id],
        "allowed_claim_types": allowed_claim_types,
        "gateway": "api_model_gateway",
        "provider_call_executed": False,
        "control_plane_only": True,
        "deterministic_stub": True,
    }


def _claim_source(payload: dict[str, Any]) -> tuple[str, str]:
    sources = payload.get("sources")
    if isinstance(sources, list):
        for source in sources:
            if not isinstance(source, dict):
                continue
            source_id = source.get("source_id") or source.get("id")
            text = source.get("text") or source.get("content")
            if isinstance(source_id, str) and source_id and isinstance(text, str):
                return source_id, text
    source_id = payload.get("source_id")
    text = payload.get("text") or payload.get("content")
    return (
        source_id if isinstance(source_id, str) and source_id else "src_claim_1",
        text if isinstance(text, str) and text else "No claim text provided.",
    )


def _allowed_claim_types(payload: dict[str, Any]) -> list[str]:
    value = payload.get("allowed_claim_types")
    if isinstance(value, list):
        claim_types = [
            item
            for item in value
            if isinstance(item, str) and item in DEFAULT_CLAIM_TYPES
        ]
        if claim_types:
            return claim_types
    return list(DEFAULT_CLAIM_TYPES)


def _claim_type(text: str, allowed_claim_types: list[str]) -> str:
    normalized = text.lower()
    preferred = "factual"
    if any(token in normalized for token in ("cost", "revenue", "price", "budget")):
        preferred = "metric"
    elif any(token in normalized for token in ("policy", "regulation", "compliance")):
        preferred = "policy"
    elif any(token in normalized for token in ("product", "api", "gateway", "model")):
        preferred = "product"
    return preferred if preferred in allowed_claim_types else allowed_claim_types[0]


def _first_sentence(text: str) -> str:
    stripped = " ".join(text.strip().split())
    if not stripped:
        return "No claim text provided."
    for separator in (". ", "! ", "? "):
        if separator in stripped:
            return stripped.split(separator, 1)[0].rstrip(".!?") + "."
    return stripped.rstrip(".!?") + "."


def _claim_entity(payload: dict[str, Any], claim_text: str) -> str:
    entity = payload.get("entity")
    if isinstance(entity, str) and entity:
        return entity
    for token in claim_text.replace(".", "").split():
        if token[:1].isupper() and token.lower() not in {"the", "a", "an"}:
            return token.strip(",;:")
    return "TokenBank"
