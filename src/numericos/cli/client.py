"""Thin synchronous HTTP client for the NumericOS API."""

from __future__ import annotations

import json
from collections.abc import Iterable, Iterator
from contextlib import contextmanager
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
    """No HTTP response at all, or a response that broke off (refused, reset, timeout, ...)."""

    def __init__(self, url: str, cause: Exception) -> None:
        self.url = url
        self.cause = cause
        super().__init__(f"cannot reach {url}: {cause}")


def iter_sse(lines: Iterable[str]) -> Iterator[tuple[str | None, str]]:
    """Decode the lines of a Server-Sent Events stream into ``(last event id, data)`` pairs.

    Follows the dispatch rules of the SSE format: a blank line ends an event, ``data`` lines are
    joined with a newline, lines starting with a colon are comments (keep-alives), and the event
    ID stays in effect until another ``id`` line replaces it. Events without data are skipped.
    """
    event_id: str | None = None
    data: list[str] = []
    for line in lines:
        if line == "":
            if data:
                yield event_id, "\n".join(data)
            data = []
        elif not line.startswith(":"):
            field, _, value = line.partition(":")
            value = value.removeprefix(" ")
            if field == "data":
                data.append(value)
            elif field == "id":
                event_id = value


def _envelope(response: httpx.Response) -> dict[str, Any]:
    try:
        body = response.json()
    except ValueError:
        body = None
    if isinstance(body, dict) and "error" in body:
        return body
    return {
        "error": {
            "code": "HTTP_ERROR",
            "message": response.text,
            "details": {},
            "correlation_id": None,
        }
    }


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

    def post(self, path: str, json: Any, headers: dict[str, str] | None = None) -> Any:
        return self._request("POST", path, json=json, headers=headers)

    def patch(self, path: str, json: Any) -> Any:
        return self._request("PATCH", path, json=json)

    def put(self, path: str, json: Any) -> Any:
        return self._request("PUT", path, json=json)

    @contextmanager
    def stream(self, path: str) -> Iterator[Iterator[bytes]]:
        """The body of a file download, in chunks, once the server has answered with success."""
        try:
            with self._http.stream("GET", path, headers={"Accept": "*/*"}) as response:
                if not response.is_success:
                    response.read()
                    raise ApiError(response.status_code, _envelope(response))
                yield response.iter_bytes()
        except httpx.TransportError as exc:
            raise ApiUnreachable(self.base_url, exc) from exc

    def follow_events(self, project_id: str, after: int = 0) -> Iterator[dict[str, Any]]:
        """Replay a project's ledger after ``after``, then yield events as they are committed.

        The iterator ends only if the server ends the stream; a broken connection raises
        ``ApiUnreachable``. The caller keeps the last ``seq`` it saw to resume exactly there.
        """
        try:
            with self._http.stream(
                "GET",
                "/v1/events",
                params={"project_id": project_id, "after": after},
                headers={"Accept": "text/event-stream"},
                # Connecting must be quick; between events the stream may stay silent.
                timeout=httpx.Timeout(10.0, read=None),
            ) as response:
                if not response.is_success:
                    response.read()
                    raise ApiError(response.status_code, _envelope(response))
                for _event_id, data in iter_sse(response.iter_lines()):
                    event: dict[str, Any] = json.loads(data)
                    yield event
        except httpx.TransportError as exc:
            raise ApiUnreachable(self.base_url, exc) from exc

    def _request(self, method: str, path: str, **kwargs: Any) -> Any:
        try:
            response = self._http.request(method, path, **kwargs)
        except httpx.TransportError as exc:
            raise ApiUnreachable(self.base_url, exc) from exc
        if response.is_success:
            return response.json() if response.content else None
        raise ApiError(response.status_code, _envelope(response))
