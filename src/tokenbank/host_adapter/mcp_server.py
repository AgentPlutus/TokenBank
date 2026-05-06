"""Minimal WP12 MCP stdio server wrapper around HostAdapterCore."""

from __future__ import annotations

import sys
from typing import Any, TextIO

from tokenbank.core.canonical import canonical_json_dumps
from tokenbank.host_adapter.core import HostAdapterCore

MCP_TOOL_NAMES = (
    "tokenbank_list_capabilities",
    "tokenbank_estimate",
    "tokenbank_submit",
    "tokenbank_get_result",
    "tokenbank_cancel",
    "tokenbank_get_routebook_excerpt",
    "tokenbank_get_route_explanation",
    "tokenbank_get_task_analysis",
    "tokenbank_get_route_score",
)


class MCPStdioServer:
    """Line-delimited JSON-RPC stdio stub for early MCP validation."""

    def __init__(self, core: HostAdapterCore | None = None):
        self.core = core or HostAdapterCore()

    def tool_definitions(self) -> list[dict[str, Any]]:
        """Return the bounded MCP surface."""
        return [
            _tool(
                "tokenbank_list_capabilities",
                "List Private Agent Capacity Network capabilities and caveats.",
                input_schema={"type": "object", "properties": {}},
                output_schema={"type": "object"},
            ),
            _tool(
                "tokenbank_estimate",
                "Estimate a schema-bound Work Unit route without scheduling.",
                input_schema=_task_input_schema(),
                output_schema={"type": "object"},
            ),
            _tool(
                "tokenbank_submit",
                "Submit a schema-bound Work Unit through HostAdapterCore.",
                input_schema={
                    **_task_input_schema(),
                    "properties": {
                        **_task_input_schema()["properties"],
                        "wait": {
                            "type": "boolean",
                            "description": "P0 accepts but does not execute directly.",
                            "default": False,
                        },
                    },
                },
                output_schema={"type": "object"},
            ),
            _tool(
                "tokenbank_get_result",
                "Return HostResultSummary for a Work Unit when available.",
                input_schema=_work_unit_id_schema(),
                output_schema={"type": "object"},
            ),
            _tool(
                "tokenbank_cancel",
                "Return P0 cancel status for a Work Unit.",
                input_schema=_work_unit_id_schema(),
                output_schema={"type": "object"},
            ),
            _tool(
                "tokenbank_get_routebook_excerpt",
                "Return a bounded routebook excerpt for supported task types.",
                input_schema={
                    "type": "object",
                    "properties": {
                        "task_type": {
                            "type": "string",
                            "description": "Optional supported task type.",
                        },
                    },
                    "additionalProperties": False,
                },
                output_schema={"type": "object"},
            ),
            _tool(
                "tokenbank_get_route_explanation",
                "Return a bounded Routebook V1 explanation without scheduling.",
                input_schema=_task_input_schema(),
                output_schema={"type": "object"},
            ),
            _tool(
                "tokenbank_get_task_analysis",
                "Return deterministic TaskAnalysisReport without scheduling.",
                input_schema=_task_input_schema(),
                output_schema={"type": "object"},
            ),
            _tool(
                "tokenbank_get_route_score",
                "Return WP-RB3 RouteScoringReport without scheduling.",
                input_schema=_task_input_schema(),
                output_schema={"type": "object"},
            ),
        ]

    def call_tool(self, name: str, arguments: dict[str, Any] | None = None) -> dict:
        """Call one bounded MCP tool."""
        args = arguments or {}
        if name not in MCP_TOOL_NAMES:
            raise ValueError(f"unknown MCP tool: {name}")
        if name == "tokenbank_list_capabilities":
            return self.core.list_capabilities()
        if name == "tokenbank_estimate":
            return self.core.estimate_route(
                task_type=_optional_task_type(args),
                input_payload=_input_payload(args),
            )
        if name == "tokenbank_submit":
            return self.core.submit_work_unit(
                task_type=_optional_task_type(args),
                input_payload=_input_payload(args),
                wait=bool(args.get("wait", False)),
            )
        if name == "tokenbank_get_result":
            return self.core.get_work_unit_result(
                work_unit_id=_required_work_unit_id(args)
            )
        if name == "tokenbank_cancel":
            return self.core.cancel_work_unit(work_unit_id=_required_work_unit_id(args))
        if name == "tokenbank_get_route_explanation":
            return self.core.explain_route(
                task_type=_optional_task_type(args),
                input_payload=_input_payload(args),
            )
        if name == "tokenbank_get_task_analysis":
            return self.core.analyze_route(
                task_type=_optional_task_type(args),
                input_payload=_input_payload(args),
            )
        if name == "tokenbank_get_route_score":
            return self.core.score_route(
                task_type=_optional_task_type(args),
                input_payload=_input_payload(args),
            )
        return self.core.get_routebook_excerpt(
            task_type=args.get("task_type")
            if isinstance(args.get("task_type"), str)
            else None
        )

    def handle_request(self, request: dict[str, Any]) -> dict[str, Any] | None:
        """Handle one JSON-RPC request object."""
        request_id = request.get("id")
        method = request.get("method")
        if isinstance(method, str) and method.startswith("notifications/"):
            return None
        try:
            if method == "initialize":
                return _result(
                    request_id,
                    {
                        "protocolVersion": "2024-11-05",
                        "serverInfo": {
                            "name": "tokenbank",
                            "version": "0.1.0",
                        },
                        "capabilities": {"tools": {}},
                    },
                )
            if method == "tools/list":
                return _result(request_id, {"tools": self.tool_definitions()})
            if method == "tools/call":
                params = request.get("params")
                if not isinstance(params, dict):
                    raise ValueError("tools/call params must be an object")
                name = params.get("name")
                if not isinstance(name, str):
                    raise ValueError("tools/call name is required")
                arguments = params.get("arguments")
                if arguments is not None and not isinstance(arguments, dict):
                    raise ValueError("tools/call arguments must be an object")
                structured = self.call_tool(name, arguments)
                return _result(
                    request_id,
                    {
                        "content": [
                            {
                                "type": "text",
                                "text": canonical_json_dumps(structured),
                            }
                        ],
                        "structuredContent": structured,
                        "isError": False,
                    },
                )
            if method in {"resources/list", "resources/read"}:
                return _error(
                    request_id,
                    code=-32601,
                    message="MCP resources are not exposed by the Phase 0 stub",
                )
            return _error(request_id, code=-32601, message="method not found")
        except Exception as exc:
            return _error(request_id, code=-32000, message=str(exc))

    def serve(
        self,
        *,
        stdin: TextIO = sys.stdin,
        stdout: TextIO = sys.stdout,
    ) -> None:
        """Serve line-delimited JSON-RPC over stdio."""
        import json

        for line in stdin:
            line = line.strip()
            if not line:
                continue
            response = self.handle_request(json.loads(line))
            if response is None:
                continue
            stdout.write(canonical_json_dumps(response) + "\n")
            stdout.flush()


