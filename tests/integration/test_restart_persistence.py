"""Stopping and starting the API process loses nothing: state, ledger and cursors survive."""

from __future__ import annotations

from typing import Any

import httpx

from tests.conftest import LiveServer
from tests.integration.helpers import event_stream, get, ledger, new_card, new_project, take


def snapshot(server: LiveServer, project_id: str) -> dict[str, Any]:
    return {
        "projects": get(server, "/v1/projects"),
        "project": get(server, f"/v1/projects/{project_id}"),
        "board": get(server, f"/v1/projects/{project_id}/board"),
        "ledger": ledger(server, project_id),
    }


def test_state_and_ledger_are_identical_after_a_restart(live_server: LiveServer) -> None:
    project = new_project(live_server, "Survives restarts")
    first = new_card(live_server, project["id"], "first")
    second = new_card(live_server, project["id"], "second", type="hypothesis")
    moved = httpx.patch(
        f"{live_server.base_url}/v1/cards/{second['id']}",
        json={"version": second["version"], "workflow_status": "review", "position": 0},
    )
    edited = httpx.patch(
        f"{live_server.base_url}/v1/cards/{first['id']}",
        json={"version": first["version"], "title": "first, edited"},
    )
    assert (moved.status_code, edited.status_code) == (200, 200)
    before = snapshot(live_server, project["id"])
    assert len(before["ledger"]) == 5

    live_server.stop()
    live_server.start()

    assert snapshot(live_server, project["id"]) == before

    # The ledger continues where it stopped: no sequence number is ever reused.
    new_card(live_server, project["id"], "after the restart")
    last_before = before["ledger"][-1]["seq"]
    assert [event["seq"] for event in ledger(live_server, project["id"])][-2:] == [
        last_before,
        last_before + 1,
    ]


def test_a_subscriber_resumes_across_a_restart_with_its_last_event_id(
    live_server: LiveServer,
) -> None:
    project = new_project(live_server)
    new_card(live_server, project["id"], "before the restart")
    with event_stream(live_server, project["id"]) as stream:
        last_seen = take(stream, 2)[-1]["seq"]

    live_server.stop()
    live_server.start()
    new_card(live_server, project["id"], "committed after the restart")

    with event_stream(live_server, project["id"], last_event_id=last_seen) as stream:
        resumed = take(stream, 1)
        new_card(live_server, project["id"], "and one more")
        following = take(stream, 1)

    titles = [event["payload"]["card"]["title"] for event in resumed + following]
    assert titles == ["committed after the restart", "and one more"]
    assert resumed[0]["seq"] == last_seen + 1
