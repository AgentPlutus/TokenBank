from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

from tokenbank.app.api import create_app

REPO_ROOT = Path(__file__).resolve().parents[2]
HOST_HEADERS = {"Authorization": "Bearer tbk_h_testhost"}
WORKER_HEADERS = {"Authorization": "Bearer tbk_w_testworker"}
INTERNAL_HEADERS = {"Authorization": "Bearer tbk_i_testinternal"}


def _client(tmp_path: Path) -> TestClient:
    app = create_app(
        config_dir=REPO_ROOT / "config",
        db_path=tmp_path / "tokenbank.db",
    )
    return TestClient(app)


def test_host_auth_required(tmp_path: Path) -> None:
    with _client(tmp_path) as client:
        response = client.get("/v0/host/capabilities")

    assert response.status_code == 401
    assert response.json()["detail"]["error"] == "missing_bearer_token"


def test_worker_auth_required(tmp_path: Path) -> None:
    with _client(tmp_path) as client:
        response = client.post(
            "/v0/workers/register",
            headers=HOST_HEADERS,
            json={"worker_id": "wrk_wrong_token"},
        )

    assert response.status_code == 403
    assert response.json()["detail"]["error"] == "wrong_token_kind"


def test_internal_endpoint_not_public(tmp_path: Path) -> None:
    with _client(tmp_path) as client:
        public_response = client.post(
            "/internal/router/plan",
            headers=HOST_HEADERS,
        )
        internal_response = client.post(
            "/internal/router/plan",
            headers=INTERNAL_HEADERS,
        )

    assert public_response.status_code == 403
    assert internal_response.status_code == 200
    assert internal_response.json()["status"] == "ok"
