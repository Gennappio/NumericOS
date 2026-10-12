from __future__ import annotations

from typing import Any

import pytest
from fastapi.testclient import TestClient

from tests.api.helpers import (
    UNKNOWN_CARD,
    UNKNOWN_PROJECT,
    Json,
    add_card,
    column,
    create_project,
    error_of,
    events,
    get_card,
    patch_card,
    ranks,
    titles,
)

CARD_FIELDS = {
    "id",
    "project_id",
    "type",
    "title",
    "description",
    "workflow_status",
    "sort_order",
    "entity_ref",
    "origin",
    "version",
    "created_at",
    "updated_at",
}


@pytest.fixture
def project(client: TestClient) -> Json:
    return create_project(client)


def test_create_appends_to_the_column_and_records_one_event(
    client: TestClient, project: Json
) -> None:
    response = client.post(
        f"/v1/projects/{project['id']}/cards",
        json={"type": "hypothesis", "title": "Sparse kernel cache locality"},
        headers={"X-Actor": "web:local"},
    )

    assert response.status_code == 201
    card = response.json()
    assert set(card) == CARD_FIELDS
    assert card["id"].startswith("card_")
    assert card["project_id"] == project["id"]
    assert card["type"] == "hypothesis"
    assert card["workflow_status"] == "backlog"
    assert card["sort_order"] == 0
    assert card["entity_ref"] is None
    assert card["version"] == 1

    second = add_card(client, project["id"], "second")
    third = add_card(client, project["id"], "third")
    assert [second["sort_order"], third["sort_order"]] == [1000, 2000]

    created = [event for event in events(client, project["id"]) if event["type"] == "CARD_CREATED"]
    assert len(created) == 3
    assert created[0]["subject_id"] == card["id"]
    assert created[0]["actor"] == "web:local"
    assert created[0]["payload"] == {"card": card}


def test_create_under_an_unknown_project_is_404(client: TestClient) -> None:
    response = client.post(
        f"/v1/projects/{UNKNOWN_PROJECT}/cards", json={"type": "task", "title": "orphan"}
    )

    assert response.status_code == 404
    assert error_of(response)["details"] == {"resource": "project", "id": UNKNOWN_PROJECT}


def test_board_lists_statuses_and_cards_in_board_order(client: TestClient, project: Json) -> None:
    add_card(client, project["id"], "r1", status="review")
    add_card(client, project["id"], "b1", status="backlog")
    add_card(client, project["id"], "p1", status="planned")
    add_card(client, project["id"], "b2", status="backlog")

    board = client.get(f"/v1/projects/{project['id']}/board").json()

    assert board["project_id"] == project["id"]
    assert board["workflow_statuses"] == [
        "backlog",
        "planned",
        "active",
        "review",
        "completed",
        "blocked",
    ]
    assert titles(board["cards"]) == ["b1", "b2", "p1", "r1"]


def test_board_of_an_unknown_project_is_404(client: TestClient) -> None:
    assert client.get(f"/v1/projects/{UNKNOWN_PROJECT}/board").status_code == 404


def test_move_to_another_column_at_a_position(client: TestClient, project: Json) -> None:
    pid = project["id"]
    add_card(client, pid, "a")
    b = add_card(client, pid, "b")
    add_card(client, pid, "c")
    r1 = add_card(client, pid, "r1", status="review")
    r2 = add_card(client, pid, "r2", status="review")

    response = patch_card(client, b, workflow_status="review", position=0)

    assert response.status_code == 200
    moved = response.json()
    assert moved["workflow_status"] == "review"
    assert moved["sort_order"] == 0
    assert moved["version"] == 2

    review = column(client, pid, "review")
    assert titles(review) == ["b", "r1", "r2"]
    assert ranks(review) == [0, 1000, 2000]
    backlog = column(client, pid, "backlog")
    assert titles(backlog) == ["a", "c"]
    assert ranks(backlog) == [0, 2000]

    # Siblings were renumbered but not edited: their version and timestamps are untouched.
    for sibling in (r1, r2):
        stored = get_card(client, sibling["id"])
        assert stored["version"] == 1
        assert stored["updated_at"] == sibling["updated_at"]

    event = events(client, pid)[-1]
    assert event["type"] == "CARD_MOVED"
    assert event["subject_id"] == b["id"]
    assert event["payload"]["card"] == moved
    assert event["payload"]["changed_fields"] == []
    assert event["payload"]["from"] == {"workflow_status": "backlog", "sort_order": 1000}
    assert event["payload"]["to"] == {"workflow_status": "review", "sort_order": 0}
    assert event["payload"]["reindexed"] == [
        {"id": r1["id"], "sort_order": 1000},
        {"id": r2["id"], "sort_order": 2000},
    ]


def test_status_without_position_appends(client: TestClient, project: Json) -> None:
    pid = project["id"]
    a = add_card(client, pid, "a")
    add_card(client, pid, "r1", status="review")
    add_card(client, pid, "r2", status="review")

    response = patch_card(client, a, workflow_status="review")

    assert response.status_code == 200
    assert titles(column(client, pid, "review")) == ["r1", "r2", "a"]
    assert response.json()["sort_order"] == 2000


def test_position_alone_reorders_inside_the_column(client: TestClient, project: Json) -> None:
    pid = project["id"]
    add_card(client, pid, "a")
    add_card(client, pid, "b")
    c = add_card(client, pid, "c")

    response = patch_card(client, c, position=0)

    assert response.status_code == 200
    backlog = column(client, pid, "backlog")
    assert titles(backlog) == ["c", "a", "b"]
    assert ranks(backlog) == [0, 1000, 2000]
    assert events(client, pid)[-1]["type"] == "CARD_MOVED"


