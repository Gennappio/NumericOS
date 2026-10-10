from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

from numericos import __version__
from numericos.api.app import create_app
from numericos.config import Settings


def test_health_reports_version_time_and_migrated_database(client: TestClient) -> None:
    response = client.get("/v1/health")

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert body["app"] == "numericos"
    assert body["version"] == __version__
    assert body["time_utc"].endswith("Z")
    assert body["db"] == "ok"
    assert body["schema_revision"] == body["expected_revision"] == "0001"


def test_health_is_degraded_when_the_schema_is_missing(tmp_path: Path) -> None:
    settings = Settings(data_dir=tmp_path / "data")
    settings.data_dir.mkdir()

    with TestClient(create_app(settings)) as client:
        body = client.get("/v1/health").json()

    assert body["status"] == "degraded"
    assert body["db"] == "ok"
    assert body["schema_revision"] is None


def test_health_reports_an_unavailable_database(tmp_path: Path) -> None:
    settings = Settings(data_dir=tmp_path / "missing" / "data")  # directory never created

    with TestClient(create_app(settings)) as client:
        body = client.get("/v1/health").json()

    assert body["status"] == "degraded"
    assert body["db"] == "unavailable"


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


def test_both_spellings_of_the_local_gui_origin_may_change_data(client: TestClient) -> None:
    for origin in ("http://localhost:5173", "http://127.0.0.1:5173"):
        preflight = client.options(
            "/v1/cards/card_x",
            headers={
                "Origin": origin,
                "Access-Control-Request-Method": "PATCH",
                "Access-Control-Request-Headers": "content-type,x-actor",
            },
        )

        assert preflight.status_code == 200
        assert preflight.headers["access-control-allow-origin"] == origin
        assert "PATCH" in preflight.headers["access-control-allow-methods"]
