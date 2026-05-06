from __future__ import annotations

from tokenbank.backends.adapter import (
    BackendExecutionContext,
    adapter_for_backend_class,
)
from tokenbank.backends.api_model_gateway import APIModelGatewayAdapter
from tokenbank.backends.browser_fetch import BrowserFetchAdapter
from tokenbank.backends.local_script import LocalScriptAdapter
from tokenbank.backends.local_tool import LocalToolAdapter
from tokenbank.backends.primary_model_gateway import PrimaryModelGatewayAdapter
from tokenbank.capacity.validators import CONTROL_PLANE_GATEWAY_WORKER_ID


def context(
    *,
    backend_id: str = "backend:url_check:v0",
    backend_class: str = "local_tool",
    task_type: str = "url_check",
    input_payload: dict | None = None,
    effective_constraints: dict | None = None,
    worker_id: str | None = "wrk_demo_local",
    capacity_node_id: str | None = "capnode:worker:wrk_demo_local",
    provider_token: str | None = None,
) -> BackendExecutionContext:
    return BackendExecutionContext(
        work_unit_id=f"wu_{task_type}",
        run_id="run_backend_adapters",
        attempt_id="att_backend_adapters",
        assignment_id="asg_backend_adapters",
        backend_id=backend_id,
        backend_class=backend_class,
        task_type=task_type,
        input_payload=input_payload or {"url": "https://example.com/a?b=1"},
        effective_constraints=effective_constraints or {},
        worker_id=worker_id,
        capacity_node_id=capacity_node_id,
        provider_id="provider:p0_openai_compatible",
        model_id="model:p0_stub",
        provider_token=provider_token,
    )


def gateway_context(
    *,
    backend_id: str,
    backend_class: str,
    task_type: str = "claim_extraction",
    input_payload: dict | None = None,
    provider_token: str | None = None,
    worker_id: str | None = CONTROL_PLANE_GATEWAY_WORKER_ID,
) -> BackendExecutionContext:
    return context(
        backend_id=backend_id,
        backend_class=backend_class,
        task_type=task_type,
        input_payload=input_payload or {"text": "A claim appears here."},
        worker_id=worker_id,
        capacity_node_id=f"capnode:worker:{CONTROL_PLANE_GATEWAY_WORKER_ID}",
        provider_token=provider_token,
    )


def test_local_tool_url_check_success() -> None:
    envelope = LocalToolAdapter().execute(context())

    assert envelope.status == "succeeded"
    assert envelope.output["ok"] is True
    assert envelope.output["url"] == "https://example.com/a?b=1"
    assert envelope.output_hash
    assert envelope.result_hash
    assert envelope.backend_id == "backend:url_check:v0"


def test_local_tool_schema_invalid_or_bad_input() -> None:
    envelope = LocalToolAdapter().execute(context(input_payload={"url": "notaurl"}))

    assert envelope.status == "failed"
    assert envelope.backend_error is not None
    assert envelope.backend_error.error_code == "local_tool.bad_input"
    assert envelope.backend_error.retryable is False


def test_local_script_dedup_scaffold_or_hash_allowlist_behavior() -> None:
    envelope = LocalScriptAdapter().execute(
        context(
            backend_id="backend:dedup:local_script:v0",
            backend_class="local_script",
            task_type="dedup",
            input_payload={"items": ["a", "a", "b"]},
            effective_constraints={
                "script_hash": "sha256:allowed",
                "allowed_script_hashes": ["sha256:allowed"],
            },
        )
    )

    assert envelope.status == "succeeded"
    assert envelope.output["unique_items"] == ["a", "b"]
    assert envelope.output["duplicate_count"] == 1


