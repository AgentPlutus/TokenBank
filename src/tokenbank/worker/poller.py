"""Control-plane HTTP client and polling helpers."""

from __future__ import annotations

from typing import Any

import httpx


class ControlPlaneRequestError(RuntimeError):
    """Raised when the control plane request fails."""


class ControlPlaneClient:
    def __init__(
        self,
        *,
        base_url: str,
        worker_token: str,
        timeout_seconds: float = 10,
        client: httpx.Client | None = None,
    ):
        self._owned_client = client is None
        self.client = client or httpx.Client(
            base_url=base_url,
            timeout=timeout_seconds,
        )
        self.headers = {"Authorization": f"Bearer {worker_token}"}

    def close(self) -> None:
        if self._owned_client:
            self.client.close()

    def register_worker(self, payload: dict[str, Any]) -> dict[str, Any]:
        return self._request("POST", "/v0/workers/register", json=payload)

    def heartbeat(self, worker_id: str) -> dict[str, Any]:
        return self._request("POST", f"/v0/workers/{worker_id}/heartbeat")

    def poll_assignment(self, worker_id: str) -> dict[str, Any] | None:
        response = self._request("GET", f"/v0/workers/{worker_id}/assignments/next")
        return response.get("assignment")

    def accept_assignment(self, assignment_id: str, worker_id: str) -> dict[str, Any]:
        return self._request(
            "POST",
            f"/v0/assignments/{assignment_id}/accept",
            json={"worker_id": worker_id},
        )

    def progress_assignment(
        self,
        *,
        assignment_id: str,
        worker_id: str,
        lease_token: str,
        expected_lease_version: int,
    ) -> dict[str, Any]:
        return self._request(
            "POST",
            f"/v0/assignments/{assignment_id}/progress",
            json={
                "worker_id": worker_id,
                "lease_token": lease_token,
                "expected_lease_version": expected_lease_version,
            },
        )

    def submit_result(
        self,
        *,
        assignment_id: str,
        worker_id: str,
        output: dict[str, Any],
        lease_token: str | None = None,
        lease_token_hash_value: str | None = None,
        result_envelope: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "worker_id": worker_id,
            "output": output,
        }
        if result_envelope is not None:
            payload["result_envelope"] = result_envelope
        if lease_token_hash_value is not None:
            payload["lease_token_hash"] = lease_token_hash_value
        else:
            payload["lease_token"] = lease_token
        return self._request(
            "POST",
            f"/v0/assignments/{assignment_id}/result",
            json=payload,
        )

    def _request(self, method: str, path: str, **kwargs: Any) -> dict[str, Any]:
        response = self.client.request(
            method,
            path,
            headers=self.headers,
            **kwargs,
        )
        if response.status_code >= 400:
            raise ControlPlaneRequestError(response.text)
        return response.json()
