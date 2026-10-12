"""Helpers for tests that talk to a real server process."""

from __future__ import annotations

import json
from collections.abc import Iterator
from contextlib import contextmanager
from typing import Any

import httpx

from numericos.cli.client import iter_sse
from tests.conftest import LiveServer

Json = dict[str, Any]
EVENT_STREAM = {"Accept": "text/event-stream"}


def post(server: LiveServer, path: str, body: Json) -> Json:
    response = httpx.post(f"{server.base_url}{path}", json=body, timeout=30)
    assert response.status_code == 201, response.text
    result: Json = response.json()
    return result


def get(server: LiveServer, path: str, **params: Any) -> Json:
    response = httpx.get(f"{server.base_url}{path}", params=params, timeout=30)
    assert response.status_code == 200, response.text
    result: Json = response.json()
    return result


def new_project(server: LiveServer, name: str = "Heat 2D") -> Json:
    return post(server, "/v1/projects", {"name": name})


def new_card(server: LiveServer, project_id: str, title: str, **fields: Any) -> Json:
    return post(
        server, f"/v1/projects/{project_id}/cards", {"type": "task", "title": title, **fields}
    )


def ledger(server: LiveServer, project_id: str) -> list[Json]:
    events: list[Json] = get(server, "/v1/events", project_id=project_id, limit=1000)["events"]
    return events


@contextmanager
def event_stream(
    server: LiveServer,
    project_id: str,
    *,
    after: int | None = None,
    last_event_id: int | None = None,
    timeout: float = 10.0,
) -> Iterator[Iterator[tuple[str | None, Json]]]:
    """Open the SSE view of a project's ledger and yield ``(frame id, event)`` pairs.

    A read that stays silent for ``timeout`` seconds fails the test instead of hanging it.
    """
    headers = dict(EVENT_STREAM)
    if last_event_id is not None:
        headers["Last-Event-ID"] = str(last_event_id)
    params: Json = {"project_id": project_id}
    if after is not None:
        params["after"] = after
    with httpx.stream(
        "GET", f"{server.base_url}/v1/events", params=params, headers=headers, timeout=timeout
    ) as response:
        assert response.status_code == 200, response.read()
        assert response.headers["content-type"].startswith("text/event-stream")
        yield ((event_id, json.loads(data)) for event_id, data in iter_sse(response.iter_lines()))


def take(stream: Iterator[tuple[str | None, Json]], count: int) -> list[Json]:
    """The next ``count`` events; every frame ID must be the event's ``seq``."""
    events = []
    for _ in range(count):
        frame_id, event = next(stream)
        assert frame_id == str(event["seq"])
        events.append(event)
    return events
