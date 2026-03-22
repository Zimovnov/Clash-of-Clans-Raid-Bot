from fastapi.testclient import TestClient

from app.api.main import create_app
from app.core.config import get_settings


def _build_client(monkeypatch, **env_values: str) -> TestClient:
    for key, value in env_values.items():
        monkeypatch.setenv(key, value)
    get_settings.cache_clear()
    return TestClient(create_app())


def test_docs_disabled_by_default(monkeypatch) -> None:
    monkeypatch.delenv("API_DOCS_ENABLED", raising=False)
    monkeypatch.delenv("INTERNAL_API_TOKEN", raising=False)
    get_settings.cache_clear()

    with TestClient(create_app()) as client:
        assert client.get("/docs").status_code == 404
        assert client.get("/openapi.json").status_code == 404


def test_docs_can_be_enabled(monkeypatch) -> None:
    with _build_client(monkeypatch, API_DOCS_ENABLED="true") as client:
        assert client.get("/docs").status_code == 200
        assert client.get("/openapi.json").status_code == 200


def test_internal_routes_are_disabled_without_token(monkeypatch) -> None:
    monkeypatch.setenv("INTERNAL_API_TOKEN", "")
    get_settings.cache_clear()

    with TestClient(create_app()) as client:
        response = client.post("/internal/jobs/build-report", json={"tag": "#ABC"})

    assert response.status_code == 404


def test_internal_routes_require_bearer_token(monkeypatch) -> None:
    with _build_client(monkeypatch, INTERNAL_API_TOKEN="secret-token") as client:
        response = client.post("/internal/jobs/build-report", json={"tag": "#ABC"})

    assert response.status_code == 401
    assert response.headers["www-authenticate"] == "Bearer"


def test_internal_routes_reject_invalid_bearer_token(monkeypatch) -> None:
    with _build_client(monkeypatch, INTERNAL_API_TOKEN="secret-token") as client:
        response = client.post(
            "/internal/jobs/build-report",
            json={"tag": "#ABC"},
            headers={"Authorization": "Bearer wrong-token"},
        )

    assert response.status_code == 401
    assert response.headers["www-authenticate"] == "Bearer"
