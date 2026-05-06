from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from tokenbank.backends.adapter import BackendExecutionContext, build_result_envelope
from tokenbank.backends.local_tool import LocalToolAdapter
from tokenbank.backends.usage import make_usage_record
from tokenbank.models.result_envelope import WorkUnitResultEnvelope
from tokenbank.verifier.recipes import load_all_verifier_recipes
from tokenbank.verifier.runner import VerifierRunner


def context(
    *,
    task_type: str,
    backend_id: str = "backend:test:v0",
    backend_class: str = "local_tool",
) -> BackendExecutionContext:
    return BackendExecutionContext(
        work_unit_id=f"wu_{task_type}",
        run_id="run_verifier",
        attempt_id="att_verifier",
        assignment_id="asg_verifier",
        backend_id=backend_id,
        backend_class=backend_class,
        task_type=task_type,
        input_payload={},
        worker_id="wrk_demo_local",
        capacity_node_id="capnode:worker:wrk_demo_local",
    )


def envelope_for(
    *,
    recipe_id: str,
    task_type: str,
    output: dict[str, Any],
    backend_id: str = "backend:test:v0",
    backend_class: str = "local_tool",
) -> WorkUnitResultEnvelope:
    ctx = context(
        task_type=task_type,
        backend_id=backend_id,
        backend_class=backend_class,
    )
    usage = [
        make_usage_record(
            work_unit_id=ctx.work_unit_id,
            attempt_id=ctx.attempt_id,
            backend_id=ctx.backend_id,
            cost_source="zero_internal_phase0",
            cost_confidence="high",
        )
    ]
    return build_result_envelope(
        context=ctx,
        output=output,
        usage_records=usage,
        started_at=datetime.now(UTC),
    )


def verify(recipe_id: str, envelope: WorkUnitResultEnvelope):
    return VerifierRunner.for_recipe_id(recipe_id).run(result_envelope=envelope)


def test_url_200_accept() -> None:
    report = verify(
        "url_check_v0",
        envelope_for(
            recipe_id="url_check_v0",
            task_type="url_check",
            output={"ok": True, "status_code": 200, "final_url": "https://example.com"},
        ),
    )

    assert report.recommendation == "accept"
    assert report.metadata["deterministic_status"] == "passed"


def test_url_404_accept_or_warning_according_to_recipe() -> None:
    report = verify(
        "url_check_v0",
        envelope_for(
            recipe_id="url_check_v0",
            task_type="url_check",
            output={"ok": False, "status_code": 404, "final_url": "https://example.com"},
        ),
    )

    assert report.recommendation == "accept_with_warning"
    assert report.status == "needs_review"


def test_url_timeout_retry() -> None:
    report = verify(
        "url_check_v0",
        envelope_for(
            recipe_id="url_check_v0",
            task_type="url_check",
            output={"ok": False, "timed_out": True},
        ),
    )

    assert report.recommendation == "retry"


def test_url_private_ip_or_redirect_quarantine() -> None:
    report = verify(
        "url_check_v0",
        envelope_for(
            recipe_id="url_check_v0",
            task_type="url_check",
            output={"ok": False, "private_ip_denied": True},
        ),
    )

    assert report.recommendation == "quarantine"


def test_result_hash_mismatch_quarantine() -> None:
    envelope = envelope_for(
        recipe_id="url_check_v0",
        task_type="url_check",
        output={"ok": True, "status_code": 200},
    ).model_copy(update={"result_hash": "bad_result_hash"})

    report = verify("url_check_v0", envelope)

    assert report.recommendation == "quarantine"


def test_output_hash_missing_reject() -> None:
    envelope = envelope_for(
        recipe_id="url_check_v0",
        task_type="url_check",
        output={"ok": True, "status_code": 200},
    ).model_copy(update={"output_hash": ""})

    report = verify("url_check_v0", envelope)

    assert report.recommendation == "reject"


def test_schema_invalid_retry_or_reject() -> None:
    report = verify(
        "url_check_v0",
        envelope_for(
            recipe_id="url_check_v0",
            task_type="url_check",
            output={"status_code": 200},
        ),
    )

    assert report.recommendation == "retry"