def test_browser_fetch_redirect_denied_or_private_ip_denied() -> None:
    envelope = BrowserFetchAdapter().execute(
        context(
            backend_id="backend:webpage_extraction:browser_fetch:v0",
            backend_class="browser_fetch",
            task_type="webpage_extraction",
            input_payload={"url": "http://127.0.0.1/private"},
        )
    )

    assert envelope.status == "failed"
    assert envelope.backend_error is not None
    assert envelope.backend_error.error_code == "browser_fetch.private_ip_denied"
    assert envelope.backend_error.fallbackable is True


def test_api_gateway_missing_credentials_error() -> None:
    envelope = APIModelGatewayAdapter().execute(
        gateway_context(
            backend_id="backend:api_model_gateway:l1_structured",
            backend_class="api_model_gateway",
            task_type="structured_summary",
        )
    )

    assert envelope.status == "failed"
    assert envelope.backend_error is not None
    assert envelope.backend_error.error_code == "api_model_gateway.credentials_missing"
    assert envelope.cost_source == "estimated"
    assert envelope.cost_confidence == "low"


def test_api_gateway_claim_extraction_stub_success() -> None:
    envelope = APIModelGatewayAdapter().execute(
        gateway_context(
            backend_id="backend:claim_extraction:api_gateway:v0",
            backend_class="api_model_gateway",
            input_payload={
                "text": "TokenBank routes private capacity through a gateway.",
                "source_id": "src_backend_claim_1",
            },
        )
    )

    assert envelope.status == "succeeded"
    assert envelope.output["provider_call_executed"] is False
    assert envelope.output["claims"][0]["source_post_refs"] == [
        "src_backend_claim_1"
    ]


def test_api_gateway_no_worker_direct_call() -> None:
    envelope = APIModelGatewayAdapter().execute(
        gateway_context(
            backend_id="backend:claim_extraction:api_gateway:v0",
            backend_class="api_model_gateway",
            worker_id="wrk_demo_local",
        )
    )

    assert envelope.status == "failed"
    assert envelope.backend_error is not None
    assert envelope.backend_error.error_code == "api_model_gateway.worker_direct_denied"


def test_primary_gateway_missing_credentials_error() -> None:
    envelope = PrimaryModelGatewayAdapter().execute(
        gateway_context(
            backend_id="backend:claim_extraction:primary_gateway:v0",
            backend_class="primary_model_gateway",
        )
    )

    assert envelope.status == "failed"
    assert envelope.backend_error is not None
    assert envelope.backend_error.error_code == (
        "primary_model_gateway.credentials_missing"
    )
    assert envelope.backend_error.fallbackable is True


def test_result_envelope_has_output_hash_and_result_hash() -> None:
    envelope = LocalToolAdapter().execute(context())

    assert len(envelope.output_hash) == 64
    assert len(envelope.result_hash) == 64


def test_usage_record_cost_source_zero_internal_for_local_tool() -> None:
    envelope = LocalToolAdapter().execute(context())

    assert envelope.usage_records[0].cost_source == "zero_internal_phase0"
    assert envelope.usage_records[0].cost_confidence == "high"
    assert envelope.actual_cost_micros == 0


def test_backend_error_retryable_fallbackable_fields() -> None:
    envelope = BrowserFetchAdapter().execute(
        context(
            backend_id="backend:webpage_extraction:browser_fetch:v0",
            backend_class="browser_fetch",
            task_type="webpage_extraction",
            input_payload={
                "url": "https://example.com/start",
                "redirect_url": "https://example.net/next",
            },
        )
    )

    assert envelope.backend_error is not None
    assert envelope.backend_error.retryable is False
    assert envelope.backend_error.fallbackable is True


def test_unknown_backend_unsupported_backend_error() -> None:
    envelope = adapter_for_backend_class("unknown_backend").execute(
        context(
            backend_id="backend:unknown:v0",
            backend_class="unknown_backend",
            task_type="unknown_task",
        )
    )

    assert envelope.status == "failed"
    assert envelope.backend_error is not None
    assert envelope.backend_error.error_code == "backend.unsupported"
