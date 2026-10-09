"""Every non-2xx response, including the framework's own, uses the single error envelope."""

from __future__ import annotations

from fastapi.testclient import TestClient
from pydantic import BaseModel

from numericos.api.app import create_app
from numericos.config import Settings


def test_unknown_route_uses_error_envelope(client: TestClient) -> None:
    response = client.get("/v1/does-not-exist")

    assert response.status_code == 404
    error = response.json()["error"]
    assert error["code"] == "NOT_FOUND"
    assert error["details"] == {}
    assert error["correlation_id"].startswith("cor_")
    assert response.headers["x-correlation-id"] == error["correlation_id"]


def test_method_not_allowed_uses_error_envelope(client: TestClient) -> None:
    response = client.post("/v1/health")

    assert response.status_code == 405
    assert response.json()["error"]["code"] == "METHOD_NOT_ALLOWED"


class _EchoIn(BaseModel):
    name: str
    count: int


def test_validation_errors_are_machine_readable(settings: Settings) -> None:
    app = create_app(settings)

    @app.post("/v1/_echo")
    def _echo(payload: _EchoIn) -> _EchoIn:
        return payload

    with TestClient(app) as client:
        response = client.post("/v1/_echo", json={"name": "x", "count": "not-a-number"})

    assert response.status_code == 422
    error = response.json()["error"]
    assert error["code"] == "VALIDATION_ERROR"
    assert error["details"]["errors"][0]["loc"] == ["body", "count"]
    assert error["details"]["errors"][0]["type"]


def test_unexpected_exceptions_do_not_leak_internals(settings: Settings) -> None:
    app = create_app(settings)

    @app.get("/v1/_boom")
    def _boom() -> None:
        raise RuntimeError("secret internal detail")

    with TestClient(app, raise_server_exceptions=False) as client:
        response = client.get("/v1/_boom")

    assert response.status_code == 500
    error = response.json()["error"]
    assert error["code"] == "INTERNAL_ERROR"
    assert "secret" not in response.text
    assert error["correlation_id"].startswith("cor_")
