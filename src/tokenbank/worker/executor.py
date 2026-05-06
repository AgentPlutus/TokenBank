"""Minimal local_tool executor for WP6 plumbing."""

from __future__ import annotations

import json
from typing import Any

from tokenbank.backends.adapter import (
    BackendExecutionContext,
    adapter_for_backend_class,
)
from tokenbank.core.canonical import canonical_json_dumps
from tokenbank.models.result_envelope import WorkUnitResultEnvelope
from tokenbank.worker.sandbox import AssignmentSandbox

FORBIDDEN_BACKEND_CLASSES = {
    "account_pool",
    "api_model_gateway",
    "credential_broker",
    "external_seller",
    "oauth_proxy",
    "primary_model_gateway",
}


class LocalToolExecutor:
    def execute(
        self,
        *,
        assignment: dict[str, Any],
        sandbox: AssignmentSandbox,
    ) -> dict[str, Any]:
        return self.execute_envelope(assignment=assignment, sandbox=sandbox).output

    def execute_envelope(
        self,
        *,
        assignment: dict[str, Any],
        sandbox: AssignmentSandbox,
    ) -> WorkUnitResultEnvelope:
        backend_id = str(assignment.get("backend_id") or "")
        body = self._coerce_dict(assignment.get("body"))
        effective_constraints = self._coerce_dict(
            assignment.get("effective_constraints")
        )
        backend_class = str(
            assignment.get("backend_class")
            or body.get("backend_class")
            or effective_constraints.get("backend_class")
            or self._backend_class_from_id(backend_id)
        )
        if self._is_forbidden_backend(
            backend_id=backend_id,
            backend_class=backend_class,
        ):
            raise PermissionError("worker cannot call API model providers directly")

        context = self._execution_context(
            assignment=assignment,
            body=body,
            effective_constraints=effective_constraints,
            backend_id=backend_id,
            backend_class=backend_class,
        )
        envelope = adapter_for_backend_class(backend_class).execute(context)
        (sandbox.output_dir / "result.json").write_text(
            canonical_json_dumps(envelope.output),
            encoding="utf-8",
        )
        return envelope

    def _execution_context(
        self,
        *,
        assignment: dict[str, Any],
        body: dict[str, Any],
        effective_constraints: dict[str, Any],
        backend_id: str,
        backend_class: str,
    ) -> BackendExecutionContext:
        input_payload = self._coerce_dict(
            body.get("input")
            or effective_constraints.get("input")
            or effective_constraints.get("inline_input")
        )
        if not input_payload:
            url = self._extract_url(assignment)
            input_payload = {"url": url} if url else {}
        return BackendExecutionContext(
            work_unit_id=str(assignment["work_unit_id"]),
            run_id=str(
                body.get("run_id")
                or effective_constraints.get("run_id")
                or "run_worker_local"
            ),
            attempt_id=str(assignment["attempt_id"]),
            assignment_id=str(assignment["assignment_id"]),
            backend_id=backend_id,
            backend_class=backend_class or "local_tool",
            task_type=str(
                body.get("task_type")
                or effective_constraints.get("task_type")
                or "url_check"
            ),
            input_payload=input_payload,
            effective_constraints=effective_constraints,
            worker_id=str(assignment["worker_id"]),
            capacity_node_id=str(assignment.get("capacity_node_id") or ""),
        )

    def _extract_url(self, assignment: dict[str, Any]) -> str | None:
        body = assignment.get("body")
        if isinstance(body, dict):
            url = body.get("url")
            if isinstance(url, str):
                return url
        for key in ("effective_constraints", "effective_constraints_json", "body_json"):
            payload = self._coerce_dict(assignment.get(key))
            url = self._find_url(payload)
            if url is not None:
                return url
        return None

    def _coerce_dict(self, value: Any) -> dict[str, Any]:
        if isinstance(value, dict):
            return value
        if isinstance(value, str) and value:
            try:
                payload = json.loads(value)
            except json.JSONDecodeError:
                return {}
            return payload if isinstance(payload, dict) else {}
        return {}

    def _find_url(self, payload: dict[str, Any]) -> str | None:
        for key in ("url", "target_url"):
            value = payload.get(key)
            if isinstance(value, str):
                return value
        for key in ("input", "body", "effective_constraints"):
            value = payload.get(key)
            if isinstance(value, dict):
                nested = self._find_url(value)
                if nested is not None:
                    return nested
        return None

    def _is_forbidden_backend(self, *, backend_id: str, backend_class: str) -> bool:
        values = {backend_class, *backend_id.split(":")}
        return bool(FORBIDDEN_BACKEND_CLASSES.intersection(values))

    def _backend_class_from_id(self, backend_id: str) -> str:
        if "url_check" in backend_id:
            return "local_tool"
        if "local_script" in backend_id or "dedup" in backend_id:
            return "local_script"
        if "browser_fetch" in backend_id:
            return "browser_fetch"
        return "local_tool"