def test_out_of_range_position_is_clamped(client: TestClient, project: Json) -> None:
    pid = project["id"]
    a = add_card(client, pid, "a")
    add_card(client, pid, "b")
    add_card(client, pid, "c")

    response = patch_card(client, a, position=99)

    assert response.status_code == 200
    assert titles(column(client, pid, "backlog")) == ["b", "c", "a"]


def test_moving_a_card_to_where_it_already_is_changes_nothing(
    client: TestClient, project: Json
) -> None:
    pid = project["id"]
    a = add_card(client, pid, "a")
    add_card(client, pid, "b")
    before = len(events(client, pid))

    same_position = patch_card(client, a, position=0)
    same_status = patch_card(client, a, workflow_status="backlog")

    for response in (same_position, same_status):
        assert response.status_code == 200
        assert response.json() == a
    assert len(events(client, pid)) == before


def test_editing_content_records_card_updated(client: TestClient, project: Json) -> None:
    pid = project["id"]
    card = add_card(client, pid, "old title")

    response = patch_card(
        client, card, description="new description", title="new title", type="issue"
    )

    assert response.status_code == 200
    updated = response.json()
    assert (updated["title"], updated["description"], updated["type"]) == (
        "new title",
        "new description",
        "issue",
    )
    assert updated["version"] == 2
    assert updated["sort_order"] == card["sort_order"]
    event = events(client, pid)[-1]
    assert event["type"] == "CARD_UPDATED"
    assert event["payload"] == {"card": updated, "changed_fields": ["type", "title", "description"]}


def test_edit_and_move_in_one_request_is_one_event(client: TestClient, project: Json) -> None:
    pid = project["id"]
    card = add_card(client, pid, "draft")
    before = len(events(client, pid))

    response = patch_card(client, card, title="final", workflow_status="active")

    assert response.status_code == 200
    recorded = events(client, pid)
    assert len(recorded) == before + 1
    assert recorded[-1]["type"] == "CARD_MOVED"
    assert recorded[-1]["payload"]["changed_fields"] == ["title"]
    assert recorded[-1]["payload"]["to"] == {"workflow_status": "active", "sort_order": 0}


def test_stale_version_is_rejected_and_writes_nothing(client: TestClient, project: Json) -> None:
    pid = project["id"]
    card = add_card(client, pid, "contested")
    assert patch_card(client, card, title="first writer").status_code == 200
    before = len(events(client, pid))

    response = patch_card(client, card, title="second writer", workflow_status="review")

    assert response.status_code == 409
    error = error_of(response)
    assert error["code"] == "STALE_REVISION"
    assert error["details"] == {
        "resource": "card",
        "id": card["id"],
        "current_version": 2,
        "provided_version": 1,
    }
    stored = get_card(client, card["id"])
    assert stored["title"] == "first writer"
    assert stored["workflow_status"] == "backlog"
    assert len(events(client, pid)) == before


def test_project_assertion_must_match(client: TestClient, project: Json) -> None:
    other = create_project(client, name="other project")
    card = add_card(client, project["id"], "mine")

    mismatch = patch_card(client, card, project_id=other["id"], title="hijacked")
    match = patch_card(client, card, project_id=project["id"], title="renamed")

    assert mismatch.status_code == 409
    error = error_of(mismatch)
    assert error["code"] == "PROJECT_MISMATCH"
    assert error["details"] == {
        "card_id": card["id"],
        "card_project_id": project["id"],
        "requested_project_id": other["id"],
    }
    assert match.status_code == 200
    assert match.json()["title"] == "renamed"
    assert len(events(client, other["id"])) == 1  # only its own PROJECT_CREATED


def test_unknown_card_is_404(client: TestClient) -> None:
    get = client.get(f"/v1/cards/{UNKNOWN_CARD}")
    patch = client.patch(f"/v1/cards/{UNKNOWN_CARD}", json={"version": 1, "title": "x"})

    for response in (get, patch):
        assert response.status_code == 404
        assert error_of(response)["details"] == {"resource": "card", "id": UNKNOWN_CARD}


def test_a_completed_card_carries_no_validity_claim(client: TestClient, project: Json) -> None:
    card = add_card(client, project["id"], "H01", card_type="hypothesis")

    completed = patch_card(client, card, workflow_status="completed").json()

    assert completed["workflow_status"] == "completed"
    assert set(completed) == CARD_FIELDS  # no supported/refuted/epistemic field exists
    assert "supported" not in str(completed).lower()


@pytest.mark.parametrize(
    "body",
    [
        {"title": "no type"},
        {"type": "wish", "title": "unknown type"},
        {"type": "task", "title": ""},
        {"type": "task", "title": "x" * 301},
        {"type": "task", "title": "ok", "workflow_status": "done"},
        {"type": "task", "title": "ok", "status": "planned"},
    ],
)
def test_invalid_card_is_rejected(client: TestClient, project: Json, body: dict[str, Any]) -> None:
    response = client.post(f"/v1/projects/{project['id']}/cards", json=body)

    assert response.status_code == 422
    assert error_of(response)["code"] == "VALIDATION_ERROR"
    assert column(client, project["id"], "backlog") == []


@pytest.mark.parametrize(
    "fields",
    [
        {"title": None},
        {"workflow_status": None},
        {"workflow_status": "done"},
        {"position": -1},
        {"status": "review"},
        {"type": "wish"},
    ],
)
def test_invalid_card_patch_is_rejected(
    client: TestClient, project: Json, fields: dict[str, Any]
) -> None:
    card = add_card(client, project["id"], "stable")

    response = patch_card(client, card, **fields)

    assert response.status_code == 422
    assert error_of(response)["code"] == "VALIDATION_ERROR"
    assert get_card(client, card["id"]) == card
