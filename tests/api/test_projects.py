from __future__ import annotations

from typing import Any

import pytest
from fastapi.testclient import TestClient

from numericos.core.ids import is_valid_id
from tests.api.helpers import UNKNOWN_PROJECT, create_project, error_of, events

PROJECT_FIELDS = {
    "id",
    "name",
    "research_question",
    "description",
    "root_path",
    "is_demo",
    "version",
    "created_at",
    "updated_at",
}


def test_create_returns_the_public_representation_and_one_event(client: TestClient) -> None:
    response = client.post(
        "/v1/projects",
        json={
            "name": "Sparse Poisson",
            "research_question": "Does CSR assembly beat the dense baseline at equal error?",
            "root_path": "/work/poisson",
        },
        headers={"X-Actor": "web:local"},
    )

    assert response.status_code == 201
    project = response.json()
    assert set(project) == PROJECT_FIELDS
    assert project["id"].startswith("prj_")
    assert is_valid_id(project["id"])
    assert project["name"] == "Sparse Poisson"
    assert project["root_path"] == "/work/poisson"
    assert project["is_demo"] is False
    assert project["version"] == 1
    assert project["created_at"] == project["updated_at"]
    assert project["created_at"].endswith("Z")

    (event,) = events(client, project["id"])
    assert event["type"] == "PROJECT_CREATED"
    assert event["subject_id"] == project["id"]
    assert event["actor"] == "web:local"
    assert event["producer"] == "api"
    assert event["severity"] == "info"
    assert event["correlation_id"] == response.headers["x-correlation-id"]
    assert event["payload"] == {"project": project}


def test_projects_are_listed_in_creation_order(client: TestClient) -> None:
    first = create_project(client, name="first")
    second = create_project(client, name="second")

    body = client.get("/v1/projects").json()

    assert [project["id"] for project in body["projects"]] == [first["id"], second["id"]]


def test_get_returns_the_stored_project(client: TestClient) -> None:
    project = create_project(client, research_question="Is FTCS stable at dt = 0.01?")

    response = client.get(f"/v1/projects/{project['id']}")

    assert response.status_code == 200
    assert response.json() == project


def test_unknown_project_is_a_typed_404(client: TestClient) -> None:
    response = client.get(f"/v1/projects/{UNKNOWN_PROJECT}")

    assert response.status_code == 404
    error = error_of(response)
    assert error["code"] == "NOT_FOUND"
    assert error["details"] == {"resource": "project", "id": UNKNOWN_PROJECT}


def test_patch_changes_fields_bumps_version_and_records_one_event(client: TestClient) -> None:
    project = create_project(client, research_question="old question")
    url = f"/v1/projects/{project['id']}"

    response = client.patch(
        url, json={"version": 1, "name": "Heat 2D (explicit)", "research_question": "new question"}
    )

    assert response.status_code == 200
    updated = response.json()
    assert updated["name"] == "Heat 2D (explicit)"
    assert updated["research_question"] == "new question"
    assert updated["version"] == 2
    assert updated["created_at"] == project["created_at"]
    assert updated["updated_at"] >= project["updated_at"]
    assert client.get(url).json() == updated

    recorded = events(client, project["id"])
    assert [event["type"] for event in recorded] == ["PROJECT_CREATED", "PROJECT_UPDATED"]
    assert recorded[-1]["payload"] == {
        "changed_fields": ["name", "research_question"],
        "project": updated,
    }


def test_stale_version_is_rejected_and_writes_nothing(client: TestClient) -> None:
    project = create_project(client)
    url = f"/v1/projects/{project['id']}"

    response = client.patch(url, json={"version": 7, "name": "lost update"})

    assert response.status_code == 409
    error = error_of(response)
    assert error["code"] == "STALE_REVISION"
    assert error["details"]["current_version"] == 1
    assert error["details"]["provided_version"] == 7
    assert client.get(url).json() == project
    assert len(events(client, project["id"])) == 1


def test_patch_without_changes_is_a_no_op(client: TestClient) -> None:
    project = create_project(client)
    url = f"/v1/projects/{project['id']}"

    same_values = client.patch(url, json={"version": 1, "name": project["name"]})
    only_version = client.patch(url, json={"version": 1})

    for response in (same_values, only_version):
        assert response.status_code == 200
        assert response.json() == project
    assert len(events(client, project["id"])) == 1


def test_explicit_null_clears_the_reference_path(client: TestClient) -> None:
    project = create_project(client, root_path="/work/heat")

    response = client.patch(f"/v1/projects/{project['id']}", json={"version": 1, "root_path": None})

    assert response.status_code == 200
    assert response.json()["root_path"] is None
    assert response.json()["version"] == 2


@pytest.mark.parametrize(
    "body",
    [
        {},
        {"name": ""},
        {"name": "x" * 201},
        {"name": "x", "status": "planned"},
        {"name": "x", "root_path": "relative/path"},
    ],
)
def test_invalid_project_is_rejected_and_nothing_is_created(
    client: TestClient, body: dict[str, Any]
) -> None:
    response = client.post("/v1/projects", json=body)

    assert response.status_code == 422
    assert error_of(response)["code"] == "VALIDATION_ERROR"
    assert error_of(response)["details"]["errors"]
    assert client.get("/v1/projects").json() == {"projects": []}


@pytest.mark.parametrize(
    "body",
    [
        {"name": "missing version"},
        {"version": 0, "name": "x"},
        {"version": 1, "name": None},
        {"version": 1, "nmae": "typo"},
        {"version": 1, "root_path": "relative"},
    ],
)
def test_invalid_patch_is_rejected(client: TestClient, body: dict[str, Any]) -> None:
    project = create_project(client)

    response = client.patch(f"/v1/projects/{project['id']}", json=body)

    assert response.status_code == 422
    assert error_of(response)["code"] == "VALIDATION_ERROR"
    assert len(events(client, project["id"])) == 1
