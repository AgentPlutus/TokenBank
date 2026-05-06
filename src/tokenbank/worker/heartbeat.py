"""Heartbeat helpers."""

from __future__ import annotations

from tokenbank.worker.config import WorkerConfig
from tokenbank.worker.poller import ControlPlaneClient


def send_heartbeat(client: ControlPlaneClient, config: WorkerConfig) -> dict:
    return client.heartbeat(config.worker_id)

