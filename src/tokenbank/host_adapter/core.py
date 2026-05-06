"""HostAdapterCore ingress for CLI and MCP Work Unit submission."""

from __future__ import annotations

import json
import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import Any

from tokenbank import PHASE_0_NAME, PRODUCT_NAME
from tokenbank.accounts import AccountRegistry, build_manual_account_snapshot
from tokenbank.app.bootstrap import rebuild_capacity_projection_from_config_and_db
from tokenbank.audit import AuditReceiptRepository
from tokenbank.backends.registry import BackendRegistry
from tokenbank.capacity.discovery import discover_capacity_nodes
from tokenbank.config_runtime.loader import LoadedConfig, load_config_dir
from tokenbank.core.canonical import canonical_json_hash
from tokenbank.db.bootstrap import initialize_database
from tokenbank.host.url_check import (
    SUPPORTED_DEMO_TASKS,
    get_host_result_summary,
    get_work_unit_status,
    submit_claim_extraction_work_unit,
    submit_dedup_work_unit,
    submit_topic_classification_work_unit,
    submit_url_check_work_unit,
    submit_webpage_extraction_work_unit,
)
from tokenbank.host_adapter.normalizer import (
    HostAdapterInputError,
    NormalizedWorkUnitRequest,
    normalize_submit_request,
    reject_forbidden_host_input,
)
from tokenbank.host_adapter.summaries import host_result_response, routebook_excerpt
from tokenbank.ledger import UsageLedgerRepository
from tokenbank.models.route_decision import RouteScoringReport
from tokenbank.models.route_plan import RouteCandidate, RoutePlan
from tokenbank.models.work_unit import WorkUnit
from tokenbank.observability.report_generator import generate_cost_quality_report
from tokenbank.routebook.loader import load_routebook_dir
from tokenbank.router.route_explainer import RouteExplainer
from tokenbank.router.route_scorer import apply_scored_selection
from tokenbank.router.service import RouterService
from tokenbank.router.task_analyzer import TaskAnalyzer