def _tool(
    name: str,
    description: str,
    *,
    input_schema: dict[str, Any],
    output_schema: dict[str, Any],
) -> dict[str, Any]:
    return {
        "name": name,
        "description": description,
        "inputSchema": input_schema,
        "outputSchema": output_schema,
    }


def _task_input_schema() -> dict[str, Any]:
    return {
        "type": "object",
        "properties": {
            "task_type": {
                "type": "string",
                "enum": [
                    "url_check",
                    "dedup",
                    "webpage_extraction",
                    "topic_classification",
                    "claim_extraction",
                ],
            },
            "input": {
                "type": "object",
                "description": "Explicit Work Unit input object.",
            },
        },
        "required": ["task_type", "input"],
        "additionalProperties": False,
    }


def _work_unit_id_schema() -> dict[str, Any]:
    return {
        "type": "object",
        "properties": {
            "work_unit_id": {
                "type": "string",
                "description": "TokenBank Work Unit id.",
            },
        },
        "required": ["work_unit_id"],
        "additionalProperties": False,
    }


def _optional_task_type(args: dict[str, Any]) -> str | None:
    value = args.get("task_type")
    return value if isinstance(value, str) else None


def _input_payload(args: dict[str, Any]) -> dict[str, Any] | list[Any] | None:
    value = args.get("input")
    if isinstance(value, dict | list):
        return value
    return None


def _required_work_unit_id(args: dict[str, Any]) -> str:
    work_unit_id = args.get("work_unit_id")
    if not isinstance(work_unit_id, str) or not work_unit_id:
        raise ValueError("work_unit_id is required")
    return work_unit_id


def _result(request_id: Any, result: dict[str, Any]) -> dict[str, Any]:
    return {"jsonrpc": "2.0", "id": request_id, "result": result}


def _error(request_id: Any, *, code: int, message: str) -> dict[str, Any]:
    return {
        "jsonrpc": "2.0",
        "id": request_id,
        "error": {"code": code, "message": message},
    }
