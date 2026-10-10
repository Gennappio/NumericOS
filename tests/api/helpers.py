"""Small request helpers shared by the API tests."""

from __future__ import annotations

from typing import Any

import httpx
from fastapi.testclient import TestClient

Json = dict[str, Any]

UNKNOWN_PROJECT = "prj_01J9W2Z4K7QX8YB3N5M6T0R1S2"
UNKNOWN_CARD = "card_01J9W2Z4K7QX8YB3N5M6T0R1S2"


def create_project(client: TestClient, **fields: Any) -> Json:
    response = client.post("/v1/projects", json={"name": "Heat 2D", **fields})
    assert response.status_code == 201, response.text
    body: Json = response.json()
    return body


def add_card(
    client: TestClient,
    project_id: str,
    title: str,
    *,
    status: str = "backlog",
    card_type: str = "task",
    **fields: Any,
) -> Json:
    response = client.post(
        f"/v1/projects/{project_id}/cards",
        json={"type": card_type, "title": title, "workflow_status": status, **fields},
    )
    assert response.status_code == 201, response.text
    body: Json = response.json()
    return body


def patch_card(client: TestClient, card: Json, **fields: Any) -> httpx.Response:
    """PATCH a card using the version of the representation the test holds."""
    response: httpx.Response = client.patch(
        f"/v1/cards/{card['id']}", json={"version": card["version"], **fields}
    )
    return response


def get_card(client: TestClient, card_id: str) -> Json:
    response = client.get(f"/v1/cards/{card_id}")
    assert response.status_code == 200, response.text
    body: Json = response.json()
    return body


def column(client: TestClient, project_id: str, status: str) -> list[Json]:
    response = client.get(f"/v1/projects/{project_id}/board")
    assert response.status_code == 200, response.text
    return [card for card in response.json()["cards"] if card["workflow_status"] == status]


def titles(cards: list[Json]) -> list[str]:
    return [card["title"] for card in cards]


def ranks(cards: list[Json]) -> list[int]:
    return [card["sort_order"] for card in cards]


def events(client: TestClient, project_id: str, **params: Any) -> list[Json]:
    response = client.get("/v1/events", params={"project_id": project_id, **params})
    assert response.status_code == 200, response.text
    page: list[Json] = response.json()["events"]
    return page


def error_of(response: httpx.Response) -> Json:
    body: Json = response.json()["error"]
    return body
