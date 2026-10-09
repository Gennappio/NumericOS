"""Thin synchronous HTTP client for the NumericOS API."""

from __future__ import annotations

from types import TracebackType
from typing import Any

import httpx

from numericos.core.ids import new_id


class ApiError(Exception):
    """The API answered with an error envelope."""

    def __init__(self, status_code: int, envelope: dict[str, Any]) -> None:
        error = envelope.get("error", {})
        self.status_code = status_code
        self.envelope = envelope
        self.code = str(error.get("code", "HTTP_ERROR"))
        self.message = str(error.get("message", ""))
        self.details: dict[str, Any] = error.get("details") or {}
        super().__init__(f"{self.code}: {self.message}")


class ApiUnreachable(Exception):
    """No HTTP response at all (connection refused, timeout, ...)."""

    def __init__(self, url: str, cause: Exception) -> None:
        self.url = url
        self.cause = cause
        super().__init__(f"cannot reach {url}: {cause}")


class ApiClient:
    def __init__(self, base_url: str, *, actor: str = "cli:local", timeout: float = 10.0) -> None:
        self.base_url = base_url.rstrip("/")
        self.correlation_id = new_id("cor")
        self._http = httpx.Client(
            base_url=self.base_url,
            timeout=timeout,
            headers={
                "Accept": "application/json",
                "X-Actor": actor,
                "X-Correlation-ID": self.correlation_id,
            },
        )

    def __enter__(self) -> ApiClient:
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        self.close()

    def close(self) -> None:
        self._http.close()

    def get(self, path: str, params: dict[str, Any] | None = None) -> Any:
        return self._request("GET", path, params=params)

    def post(self, path: str, json: Any) -> Any:
        return self._request("POST", path, json=json)

    def patch(self, path: str, json: Any) -> Any:
        return self._request("PATCH", path, json=json)

    def _request(self, method: str, path: str, **kwargs: Any) -> Any:
        try:
            response = self._http.request(method, path, **kwargs)
        except httpx.TransportError as exc:
            raise ApiUnreachable(self.base_url, exc) from exc
        if response.is_success:
            return response.json() if response.content else None
        try:
            envelope = response.json()
        except ValueError:
            envelope = {
                "error": {
                    "code": "HTTP_ERROR",
                    "message": response.text,
                    "details": {},
                    "correlation_id": None,
                }
            }
        raise ApiError(response.status_code, envelope)