def test_dedup_exact_accept() -> None:
    report = verify(
        "dedup_v0",
        envelope_for(
            recipe_id="dedup_v0",
            task_type="dedup",
            backend_class="local_script",
            output={"unique_items": ["a", "b"], "duplicate_count": 1},
        ),
    )

    assert report.recommendation == "accept"


def test_dedup_overmerge_reject_or_warning() -> None:
    report = verify(
        "dedup_v0",
        envelope_for(
            recipe_id="dedup_v0",
            task_type="dedup",
            backend_class="local_script",
            output={
                "unique_items": ["merged"],
                "duplicate_count": 2,
                "overmerge_detected": True,
            },
        ),
    )

    assert report.recommendation == "accept_with_warning"


def test_topic_label_not_enum_retry() -> None:
    report = verify(
        "topic_classification_v0",
        envelope_for(
            recipe_id="topic_classification_v0",
            task_type="topic_classification",
            backend_class="api_model_gateway",
            output={
                "label": "unknown",
                "confidence": 0.9,
                "allowed_labels": ["finance", "science"],
            },
        ),
    )

    assert report.recommendation == "retry"


def test_topic_low_conf_warning() -> None:
    report = verify(
        "topic_classification_v0",
        envelope_for(
            recipe_id="topic_classification_v0",
            task_type="topic_classification",
            backend_class="api_model_gateway",
            output={
                "label": "science",
                "confidence": 0.4,
                "allowed_labels": ["finance", "science"],
            },
        ),
    )

    assert report.recommendation == "accept_with_warning"


def test_claim_missing_entity_retry_or_reject() -> None:
    report = verify(
        "claim_extraction_v0",
        envelope_for(
            recipe_id="claim_extraction_v0",
            task_type="claim_extraction",
            backend_class="api_model_gateway",
            output={"claims": [{"source_ref": "src_1", "text": "claim"}]},
        ),
    )

    assert report.recommendation == "retry"


def test_claim_missing_source_ref_fallback_or_reject() -> None:
    report = verify(
        "claim_extraction_v0",
        envelope_for(
            recipe_id="claim_extraction_v0",
            task_type="claim_extraction",
            backend_class="api_model_gateway",
            output={"claims": [{"entity": "TokenBank", "text": "claim"}]},
        ),
    )

    assert report.recommendation == "fallback"


def test_webpage_empty_retry_or_fallback() -> None:
    report = verify(
        "webpage_extraction_v0",
        envelope_for(
            recipe_id="webpage_extraction_v0",
            task_type="webpage_extraction",
            backend_class="browser_fetch",
            output={"extracted": {}},
        ),
    )

    assert report.recommendation == "fallback"


def test_webpage_prompt_injection_warning() -> None:
    report = verify(
        "webpage_extraction_v0",
        envelope_for(
            recipe_id="webpage_extraction_v0",
            task_type="webpage_extraction",
            backend_class="browser_fetch",
            output={
                "extracted": {"title": "Example"},
                "prompt_injection_detected": True,
            },
        ),
    )

    assert report.recommendation == "accept_with_warning"


def test_secret_output_quarantine() -> None:
    report = verify(
        "url_check_v0",
        envelope_for(
            recipe_id="url_check_v0",
            task_type="url_check",
            output={"ok": True, "status_code": 200, "debug": "sk-test-secret"},
        ),
    )

    assert report.recommendation == "quarantine"
    assert report.metadata["safety_status"] == "failed"


def test_local_tool_adapter_url_check_validates() -> None:
    envelope = LocalToolAdapter().execute(
        BackendExecutionContext(
            work_unit_id="wu_url_check",
            run_id="run_url_check",
            attempt_id="att_url_check",
            assignment_id="asg_url_check",
            backend_id="backend:url_check:v0",
            backend_class="local_tool",
            task_type="url_check",
            input_payload={"url": "https://example.com"},
            worker_id="wrk_demo_local",
            capacity_node_id="capnode:worker:wrk_demo_local",
        )
    )

    report = verify("url_check_v0", envelope)

    assert report.recommendation == "accept"


def test_all_five_verifier_recipes_load() -> None:
    recipes = load_all_verifier_recipes()

    assert set(recipes) == {
        "claim_extraction_v0",
        "dedup_v0",
        "topic_classification_v0",
        "url_check_v0",
        "webpage_extraction_v0",
    }
