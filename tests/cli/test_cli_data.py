"""Data commands against a real API process: the CLI and the API see the same durable state."""

from __future__ import annotations

import json
from typing import Any

import httpx
from typer.testing import CliRunner, Result

from numericos.cli.main import EXIT_API_ERROR, app
from tests.conftest import LiveServer

runner = CliRunner()
UNKNOWN_PROJECT = "prj_01J9W2Z4K7QX8YB3N5M6T0R1S2"


def run(server: LiveServer, *args: str) -> Result:
    return runner.invoke(app, [*args, "--api-url", server.base_url])


def run_json(server: LiveServer, *args: str) -> Any:
    result = run(server, *args, "--json")
    assert result.exit_code == 0, result.output
    assert result.stderr == ""
    return json.loads(result.stdout)


def test_project_created_by_the_cli_is_visible_through_the_api(live_server: LiveServer) -> None:
    created = run_json(
        live_server, "project", "add", "Heat 2D", "--question", "Is FTCS stable at dt = 0.01?"
    )

    listed = run_json(live_server, "project", "list")
    shown = run_json(live_server, "project", "show", created["id"])
    via_api = httpx.get(f"{live_server.base_url}/v1/projects/{created['id']}").json()

    assert created["name"] == "Heat 2D"
    assert created["research_question"] == "Is FTCS stable at dt = 0.01?"
    assert [project["id"] for project in listed["projects"]] == [created["id"]]
    assert shown == created == via_api


def test_project_created_through_the_api_is_visible_in_the_cli(live_server: LiveServer) -> None:
    project = httpx.post(f"{live_server.base_url}/v1/projects", json={"name": "from api"}).json()

    listed = run_json(live_server, "project", "list")

    assert listed["projects"] == [project]


def test_cards_can_be_added_moved_and_listed(live_server: LiveServer) -> None:
    project = run_json(live_server, "project", "add", "Board")
    first = run_json(
        live_server, "card", "add", "-p", project["id"], "--type", "hypothesis", "--title", "H01"
    )
    second = run_json(
        live_server, "card", "add", "-p", project["id"], "-t", "task", "--title", "T01"
    )

    moved = run_json(live_server, "card", "move", second["id"], "--status", "review")
    renamed = run_json(live_server, "card", "update", first["id"], "--title", "H01 (revised)")
    board = run_json(live_server, "card", "list", "--project", project["id"])
    ledger = run_json(live_server, "events", "list", "--project", project["id"])

    assert (moved["workflow_status"], moved["version"]) == ("review", 2)
    assert (renamed["title"], renamed["version"]) == ("H01 (revised)", 2)
    assert [(card["title"], card["workflow_status"]) for card in board["cards"]] == [
        ("H01 (revised)", "backlog"),
        ("T01", "review"),
    ]
    assert [event["type"] for event in ledger["events"]] == [
        "PROJECT_CREATED",
        "CARD_CREATED",
        "CARD_CREATED",
        "CARD_MOVED",
        "CARD_UPDATED",
    ]
    assert {event["actor"] for event in ledger["events"]} == {"cli:local"}
    assert run_json(live_server, "card", "show", second["id"]) == moved


def test_project_update_uses_the_latest_version_unless_one_is_given(
    live_server: LiveServer,
) -> None:
    project = run_json(live_server, "project", "add", "Draft")

    renamed = run_json(live_server, "project", "update", project["id"], "--name", "Final")
    stale = run(
        live_server,
        "project",
        "update",
        project["id"],
        "--name",
        "Lost",
        "--version",
        "1",
        "--json",
    )

    assert (renamed["name"], renamed["version"]) == ("Final", 2)
    assert stale.exit_code == EXIT_API_ERROR
    assert stale.stdout == ""
    assert json.loads(stale.stderr)["error"]["code"] == "STALE_REVISION"


def test_api_errors_exit_1_with_the_envelope_on_stderr(live_server: LiveServer) -> None:
    machine = run(live_server, "project", "show", UNKNOWN_PROJECT, "--json")
    human = run(live_server, "project", "show", UNKNOWN_PROJECT)

    assert machine.exit_code == EXIT_API_ERROR
    assert machine.stdout == ""
    assert json.loads(machine.stderr)["error"]["code"] == "NOT_FOUND"
    assert human.exit_code == EXIT_API_ERROR
    assert human.stdout == ""
    assert "error [NOT_FOUND] (HTTP 404)" in human.stderr


def test_usage_errors_exit_2(live_server: LiveServer) -> None:
    missing_option = run(live_server, "card", "add", "--project", "prj_x", "--title", "no type")
    bad_choice = run(
        live_server, "card", "add", "-p", "prj_x", "--type", "wish", "--title", "bad type"
    )
    nothing_to_change = run(live_server, "card", "move", "card_x")

    for result in (missing_option, bad_choice, nothing_to_change):
        assert result.exit_code == 2, result.output
        assert result.stdout == ""


def test_human_output_is_readable(live_server: LiveServer) -> None:
    project = run_json(live_server, "project", "add", "Readable")
    run_json(live_server, "card", "add", "-p", project["id"], "-t", "issue", "--title", "Wrong BC")

    projects = run(live_server, "project", "list")
    board = run(live_server, "card", "list", "-p", project["id"])
    ledger = run(live_server, "events", "list", "-p", project["id"])

    assert f"{project['id']}  v1  Readable" in projects.stdout
    assert "backlog (1)" in board.stdout
    assert "[issue] Wrong BC" in board.stdout
    assert "completed (0)" in board.stdout
    assert "PROJECT_CREATED" in ledger.stdout
    assert "cli:local" in ledger.stdout


def test_seed_demo_is_explicit_marked_and_idempotent(live_server: LiveServer) -> None:
    assert run_json(live_server, "project", "list") == {"projects": []}

    first = run_json(live_server, "seed-demo")
    second = run_json(live_server, "seed-demo")

    assert first["created"] is True
    assert second["created"] is False
    assert first["project"]["is_demo"] is True
    assert second["project"]["id"] == first["project"]["id"]
    assert first["card_count"] == second["card_count"] > 0
    assert len(run_json(live_server, "project", "list")["projects"]) == 1
    ledger = run_json(live_server, "events", "list", "-p", first["project"]["id"])
    assert {event["actor"] for event in ledger["events"]} == {"cli:seed"}
    assert "[demo]" in run(live_server, "project", "list").stdout
