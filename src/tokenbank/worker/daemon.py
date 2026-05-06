"""Foreground worker daemon for WP6."""

from __future__ import annotations

import signal
import time
from pathlib import Path
from types import FrameType
from typing import Any

from tokenbank.worker.config import WorkerConfig
from tokenbank.worker.executor import LocalToolExecutor
from tokenbank.worker.heartbeat import send_heartbeat
from tokenbank.worker.logs import WorkerLog
from tokenbank.worker.poller import ControlPlaneClient, ControlPlaneRequestError
from tokenbank.worker.sandbox import WorkerSandbox
from tokenbank.worker.spool import ResultSpool


class WorkerDaemon:
    """Minimal Windows-friendly foreground worker runtime."""

    def __init__(
        self,
        config: WorkerConfig,
        *,
        client: ControlPlaneClient | None = None,
        executor: LocalToolExecutor | None = None,
        sandbox: WorkerSandbox | None = None,
        spool: ResultSpool | None = None,
        log: WorkerLog | None = None,
    ):
        self.config = config
        self.client = client or ControlPlaneClient(
            base_url=config.control_plane_url,
            worker_token=config.worker_token,
            timeout_seconds=float(config.request_timeout_seconds),
        )
        self.executor = executor or LocalToolExecutor()
        self.sandbox = sandbox or WorkerSandbox(config.sandbox_root, config.worker_id)
        self.spool = spool or ResultSpool(config.spool_dir)
        self.log = log or WorkerLog(self.sandbox.root / "worker.log")
        self._registered = False
        self._shutdown_requested = False
        self._last_heartbeat = 0.0

    def close(self) -> None:
        self.client.close()

    def request_shutdown(self) -> None:
        self._shutdown_requested = True

    def install_signal_handlers(self) -> None:
        def handle_signal(signum: int, _frame: FrameType | None) -> None:
            self.log.write(f"shutdown signal received: {signum}")
            self.request_shutdown()

        for signum in (signal.SIGINT, signal.SIGTERM):
            signal.signal(signum, handle_signal)

    def register(self) -> dict[str, Any]:
        self.sandbox.ensure_root()
        response = self.client.register_worker(self.config.manifest_payload())
        self._registered = True
        self.log.write(f"worker registered: {self.config.worker_id}")
        return response

    def heartbeat_once(self) -> dict[str, Any]:
        response = send_heartbeat(self.client, self.config)
        self._last_heartbeat = time.monotonic()
        self.log.write(f"worker heartbeat: {self.config.worker_id}")
        return response

    def replay_completed_spool(self) -> int:
        submitted = 0
        for path, entry in self.spool.completed_entries():
            self.client.submit_result(
                assignment_id=entry.assignment_id,
                worker_id=entry.worker_id,
                output=entry.output,
                lease_token_hash_value=entry.lease_token_hash,
            )
            self.spool.remove(path)
            submitted += 1
            self.log.write(f"spooled result submitted: {entry.assignment_id}")
        return submitted

    def poll_assignment(self) -> dict[str, Any] | None:
        assignment = self.client.poll_assignment(self.config.worker_id)
        if assignment is None:
            return None
        if assignment.get("worker_id") != self.config.worker_id:
            raise PermissionError(
                "worker received assignment for a different worker_id"
            )
        return assignment

    def handle_assignment(self, assignment: dict[str, Any]) -> dict[str, Any]:
        assignment_id = str(assignment["assignment_id"])
        accepted = self.client.accept_assignment(assignment_id, self.config.worker_id)
        sandbox = self.sandbox.create_assignment(assignment_id)
        envelope = self.executor.execute_envelope(
            assignment=assignment,
            sandbox=sandbox,
        )
        progressed = self.client.progress_assignment(
            assignment_id=assignment_id,
            worker_id=self.config.worker_id,
            lease_token=accepted["lease_token"],
            expected_lease_version=int(accepted["lease_version"]),
        )
        try:
            result = self.client.submit_result(
                assignment_id=assignment_id,
                worker_id=self.config.worker_id,
                lease_token=accepted["lease_token"],
                output=envelope.output,
                result_envelope=envelope.model_dump(mode="json"),
            )
        except ControlPlaneRequestError:
            self.spool.write_completed(
                assignment_id=assignment_id,
                worker_id=self.config.worker_id,
                lease_token=accepted["lease_token"],
                output=envelope.output,
            )
            self.log.write(
                f"result submit failed; completed output spooled: {assignment_id}"
            )
            raise

        self.log.write(
            "assignment completed: "
            f"{assignment_id} lease_version={progressed['lease_version']}"
        )
        return result

    def run_once(self) -> dict[str, Any]:
        if not self._registered:
            self.register()
        spooled_count = self.replay_completed_spool()
        self.heartbeat_once()
        assignment = self.poll_assignment()
        if assignment is None:
            return {
                "status": "idle",
                "worker_id": self.config.worker_id,
                "spooled_submitted": spooled_count,
            }
        result = self.handle_assignment(assignment)
        return {
            "status": "completed",
            "worker_id": self.config.worker_id,
            "assignment_id": assignment["assignment_id"],
            "result": result,
            "spooled_submitted": spooled_count,
        }

    def run(self, *, max_iterations: int | None = None) -> None:
        iteration = 0
        while not self._shutdown_requested:
            if max_iterations is not None and iteration >= max_iterations:
                return
            if not self._registered:
                self.register()
                self.replay_completed_spool()
            now = time.monotonic()
            if now - self._last_heartbeat >= float(
                self.config.heartbeat_interval_seconds
            ):
                self.heartbeat_once()
            assignment = self.poll_assignment()
            if assignment is not None:
                self.handle_assignment(assignment)
            iteration += 1
            time.sleep(float(self.config.poll_interval_seconds))


def run_worker_from_config(
    config: WorkerConfig,
    *,
    once: bool = False,
    max_iterations: int | None = None,
) -> dict[str, Any] | None:
    daemon = WorkerDaemon(config)
    try:
        daemon.install_signal_handlers()
        if once:
            return daemon.run_once()
        daemon.run(max_iterations=max_iterations)
        return None
    finally:
        daemon.close()


def ensure_worker_dirs(config: WorkerConfig) -> list[Path]:
    sandbox = WorkerSandbox(config.sandbox_root, config.worker_id)
    root = sandbox.ensure_root()
    config.spool_dir.mkdir(parents=True, exist_ok=True)
    return [root, config.spool_dir]
