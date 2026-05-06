"""Host-facing endpoint skeletons."""

from __future__ import annotations

import sqlite3
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, status

from tokenbank.app.deps import get_db, get_loaded_config, require_host_token
from tokenbank.app.routers.common import not_implemented
from tokenbank.app.security import AuthContext
from tokenbank.config_runtime.loader import LoadedConfig
from tokenbank.host.url_check import (
    get_host_result_summary,
    get_work_unit_status,
    submit_claim_extraction_work_unit,
    submit_dedup_work_unit,
    submit_topic_classification_work_unit,
    submit_url_check_work_unit,
    submit_webpage_extraction_work_unit,
)

router = APIRouter(
    prefix="/v0/host",
    tags=["host"],
    dependencies=[Depends(require_host_token)],
)


@router.get("/capabilities")
def host_capabilities(db: Annotated[sqlite3.Connection, Depends(get_db)]) -> dict:
    rows = db.execute(
        """
        SELECT capacity_node_id, node_type, status, allowed_task_types_json
        FROM capacity_nodes
        ORDER BY capacity_node_id
        """
    ).fetchall()
    return {
        "status": "ok",
        "capability_count": len(rows),
        "capacity_node_ids": [row["capacity_node_id"] for row in rows],
    }


@router.post("/work-units")
def submit_work_unit(
    _: Annotated[AuthContext, Depends(require_host_token)],
    payload: dict[str, Any],
    db: Annotated[sqlite3.Connection, Depends(get_db)],
    config: Annotated[LoadedConfig, Depends(get_loaded_config)],
) -> dict[str, Any]:
    task_type = payload.get("task_type")
    if task_type not in {
        "url_check",
        "dedup",
        "webpage_extraction",
        "topic_classification",
        "claim_extraction",
    }:
        return not_implemented("host.work_units.submit.unsupported_demo_task")
    inline_input = payload.get("inline_input", {})
    if not isinstance(inline_input, dict):
        inline_input = {}
    try:
        if task_type == "url_check":
            url = payload.get("url") or inline_input.get("url")
            if not isinstance(url, str) or not url:
                raise ValueError("url_check requires url")
            return submit_url_check_work_unit(db, loaded_config=config, url=url)

        items = payload.get("items") or inline_input.get("items")
        if task_type == "dedup":
            if not isinstance(items, list):
                raise ValueError("dedup requires items list")
            return submit_dedup_work_unit(db, loaded_config=config, items=items)

        if task_type == "topic_classification":
            text = payload.get("text") or inline_input.get("text")
            if not isinstance(text, str) or not text:
                raise ValueError("topic_classification requires text")
            allowed_labels = (
                payload.get("allowed_labels") or inline_input.get("allowed_labels")
            )
            if allowed_labels is not None and (
                not isinstance(allowed_labels, list)
                or not all(isinstance(label, str) and label for label in allowed_labels)
            ):
                raise ValueError(
                    "topic_classification allowed_labels must be a string list"
                )
            return submit_topic_classification_work_unit(
                db,
                loaded_config=config,
                text=text,
                allowed_labels=allowed_labels,
            )

        if task_type == "claim_extraction":
            text = payload.get("text") or inline_input.get("text")
            if not isinstance(text, str) or not text:
                raise ValueError("claim_extraction requires text")
            source_id = payload.get("source_id") or inline_input.get("source_id")
            if not isinstance(source_id, str) or not source_id:
                source_id = "src_claim_1"
            entity = payload.get("entity") or inline_input.get("entity")
            allowed_claim_types = (
                payload.get("allowed_claim_types")
                or inline_input.get("allowed_claim_types")
            )
            if allowed_claim_types is not None and (
                not isinstance(allowed_claim_types, list)
                or not all(
                    isinstance(claim_type, str) and claim_type
                    for claim_type in allowed_claim_types
                )
            ):
                raise ValueError(
                    "claim_extraction allowed_claim_types must be a string list"
                )
            return submit_claim_extraction_work_unit(
                db,
                loaded_config=config,
                text=text,
                source_id=source_id,
                entity=entity if isinstance(entity, str) else None,
                allowed_claim_types=allowed_claim_types,
            )

        url = payload.get("url") or inline_input.get("url")
        if not isinstance(url, str) or not url:
            raise ValueError("webpage_extraction requires url")
        html = payload.get("html") or inline_input.get("html")
        text = payload.get("text") or inline_input.get("text")
        title = payload.get("title") or inline_input.get("title")
        return submit_webpage_extraction_work_unit(
            db,
            loaded_config=config,
            url=url,
            html=html if isinstance(html, str) else None,
            text=text if isinstance(text, str) else None,
            title=title if isinstance(title, str) else None,
        )
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"error": str(exc)},
        ) from exc


@router.get("/work-units/{work_unit_id}/status")
def work_unit_status(
    work_unit_id: str,
    db: Annotated[sqlite3.Connection, Depends(get_db)],
) -> dict[str, Any]:
    current = get_work_unit_status(db, work_unit_id=work_unit_id)
    if current is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"error": "work_unit_not_found"},
        )
    return {"status": "ok", "work_unit": current}


@router.get("/work-units/{work_unit_id}/result")
def work_unit_result(
    work_unit_id: str,
    db: Annotated[sqlite3.Connection, Depends(get_db)],
) -> dict[str, Any]:
    summary = get_host_result_summary(db, work_unit_id=work_unit_id)
    if summary is None:
        return {
            "status": "pending",
            "work_unit_id": work_unit_id,
            "host_result_summary": None,
        }
    return {
        "status": "ok",
        "work_unit_id": work_unit_id,
        "host_result_summary": summary.model_dump(mode="json"),
    }


@router.post("/work-units/{work_unit_id}/cancel")
def cancel_work_unit(work_unit_id: str) -> dict[str, str]:
    response = not_implemented("host.work_units.cancel")
    response["work_unit_id"] = work_unit_id
    return response


@router.post("/routes/estimate")
def estimate_route(_: dict[str, Any] | None = None) -> dict[str, str]:
    return not_implemented("host.routes.estimate")


@router.get("/artifacts/{artifact_ref_id}")
def get_artifact(artifact_ref_id: str) -> dict[str, str]:
    response = not_implemented("host.artifacts.get")
    response["artifact_ref_id"] = artifact_ref_id
    return response


@router.get("/reports/{run_id}/summary")
def get_report_summary(
    run_id: str,
    db: Annotated[sqlite3.Connection, Depends(get_db)],
) -> dict[str, Any]:
    row = db.execute(
        """
        SELECT body_json
        FROM host_result_summaries
        WHERE run_id = ?
        ORDER BY created_at DESC
        LIMIT 1
        """,
        (run_id,),
    ).fetchone()
    if row is None:
        return {"status": "pending", "run_id": run_id, "host_result_summary": None}
    import json

    return {
        "status": "ok",
        "run_id": run_id,
        "host_result_summary": json.loads(row["body_json"]),
    }
