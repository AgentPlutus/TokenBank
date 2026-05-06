from __future__ import annotations

from pathlib import Path

from tokenbank.backends.adapter import BackendExecutionContext
from tokenbank.backends.api_model_gateway import APIModelGatewayAdapter
from tokenbank.backends.errors import normalize_backend_error
from tokenbank.capacity.validators import CONTROL_PLANE_GATEWAY_WORKER_ID
from tokenbank.core.canonical import canonical_json_dumps

REPO_ROOT = Path(__file__).resolve().parents[2]


def test_credential_not_serialized() -> None:
    secret = "sk-test-secret-token"
    context = BackendExecutionContext(
        work_unit_id="wu_secret",
        run_id="run_secret",
        attempt_id="att_secret",
        assignment_id="asg_secret",
        backend_id="backend:claim_extraction:api_gateway:v0",
        backend_class="api_model_gateway",
        task_type="claim_extraction",
        input_payload={"text": "claim"},
        worker_id=CONTROL_PLANE_GATEWAY_WORKER_ID,
        capacity_node_id=f"capnode:worker:{CONTROL_PLANE_GATEWAY_WORKER_ID}",
        provider_id="provider:p0_openai_compatible",
        model_id="model:p0_stub",
        provider_token=secret,
    )

    envelope = APIModelGatewayAdapter().execute(context)
    serialized = canonical_json_dumps(envelope.model_dump(mode="json"))

    assert secret not in serialized
    assert "provider_token" not in serialized


def test_backend_error_redacts_secret_details() -> None:
    error = normalize_backend_error(
        error_code="credential.test",
        error_message="redaction test",
        details={"provider_token": "sk-test-secret-token"},
    )
    serialized = canonical_json_dumps(error.model_dump(mode="json"))

    assert "sk-test-secret-token" not in serialized
    assert "[REDACTED_SECRET]" in serialized


def test_no_openai_compatible_proxy_endpoint() -> None:
    source_text = "\n".join(
        path.read_text(encoding="utf-8")
        for path in (REPO_ROOT / "src").rglob("*.py")
    )

    forbidden_endpoint_markers = [
        '@app.post("/v1/chat/completions"',
        '@app.route("/v1/chat/completions"',
        '"/v1/chat/completions"',
        "'/v1/chat/completions'",
    ]
    for marker in forbidden_endpoint_markers:
        assert marker not in source_text
