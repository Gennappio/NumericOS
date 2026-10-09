from __future__ import annotations

from fastapi.testclient import TestClient

from numericos import __version__


def test_health_reports_version_and_utc_time(client: TestClient) -> None:
    response = client.get("/v1/health")

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert body["app"] == "numericos"
    assert body["version"] == __version__
    assert body["time_utc"].endswith("Z")


def test_correlation_id_is_generated_when_missing(client: TestClient) -> None:
    response = client.get("/v1/health")

    assert response.headers["x-correlation-id"].startswith("cor_")


def test_valid_correlation_id_is_echoed(client: TestClient) -> None:
    response = client.get("/v1/health", headers={"X-Correlation-ID": "task-42.a_b"})

    assert response.headers["x-correlation-id"] == "task-42.a_b"


def test_invalid_correlation_id_is_replaced(client: TestClient) -> None:
    response = client.get("/v1/health", headers={"X-Correlation-ID": "not valid: spaces"})

    assert response.headers["x-correlation-id"].startswith("cor_")


def test_cors_is_limited_to_configured_origins(client: TestClient) -> None:
    allowed = client.options(
        "/v1/health",
        headers={"Origin": "http://localhost:5173", "Access-Control-Request-Method": "GET"},
    )
    denied = client.options(
        "/v1/health",
        headers={"Origin": "http://evil.example", "Access-Control-Request-Method": "GET"},
    )

    assert allowed.headers["access-control-allow-origin"] == "http://localhost:5173"
    assert "access-control-allow-origin" not in denied.headers
