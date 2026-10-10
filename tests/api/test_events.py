from __future__ import annotations

from typing import Any

import pytest
from fastapi.testclient import TestClient

from tests.api.helpers import UNKNOWN_PROJECT, add_card, create_project, error_of, events

EVENT_FIELDS = {
    "event_id",
    "seq",
    "project_id",
    "type",
    "subject_id",
    "actor",
    "producer",
    "severity",
    "correlation_id",
    "schema_version",
    "timestamp_utc",
    "payload",
}


def test_events_are_returned_in_sequence_order(client: TestClient) -> None:
    project = create_project(client)
    for title in ("a", "b", "c"):
        add_card(client, project["id"], title)

    page = client.get("/v1/events", params={"project_id": project["id"]}).json()

    assert [event["type"] for event in page["events"]] == [
        "PROJECT_CREATED",
        "CARD_CREATED",
        "CARD_CREATED",
        "CARD_CREATED",
    ]
    seqs = [event["seq"] for event in page["events"]]
    assert seqs == sorted(seqs)
    assert len(set(seqs)) == 4
    assert page["has_more"] is False
    assert page["next_cursor"] == seqs[-1]
    for event in page["events"]:
        assert set(event) == EVENT_FIELDS
        assert event["event_id"].startswith("evt_")
        assert event["project_id"] == project["id"]
        assert event["schema_version"] == 1
        assert event["timestamp_utc"].endswith("Z")


def test_cursor_returns_only_newer_events(client: TestClient) -> None:
    project = create_project(client)
    add_card(client, project["id"], "a")
    cursor = events(client, project["id"])[-1]["seq"]
    add_card(client, project["id"], "b")
    add_card(client, project["id"], "c")

    newer = events(client, project["id"], after=cursor)
    nothing = client.get(
        "/v1/events", params={"project_id": project["id"], "after": newer[-1]["seq"]}
    ).json()

    assert [event["payload"]["card"]["title"] for event in newer] == ["b", "c"]
    assert all(event["seq"] > cursor for event in newer)
    assert nothing == {"events": [], "next_cursor": None, "has_more": False}


def test_pages_can_be_walked_with_limit_and_cursor(client: TestClient) -> None:
    project = create_project(client)
    for index in range(4):
        add_card(client, project["id"], f"card {index}")
    params: dict[str, Any] = {"project_id": project["id"], "limit": 2}

    first = client.get("/v1/events", params=params).json()
    second = client.get("/v1/events", params={**params, "after": first["next_cursor"]}).json()
    third = client.get("/v1/events", params={**params, "after": second["next_cursor"]}).json()

    assert (len(first["events"]), first["has_more"]) == (2, True)
    assert (len(second["events"]), second["has_more"]) == (2, True)
    assert (len(third["events"]), third["has_more"]) == (1, False)
    walked = [event["seq"] for page in (first, second, third) for event in page["events"]]
    assert walked == [event["seq"] for event in events(client, project["id"])]


def test_newest_first_and_before(client: TestClient) -> None:
    project = create_project(client)
    for title in ("a", "b", "c"):
        add_card(client, project["id"], title)
    ascending = [event["seq"] for event in events(client, project["id"])]

    latest_two = events(client, project["id"], order="desc", limit=2)
    older = events(client, project["id"], order="desc", before=latest_two[-1]["seq"])

    assert [event["seq"] for event in latest_two] == ascending[:-3:-1]
    assert [event["seq"] for event in older] == ascending[-3::-1]


def test_events_are_scoped_to_their_project(client: TestClient) -> None:
    first = create_project(client, name="first")
    second = create_project(client, name="second")
    add_card(client, first["id"], "only in first")

    assert len(events(client, first["id"])) == 2
    assert [event["type"] for event in events(client, second["id"])] == ["PROJECT_CREATED"]


def test_unknown_project_is_404_not_an_empty_page(client: TestClient) -> None:
    response = client.get("/v1/events", params={"project_id": UNKNOWN_PROJECT})

    assert response.status_code == 404
    assert error_of(response)["code"] == "NOT_FOUND"


@pytest.mark.parametrize(
    "params",
    [
        {},
        {"project_id": "prj_x", "limit": 0},
        {"project_id": "prj_x", "limit": 1001},
        {"project_id": "prj_x", "after": -1},
        {"project_id": "prj_x", "order": "sideways"},
    ],
)
def test_invalid_query_is_422(client: TestClient, params: dict[str, Any]) -> None:
    response = client.get("/v1/events", params=params)

    assert response.status_code == 422
    assert error_of(response)["code"] == "VALIDATION_ERROR"


def test_actor_defaults_and_correlation_id_is_kept(client: TestClient) -> None:
    response = client.post(
        "/v1/projects", json={"name": "traced"}, headers={"X-Correlation-ID": "lab-quest-012"}
    )

    (event,) = events(client, response.json()["id"])
    assert event["actor"] == "api:unknown"
    assert event["correlation_id"] == "lab-quest-012"
    assert response.headers["x-correlation-id"] == "lab-quest-012"


def test_malformed_actor_is_rejected_before_anything_is_written(client: TestClient) -> None:
    response = client.post(
        "/v1/projects", json={"name": "x"}, headers={"X-Actor": "Not A Valid Actor!"}
    )

    assert response.status_code == 422
    assert error_of(response)["details"]["errors"][0]["loc"] == ["header", "x-actor"]
    assert client.get("/v1/projects").json() == {"projects": []}