class HostAdapterCore:
    """Core ingress shared by CLI and MCP.

    The adapter accepts explicit URLs, JSON inputs, or inline text and creates
    Work Units through the existing Router/Policy/Scheduler path. It does not
    execute backend work and does not expose workspace resources.
    """

    def __init__(
        self,
        *,
        config_dir: str | Path = "config",
        db_path: str | Path = ".tokenbank/tokenbank.db",
        routebook_dir: str | Path | None = None,
    ):
        self.config_dir = Path(config_dir)
        self.db_path = Path(db_path)
        self.routebook_dir = (
            Path(routebook_dir) if routebook_dir is not None else None
        )

    def list_capabilities(self) -> dict[str, Any]:
        """List Phase 0 private capacity and host-agent usage boundaries."""
        with self._control_plane_context() as (conn, _loaded_config):
            nodes = discover_capacity_nodes(conn)
        return {
            "status": "ok",
            "product": PRODUCT_NAME,
            "capacity_network": PHASE_0_NAME,
            "supported_task_types": sorted(SUPPORTED_DEMO_TASKS),
            "capacity_node_count": len(nodes),
            "capacity_nodes": nodes,
            "when_to_use": [
                "Submit schema-bound Work Units to private local or "
                "control-plane capacity.",
                "Route verifiable subtasks such as url_check, dedup, "
                "webpage_extraction, topic_classification, and claim_extraction.",
            ],
            "when_not_to_use": [
                "Do not use as a model proxy or final-answer writer.",
                "Do not pass credentials, OAuth tokens, cookies, or API keys.",
                "Do not ask it to scan a workspace or read arbitrary files.",
            ],
            "caveats": [
                "Phase 0 MCP is a narrow stdio stub.",
                "External provider calls are not executed by this adapter.",
                "Local zero-cost accounting uses zero_internal_phase0 caveats.",
            ],
        }

    def estimate_route(
        self,
        *,
        task_type: str | None,
        input_payload: dict[str, Any] | list[Any] | None = None,
        routebook_v1_dir: str | Path = "packs/base-routing/routebook",
    ) -> dict[str, Any]:
        """Return a deterministic RoutePlan estimate without scheduling work."""
        request = normalize_submit_request(
            task_type=task_type,
            payload=input_payload,
        )
        loaded_config = load_config_dir(self.config_dir)
        work_unit = self._estimate_work_unit(request)
        route_plan = RouterService.from_dirs(
            config_dir=loaded_config.root,
            routebook_dir=self._routebook_root(loaded_config),
        ).plan_route(work_unit.model_dump(mode="json"))
        task_analysis_report = TaskAnalyzer.from_dirs(
            config_dir=loaded_config.root,
            routebook_v1_dir=routebook_v1_dir,
        ).analyze(work_unit=work_unit, route_plan=route_plan)
        explanation = RouteExplainer.from_dirs(
            config_dir=loaded_config.root,
            routebook_dir=self._routebook_root(loaded_config),
            routebook_v1_dir=routebook_v1_dir,
        ).explain(
            work_unit=work_unit,
            route_plan=route_plan,
            task_analysis_report=task_analysis_report,
        )
        if "route_scoring_report" in explanation:
            route_plan = apply_scored_selection(
                route_plan=route_plan,
                scoring_report=RouteScoringReport.model_validate(
                    explanation["route_scoring_report"]
                ),
            )
        selected_candidate = _selected_candidate(route_plan)
        backend = BackendRegistry.from_config(loaded_config).get(
            selected_candidate.backend_id
        )
        estimated_cost_micros = (
            selected_candidate.estimated_cost_micros
            or backend.cost_model.estimated_cost_micros
        )
        return {
            "status": "ok",
            "task_type": request.task_type,
            "route_plan": route_plan.model_dump(mode="json"),
            "selected_candidate": selected_candidate.model_dump(mode="json"),
            "route_scoring_report": explanation.get("route_scoring_report"),
            "route_scoring_hash": explanation.get("route_scoring_hash"),
            "task_analysis_report": task_analysis_report.model_dump(mode="json"),
            "task_analysis_hash": canonical_json_hash(
                task_analysis_report.model_dump(mode="json")
            ),
            "estimated_cost_micros": estimated_cost_micros,
            "cost_source": backend.cost_model.cost_source,
            "verifier_recipe_id": route_plan.verifier_recipe_id,
        }

    def explain_route(
        self,
        *,
        task_type: str | None,
        input_payload: dict[str, Any] | list[Any] | None = None,
        routebook_v1_dir: str | Path = "packs/base-routing/routebook",
    ) -> dict[str, Any]:
        """Return a V1 route explanation without scheduling work."""
        request = normalize_submit_request(
            task_type=task_type,
            payload=input_payload,
        )
        loaded_config = load_config_dir(self.config_dir)
        work_unit = self._estimate_work_unit(request)
        route_plan = RouterService.from_dirs(
            config_dir=loaded_config.root,
            routebook_dir=self._routebook_root(loaded_config),
        ).plan_route(work_unit.model_dump(mode="json"))
        task_analysis_report = TaskAnalyzer.from_dirs(
            config_dir=loaded_config.root,
            routebook_v1_dir=routebook_v1_dir,
        ).analyze(work_unit=work_unit, route_plan=route_plan)
        explanation = RouteExplainer.from_dirs(
            config_dir=loaded_config.root,
            routebook_dir=self._routebook_root(loaded_config),
            routebook_v1_dir=routebook_v1_dir,
        ).explain(
            work_unit=work_unit,
            route_plan=route_plan,
            task_analysis_report=task_analysis_report,
        )
        if "route_scoring_report" in explanation:
            route_plan = apply_scored_selection(
                route_plan=route_plan,
                scoring_report=RouteScoringReport.model_validate(
                    explanation["route_scoring_report"]
                ),
            )
        return {
            "status": "ok",
            "task_type": request.task_type,
            "route_plan": route_plan.model_dump(mode="json"),
            **explanation,
        }

    def score_route(
        self,
        *,
        task_type: str | None,
        input_payload: dict[str, Any] | list[Any] | None = None,
        routebook_v1_dir: str | Path = "packs/base-routing/routebook",
    ) -> dict[str, Any]:
        """Return a WP-RB3 RouteScoringReport without scheduling work."""
        explanation = self.explain_route(
            task_type=task_type,
            input_payload=input_payload,
            routebook_v1_dir=routebook_v1_dir,
        )
        return {
            "status": "ok",
            "task_type": explanation["task_type"],
            "route_plan": explanation["route_plan"],
            "task_profile": explanation["task_profile"],
            "capacity_profiles": explanation["capacity_profiles"],
            "task_analysis_report": explanation["task_analysis_report"],
            "task_analysis_hash": explanation["task_analysis_hash"],
            "route_scoring_report": explanation["route_scoring_report"],
            "route_scoring_hash": explanation["route_scoring_hash"],
        }

    def analyze_route(
        self,
        *,
        task_type: str | None,
        input_payload: dict[str, Any] | list[Any] | None = None,
        routebook_v1_dir: str | Path = "packs/base-routing/routebook",
    ) -> dict[str, Any]:
        """Return a deterministic TaskAnalysisReport without scheduling work."""
        request = normalize_submit_request(
            task_type=task_type,
            payload=input_payload,
        )
        loaded_config = load_config_dir(self.config_dir)
        work_unit = self._estimate_work_unit(request)
        route_plan = RouterService.from_dirs(
            config_dir=loaded_config.root,
            routebook_dir=self._routebook_root(loaded_config),
        ).plan_route(work_unit.model_dump(mode="json"))
        task_analysis_report = TaskAnalyzer.from_dirs(
            config_dir=loaded_config.root,
            routebook_v1_dir=routebook_v1_dir,
        ).analyze(work_unit=work_unit, route_plan=route_plan)
        return {
            "status": "ok",
            "task_type": request.task_type,
            "task_analysis_report": task_analysis_report.model_dump(mode="json"),
            "task_analysis_hash": canonical_json_hash(
                task_analysis_report.model_dump(mode="json")
            ),
        }

    def submit_work_unit(
        self,
        *,
        task_type: str | None,
        input_payload: dict[str, Any] | list[Any] | None = None,
        wait: bool = False,
    ) -> dict[str, Any]:
        """Create a Work Unit through Router, Policy, Scheduler."""
        request = normalize_submit_request(
            task_type=task_type,
            payload=input_payload,
        )
        with self._control_plane_context() as (conn, loaded_config):
            result = self._submit_normalized_request(
                conn,
                loaded_config=loaded_config,
                request=request,
            )
        if wait:
            result["wait_status"] = (
                "not_supported_in_phase0_stub_without_worker_or_gateway_runner"
            )
        return result

    def submit_from_file(
        self,
        *,
        task_type: str | None,
        input_path: str | Path,
        wait: bool = False,
    ) -> dict[str, Any]:
        """Submit a Work Unit from one explicit JSON file path."""
        path = Path(input_path)
        payload = json.loads(path.read_text(encoding="utf-8"))
        return self.submit_work_unit(
            task_type=task_type,
            input_payload=payload,
            wait=wait,
        )

    def get_work_unit_status(self, *, work_unit_id: str) -> dict[str, Any]:
        """Return host-safe Work Unit status."""
        with self._control_plane_context() as (conn, _loaded_config):
            current = get_work_unit_status(conn, work_unit_id=work_unit_id)
        if current is None:
            return {"status": "not_found", "work_unit_id": work_unit_id}
        return {
            "status": "ok",
            "work_unit_id": work_unit_id,
            "work_unit": {
                key: value
                for key, value in current.items()
                if key != "body_json"
            },
        }

    def get_work_unit_result(self, *, work_unit_id: str) -> dict[str, Any]:
        """Return HostResultSummary when a submitted result is available."""
        with self._control_plane_context() as (conn, _loaded_config):
            work_unit_exists = (
                get_work_unit_status(conn, work_unit_id=work_unit_id) is not None
            )
            summary = get_host_result_summary(conn, work_unit_id=work_unit_id)
        return host_result_response(
            work_unit_id=work_unit_id,
            summary=summary,
            work_unit_exists=work_unit_exists,
        )

    def get_run_status(self, *, run_id: str) -> dict[str, Any]:
        """Return a minimal run status."""
        with self._control_plane_context() as (conn, _loaded_config):
            row = conn.execute(
                """
                SELECT run_id, status, created_at, updated_at
                FROM runs
                WHERE run_id = ?
                """,
                (run_id,),
            ).fetchone()
        if row is None:
            return {"status": "not_found", "run_id": run_id}
        return {"status": "ok", "run": dict(row)}

    def cancel_work_unit(self, *, work_unit_id: str) -> dict[str, Any]:
        """Expose P0 cancellation behavior without mutating scheduler state."""
        status_response = self.get_work_unit_status(work_unit_id=work_unit_id)
        if status_response["status"] == "not_found":
            return status_response
        work_unit = status_response["work_unit"]
        current_status = work_unit.get("status")
        if current_status in {"succeeded", "failed", "quarantined", "cancelled"}:
            return {
                "status": "already_terminal",
                "work_unit_id": work_unit_id,
                "work_unit_status": current_status,
            }
        return {
            "status": "not_implemented",
            "work_unit_id": work_unit_id,
            "reason": "cancel_not_implemented_in_phase0_stub",
        }

    def get_cost_quality_summary(self, *, run_id: str) -> dict[str, Any]:
        """Return the derived WP11 run-level CostQualityReport."""
        with self._control_plane_context() as (conn, _loaded_config):
            return generate_cost_quality_report(conn, run_id=run_id)

    def list_account_snapshots(
        self,
        *,
        provider: str | None = None,
        status: str | None = None,
    ) -> dict[str, Any]:
        """Return local account snapshots without provider secret values."""
        with self._control_plane_context() as (conn, _loaded_config):
            snapshots = AccountRegistry(conn).list_snapshots(
                provider=provider,
                status=status,
            )
        return {
            "status": "ok",
            "snapshot_count": len(snapshots),
            "snapshots": snapshots,
        }

    def upsert_manual_account_snapshot(
        self,
        *,
        provider: str,
        account_label: str,
        secret_ref: str | None = None,
        status: str = "configured",
        balance_source: str = "manual",
        available_micros: int | None = None,
        monthly_spend_micros: int | None = None,
        monthly_budget_micros: int | None = None,
        requests_per_minute: int | None = None,
        tokens_per_minute: int | None = None,
        visible_models: list[str] | None = None,
    ) -> dict[str, Any]:
        """Persist one local account snapshot using refs, never raw secrets."""
        snapshot = build_manual_account_snapshot(
            provider=provider,
            account_label=account_label,
            secret_ref=secret_ref,
            status=status,  # type: ignore[arg-type]
            balance_source=balance_source,  # type: ignore[arg-type]
            available_micros=available_micros,
            monthly_spend_micros=monthly_spend_micros,
            monthly_budget_micros=monthly_budget_micros,
            requests_per_minute=requests_per_minute,
            tokens_per_minute=tokens_per_minute,
            visible_models=visible_models,
        )
        with self._control_plane_context() as (conn, _loaded_config):
            result = AccountRegistry(conn).upsert_snapshot(snapshot)
        return {"status": "ok", **result}

    def refresh_account_snapshots(self) -> dict[str, Any]:
        """Refresh local account view without calling provider APIs."""
        with self._control_plane_context() as (conn, _loaded_config):
            return AccountRegistry(conn).refresh_local()

    def record_usage_ledger_entry(
        self,
        *,
        work_unit_id: str,
        account_snapshot_id: str | None = None,
        routebook_v1_dir: str | Path = "packs/base-routing/routebook",
    ) -> dict[str, Any]:
        """Record a redacted usage ledger entry for a completed WorkUnit."""
        with self._control_plane_context() as (conn, _loaded_config):
            result = UsageLedgerRepository(conn).record_for_work_unit(
                work_unit_id=work_unit_id,
                account_snapshot_id=account_snapshot_id,
                routebook_v1_dir=routebook_v1_dir,
            )
        return {"status": "ok", **result}

    def list_usage_ledger_entries(
        self,
        *,
        work_unit_id: str | None = None,
        run_id: str | None = None,
    ) -> dict[str, Any]:
        """List redacted usage ledger entries."""
        with self._control_plane_context() as (conn, _loaded_config):
            entries = UsageLedgerRepository(conn).list_entries(
                work_unit_id=work_unit_id,
                run_id=run_id,
            )
        return {"status": "ok", "entry_count": len(entries), "entries": entries}

    def create_audit_receipt(
        self,
        *,
        work_unit_id: str,
        usage_ledger_entry_id: str | None = None,
        account_snapshot_id: str | None = None,
        routebook_v1_dir: str | Path = "packs/base-routing/routebook",
    ) -> dict[str, Any]:
        """Create a redacted audit receipt for an accepted WorkUnit result."""
        with self._control_plane_context() as (conn, _loaded_config):
            result = AuditReceiptRepository(conn).create_for_work_unit(
                work_unit_id=work_unit_id,
                usage_ledger_entry_id=usage_ledger_entry_id,
                account_snapshot_id=account_snapshot_id,
                routebook_v1_dir=routebook_v1_dir,
            )
        return {"status": "ok", **result}

    def list_audit_receipts(
        self,
        *,
        work_unit_id: str | None = None,
        run_id: str | None = None,
    ) -> dict[str, Any]:
        """List redacted audit receipts."""
        with self._control_plane_context() as (conn, _loaded_config):
            receipts = AuditReceiptRepository(conn).list_receipts(
                work_unit_id=work_unit_id,
                run_id=run_id,
            )
        return {
            "status": "ok",
            "receipt_count": len(receipts),
            "receipts": receipts,
        }

    def get_artifact(self, *, artifact_ref_id: str) -> dict[str, Any]:
        """Keep artifact reads closed until the redacted artifact store exists."""
        return {
            "status": "not_implemented",
            "artifact_ref_id": artifact_ref_id,
            "reason": "redacted_artifact_reading_deferred",
        }

    def get_routebook_excerpt(self, *, task_type: str | None = None) -> dict[str, Any]:
        """Return a bounded routebook excerpt."""
        loaded_config = load_config_dir(self.config_dir)
        routebook = load_routebook_dir(self._routebook_root(loaded_config))
        return routebook_excerpt(routebook, task_type=task_type)

    @contextmanager
    def _control_plane_context(
        self,
    ) -> Iterator[tuple[sqlite3.Connection, LoadedConfig]]:
        loaded_config = load_config_dir(self.config_dir)
        conn = initialize_database(self.db_path)
        try:
            rebuild_capacity_projection_from_config_and_db(conn, loaded_config)
            yield conn, loaded_config
        finally:
            conn.close()

    def _submit_normalized_request(
        self,
        conn: sqlite3.Connection,
        *,
        loaded_config: LoadedConfig,
        request: NormalizedWorkUnitRequest,
    ) -> dict[str, Any]:
        inline_input = request.inline_input
        if request.task_type == "url_check":
            return submit_url_check_work_unit(
                conn,
                loaded_config=loaded_config,
                url=str(inline_input["url"]),
                routebook_dir=self._routebook_root(loaded_config),
            )
        if request.task_type == "dedup":
            return submit_dedup_work_unit(
                conn,
                loaded_config=loaded_config,
                items=list(inline_input["items"]),
                routebook_dir=self._routebook_root(loaded_config),
            )
        if request.task_type == "webpage_extraction":
            return submit_webpage_extraction_work_unit(
                conn,
                loaded_config=loaded_config,
                url=str(inline_input["url"]),
                html=_optional_str(inline_input.get("html")),
                text=_optional_str(inline_input.get("text")),
                title=_optional_str(inline_input.get("title")),
                routebook_dir=self._routebook_root(loaded_config),
            )
        if request.task_type == "topic_classification":
            return submit_topic_classification_work_unit(
                conn,
                loaded_config=loaded_config,
                text=str(inline_input["text"]),
                allowed_labels=_optional_str_list(inline_input.get("allowed_labels")),
                routebook_dir=self._routebook_root(loaded_config),
            )
        if request.task_type == "claim_extraction":
            return submit_claim_extraction_work_unit(
                conn,
                loaded_config=loaded_config,
                text=str(inline_input["text"]),
                source_id=str(inline_input["source_id"]),
                entity=_optional_str(inline_input.get("entity")),
                allowed_claim_types=_optional_str_list(
                    inline_input.get("allowed_claim_types")
                ),
                routebook_dir=self._routebook_root(loaded_config),
            )
        raise HostAdapterInputError(f"unsupported task_type: {request.task_type}")

    def _routebook_root(self, loaded_config: LoadedConfig) -> Path:
        return (
            self.routebook_dir
            if self.routebook_dir is not None
            else loaded_config.root.parent / "routebook"
        )

    def _estimate_work_unit(self, request: NormalizedWorkUnitRequest) -> WorkUnit:
        config = SUPPORTED_DEMO_TASKS[request.task_type]
        return WorkUnit(
            work_unit_id=f"wu_estimate_{request.task_type}",
            run_id=f"run_estimate_{request.task_type}",
            task_type=request.task_type,
            task_level=config["task_level"],
            status="submitted",
            data_labels=["public_url"],
            inline_input=request.inline_input,
            max_cost_micros=0,
        )


def validate_host_payload(value: Any) -> None:
    """Public helper for tests and future adapters."""
    reject_forbidden_host_input(value)


def _selected_candidate(route_plan: RoutePlan) -> RouteCandidate:
    for candidate in route_plan.candidates:
        if candidate.route_candidate_id == route_plan.selected_candidate_id:
            return candidate
    raise ValueError("RoutePlan selected candidate is missing")


def _optional_str(value: Any) -> str | None:
    return value if isinstance(value, str) else None


def _optional_str_list(value: Any) -> list[str] | None:
    if isinstance(value, list) and all(isinstance(item, str) for item in value):
        return value
    return None
