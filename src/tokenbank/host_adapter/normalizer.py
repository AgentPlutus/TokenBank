"""Ingress normalizer for explicit HostAdapter Work Unit requests."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from tokenbank.host.url_check import SUPPORTED_DEMO_TASKS


class HostAdapterInputError(ValueError):
    """Raised when host input is outside the Phase 0 ingress boundary."""


@dataclass(frozen=True)
class NormalizedWorkUnitRequest:
    task_type: str
    inline_input: dict[str, Any]


CREDENTIAL_KEY_FRAGMENTS = (
    "api_key",
    "apikey",
    "oauth",
    "cookie",
    "credential",
    "provider_secret",
    "provider_token",
    "access_token",
    "refresh_token",
    "bearer",
)
MODEL_PROXY_TASK_TYPES = {
    "chat_completion",
    "chat_completions",
    "completion",
    "completions",
    "response",
    "responses",
    "model_proxy",
}
MODEL_PROXY_FIELD_KEYS = {
    "messages",
    "model",
    "prompt",
    "temperature",
    "top_p",
    "max_tokens",
    "stream",
}


def normalize_submit_request(
    *,
    task_type: str | None,
    payload: dict[str, Any] | list[Any] | None,
) -> NormalizedWorkUnitRequest:
    """Normalize explicit host input into supported Phase 0 task payloads."""
    normalized_task_type = _normalized_task_type(task_type, payload)
    if normalized_task_type in MODEL_PROXY_TASK_TYPES:
        raise HostAdapterInputError(
            "HostAdapter accepts Work Units, not model proxy requests"
        )
    if normalized_task_type not in SUPPORTED_DEMO_TASKS:
        raise HostAdapterInputError(f"unsupported task_type: {normalized_task_type}")

    payload_dict = _coerce_payload_dict(normalized_task_type, payload)
    reject_forbidden_host_input(payload_dict)
    _reject_model_proxy_shape(payload_dict)

    return NormalizedWorkUnitRequest(
        task_type=normalized_task_type,
        inline_input=_normalize_inline_input(normalized_task_type, payload_dict),
    )


def reject_forbidden_host_input(value: Any, path: tuple[str, ...] = ()) -> None:
    """Reject credential-like fields anywhere in host-provided input."""
    if isinstance(value, dict):
        for key, nested in value.items():
            key_text = str(key)
            normalized_key = key_text.lower().replace("-", "_")
            if any(
                fragment in normalized_key
                for fragment in CREDENTIAL_KEY_FRAGMENTS
            ):
                raise HostAdapterInputError(
                    "HostAdapter input must not include credentials, OAuth, "
                    "cookies, or provider secrets"
                )
            reject_forbidden_host_input(nested, (*path, key_text))
        return

    if isinstance(value, list):
        for index, item in enumerate(value):
            reject_forbidden_host_input(item, (*path, str(index)))


def _normalized_task_type(
    task_type: str | None,
    payload: dict[str, Any] | list[Any] | None,
) -> str:
    if task_type is not None:
        return task_type.strip()
    if isinstance(payload, dict) and isinstance(payload.get("task_type"), str):
        return str(payload["task_type"]).strip()
    raise HostAdapterInputError("task_type is required")


def _coerce_payload_dict(
    task_type: str,
    payload: dict[str, Any] | list[Any] | None,
) -> dict[str, Any]:
    if isinstance(payload, dict):
        inline_input = payload.get("inline_input")
        if isinstance(inline_input, dict):
            merged = dict(inline_input)
            merged.update(
                {
                    key: value
                    for key, value in payload.items()
                    if key not in {"inline_input", "task_type"}
                }
            )
            return merged
        input_payload = payload.get("input")
        if isinstance(input_payload, dict):
            merged = dict(input_payload)
            merged.update(
                {
                    key: value
                    for key, value in payload.items()
                    if key not in {"input", "task_type"}
                }
            )
            return merged
        return {
            key: value
            for key, value in payload.items()
            if key not in {"task_type", "wait"}
        }
    if isinstance(payload, list) and task_type == "dedup":
        return {"items": payload}
    return {}


def _reject_model_proxy_shape(payload: dict[str, Any]) -> None:
    keys = {str(key).lower().replace("-", "_") for key in payload}
    if MODEL_PROXY_FIELD_KEYS.intersection(keys):
        raise HostAdapterInputError(
            "HostAdapter submit creates Work Units; it is not a model proxy"
        )


def _normalize_inline_input(task_type: str, payload: dict[str, Any]) -> dict[str, Any]:
    if task_type == "url_check":
        return {"url": _required_string(payload, "url")}
    if task_type == "dedup":
        items = payload.get("items")
        if not isinstance(items, list):
            raise HostAdapterInputError("dedup requires items as a JSON array")
        return {"items": items}
    if task_type == "webpage_extraction":
        inline_input: dict[str, Any] = {"url": _required_string(payload, "url")}
        for key in ("html", "text", "title"):
            value = payload.get(key)
            if isinstance(value, str):
                inline_input[key] = value
        return inline_input
    if task_type == "topic_classification":
        inline_input = {"text": _required_string(payload, "text")}
        allowed_labels = _optional_string_list(payload, "allowed_labels")
        if allowed_labels is not None:
            inline_input["allowed_labels"] = allowed_labels
        return inline_input
    if task_type == "claim_extraction":
        inline_input = {
            "text": _required_string(payload, "text"),
            "source_id": _optional_string(payload, "source_id") or "src_claim_1",
        }
        source_id = inline_input["source_id"]
        inline_input["sources"] = [
            {"source_id": source_id, "text": inline_input["text"]}
        ]
        entity = _optional_string(payload, "entity")
        if entity is not None:
            inline_input["entity"] = entity
        allowed_claim_types = _optional_string_list(payload, "allowed_claim_types")
        if allowed_claim_types is not None:
            inline_input["allowed_claim_types"] = allowed_claim_types
        return inline_input
    raise HostAdapterInputError(f"unsupported task_type: {task_type}")


def _required_string(payload: dict[str, Any], key: str) -> str:
    value = payload.get(key)
    if not isinstance(value, str) or not value:
        raise HostAdapterInputError(f"{key} is required")
    return value


def _optional_string(payload: dict[str, Any], key: str) -> str | None:
    value = payload.get(key)
    if value is None:
        return None
    if not isinstance(value, str) or not value:
        raise HostAdapterInputError(f"{key} must be a non-empty string")
    return value


def _optional_string_list(payload: dict[str, Any], key: str) -> list[str] | None:
    value = payload.get(key)
    if value is None:
        return None
    if not isinstance(value, list) or not all(
        isinstance(item, str) and item for item in value
    ):
        raise HostAdapterInputError(f"{key} must be a JSON string array")
    return value
