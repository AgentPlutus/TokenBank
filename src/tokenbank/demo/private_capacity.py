"""Private Capacity Network demo runner for WP13."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from fastapi.testclient import TestClient

from tokenbank.app.api import create_app
from tokenbank.capacity.discovery import discover_capacity_nodes
from tokenbank.db.bootstrap import initialize_database
from tokenbank.host import execute_control_plane_gateway_assignment_once
from tokenbank.host_adapter import HostAdapterCore
from tokenbank.observability.report_generator import generate_cost_quality_report
from tokenbank.worker.config import WorkerConfig
from tokenbank.worker.daemon import WorkerDaemon
from tokenbank.worker.poller import ControlPlaneClient

DEMO_TASK_ORDER = (
    "url_check",
    "dedup",
    "webpage_extraction",
    "topic_classification",
    "claim_extraction",
)
DEMO_DATASET_FILES = {
    "url_check": "urls.json",
    "dedup": "dedup.json",
    "webpage_extraction": "webpage_extraction.json",
    "topic_classification": "topic_classification.json",
    "claim_extraction": "claim_extraction.json",
}
LOCAL_WORKER_TASKS = {"url_check", "dedup", "webpage_extraction"}
GATEWAY_TASKS = {"topic_classification", "claim_extraction"}
DEMO_WORKER_ID = "wrk_demo_local"
DEMO_WORKER_TOKEN = "tbk_w_private_capacity_demo"


class PrivateCapacityDemoRunner:
    """Run the Phase 0 private capacity demo from explicit fixtures."""

    def __init__(
        self,
        *,
        config_dir: str | Path = "config",
        db_path: str | Path = ".tokenbank/tokenbank.db",
        demo_dir: str | Path = "examples/private_capacity_demo",
    ):
        self.config_dir = Path(config_dir)
        self.db_path = Path(db_path)
        self.demo_dir = Path(demo_dir)
        self.host_adapter = HostAdapterCore(
            config_dir=self.config_dir,
            db_path=self.db_path,
        )

    def run(
        self,
        *,
        task: str | None = None,
        all_tasks: bool = False,
    ) -> dict[str, Any]:
        """Run one demo task or all five supported task types."""
        tasks = self._selected_tasks(task=task, all_tasks=all_tasks)
        capacity_before = self.host_adapter.list_capabilities()
        submissions = self._submit_tasks(tasks)
        execution_results = self._execute_submissions(tasks, submissions)
        host_results = {
            task_type: self.host_adapter.get_work_unit_result(
                work_unit_id=submission["work_unit_id"]
            )
            for task_type, submission in submissions.items()
        }
        report_summaries = self._report_summaries(submissions)
        capacity_after = self._capacity_nodes()
        report_task = tasks[0]

        return {
            "status": "ok",
            "demo": "private_capacity_demo",
            "capacity_network": "Private Agent Capacity Network",
            "xradar_required": False,
            "tasks_requested": tasks,
            "task_count": len(tasks),
            "run_id": submissions[report_task]["run_id"],
            "run_ids": {
                task_type: submission["run_id"]
                for task_type, submission in submissions.items()
            },
            "submissions": submissions,
            "execution_results": execution_results,
            "host_results": host_results,
            "report_summary": report_summaries[report_task],
            "report_summaries": report_summaries,
            "cost_quality_memory": {
                "generated": True,
                "report_run_id": submissions[report_task]["run_id"],
                "report_type": report_summaries[report_task]["report_type"],
            },
            "capacity": {
                "before_count": capacity_before["capacity_node_count"],
                "after_count": len(capacity_after),
                "nodes": capacity_after,
            },
        }

    def _selected_tasks(
        self,
        *,
        task: str | None,
        all_tasks: bool,
    ) -> list[str]:
        if all_tasks and task is not None:
            raise ValueError("use either --all or --task, not both")
        if all_tasks:
            return list(DEMO_TASK_ORDER)
        if task is None:
            raise ValueError("either --all or --task is required")
        if task not in DEMO_TASK_ORDER:
            raise ValueError(f"unsupported demo task: {task}")
        return [task]

    def _submit_tasks(self, tasks: list[str]) -> dict[str, dict[str, Any]]:
        submissions = {}
        for task_type in tasks:
            payload = self._load_task_payload(task_type)
            submissions[task_type] = self.host_adapter.submit_work_unit(
                task_type=task_type,
                input_payload=payload,
            )
        return submissions

    def _execute_submissions(
        self,
        tasks: list[str],
        submissions: dict[str, dict[str, Any]],
    ) -> dict[str, dict[str, Any]]:
        results: dict[str, dict[str, Any]] = {}
        app = create_app(config_dir=self.config_dir, db_path=self.db_path)
        with TestClient(app) as api_client:
            local_tasks = [task for task in tasks if task in LOCAL_WORKER_TASKS]
            if local_tasks:
                daemon = WorkerDaemon(
                    self._worker_config(),
                    client=ControlPlaneClient(
                        base_url="http://testserver",
                        worker_token=DEMO_WORKER_TOKEN,
                        client=api_client,
                    ),
                )
                daemon.register()
                for _task_type in local_tasks:
                    worker_result = daemon.run_once()
                    if worker_result["status"] != "completed":
                        raise RuntimeError("demo worker did not complete assignment")
                    completed_task = self._task_for_assignment(
                        submissions,
                        worker_result["assignment_id"],
                    )
                    results[completed_task] = worker_result

            for task_type in tasks:
                if task_type not in GATEWAY_TASKS:
                    continue
                gateway_result = execute_control_plane_gateway_assignment_once(
                    app.state.db,
                    assignment_id=submissions[task_type]["assignment_id"],
                )
                if gateway_result is None:
                    raise RuntimeError(f"gateway did not complete {task_type}")
                results[task_type] = gateway_result
        return results

    def _worker_config(self) -> WorkerConfig:
        worker_root = self.db_path.parent / "private_capacity_demo_worker"
        return WorkerConfig(
            worker_id=DEMO_WORKER_ID,
            worker_token=DEMO_WORKER_TOKEN,
            capabilities=["url_check", "dedup", "webpage_extraction"],
            backend_ids=[
                "backend:url_check:v0",
                "backend:dedup:local_script:v0",
                "backend:webpage_extraction:browser_fetch:v0",
            ],
            backend_classes=["local_tool", "local_script", "browser_fetch"],
            allowed_task_types=["url_check", "dedup", "webpage_extraction"],
            sandbox_root=worker_root / "sandbox",
            spool_dir=worker_root / "spool",
            heartbeat_interval_seconds=0.01,
            poll_interval_seconds=0.01,
        )

    def _load_task_payload(self, task_type: str) -> dict[str, Any]:
        path = self.demo_dir / DEMO_DATASET_FILES[task_type]
        payload = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(payload, dict):
            raise ValueError(f"demo fixture must be a JSON object: {path}")
        return payload

    def _report_summaries(
        self,
        submissions: dict[str, dict[str, Any]],
    ) -> dict[str, dict[str, Any]]:
        conn = initialize_database(self.db_path)
        try:
            return {
                task_type: generate_cost_quality_report(
                    conn,
                    run_id=submission["run_id"],
                )
                for task_type, submission in submissions.items()
            }
        finally:
            conn.close()

    def _capacity_nodes(self) -> list[dict[str, Any]]:
        conn = initialize_database(self.db_path)
        try:
            return discover_capacity_nodes(conn)
        finally:
            conn.close()

    def _task_for_assignment(
        self,
        submissions: dict[str, dict[str, Any]],
        assignment_id: str,
    ) -> str:
        for task_type, submission in submissions.items():
            if submission["assignment_id"] == assignment_id:
                return task_type
        raise RuntimeError(f"unexpected assignment completed: {assignment_id}")
