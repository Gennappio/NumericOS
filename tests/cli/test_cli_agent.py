"""Talking to the agent from the command line, with real API and supervisor processes."""

from __future__ import annotations

import json
from typing import Any

from typer.testing import CliRunner, Result

from numericos.cli.main import EXIT_STILL_RUNNING, TURN_EXIT_CODES, app
from tests.conftest import LiveServer, LiveWorker
from tests.lab import Lab

runner = CliRunner()


def cli(server: LiveServer, *args: str) -> Result:
    return runner.invoke(app, [*args, "--api-url", server.base_url])


def cli_json(server: LiveServer, *args: str) -> Any:
    result = cli(server, *args, "--json")
    assert result.exit_code == 0, result.output
    return json.loads(result.stdout)


def test_ask_opens_a_conversation_waits_and_prints_the_answer(
    live_server: LiveServer, live_worker: LiveWorker, live_lab: Lab
) -> None:
    live_lab.repo.write("notes.md", "explicit\n")
    project_id = live_lab.project["id"]

    answered = cli(
        live_server, "agent", "ask", "-p", project_id, "ECHO Stable for small dt.\nREAD notes.md"
    )
    sessions = cli_json(live_server, "agent", "sessions", "-p", project_id)
    found = cli_json(live_server, "agent", "capabilities")

    assert answered.exit_code == TURN_EXIT_CODES["final"] == 0, answered.output
    assert answered.stdout.strip() == "Stable for small dt."  # for a person, the answer itself
    assert "opened" in answered.stderr
    assert "✓ Read" in answered.stderr and "notes.md" in answered.stderr
    assert len(sessions["sessions"]) == 1 and sessions["sessions"][0]["message_count"] == 2
    assert found["available"] is True


def test_a_failed_turn_ends_with_its_own_exit_code_and_json_mode_prints_the_record(
    live_server: LiveServer, live_worker: LiveWorker, live_lab: Lab
) -> None:
    session = live_lab.open_session()

    failed = cli(live_server, "agent", "ask", "-s", session["id"], "FAIL no", "--json")

    assert failed.exit_code == TURN_EXIT_CODES["failed"] == 10
    record = json.loads(failed.stdout)
    assert record["status"] == "failed" and record["markdown"] == "no"


def test_watching_can_give_up_and_a_turn_can_be_cancelled(
    live_server: LiveServer, live_worker: LiveWorker, live_lab: Lab
) -> None:
    session = live_lab.open_session()

    gave_up = cli(live_server, "agent", "ask", "-s", session["id"], "SLEEP 60", "--timeout", "2")
    queued = json.loads(cli(live_server, "agent", "messages", session["id"], "--json").stdout)
    turn = next(m for m in queued["messages"] if m["role"] == "assistant")
    cancelled = cli_json(live_server, "agent", "cancel", turn["id"], "--reason", "enough")

    assert gave_up.exit_code == EXIT_STILL_RUNNING == 14
    assert "it keeps going" in gave_up.stderr
    assert cancelled["cancel_requested_at"] is not None


def test_the_policy_is_shown_and_set_per_task(
    live_server: LiveServer, live_worker: LiveWorker, live_lab: Lab
) -> None:
    project_id = live_lab.project["id"]

    shown = cli(live_server, "agent", "policy", "-p", project_id)
    set_one = cli_json(
        live_server,
        "agent",
        "policy",
        "-p",
        project_id,
        "--task",
        "conversation",
        "--model",
        "claude-haiku-5-5",
        "--effort",
        "low",
    )
    answered = cli(live_server, "agent", "ask", "-p", project_id, "ECHO light", "--json")
    incomplete = cli(live_server, "agent", "policy", "-p", project_id, "--model", "x")

    assert shown.exit_code == 0, shown.output
    assert "conversation           model provider default, effort provider default" in shown.stdout
    assert "clarify" in shown.stdout and "(not available yet)" in shown.stdout
    assert set_one["tasks"]["conversation"] == {"model": "claude-haiku-5-5", "effort": "low"}
    assert set_one["version"] == 1
    record = json.loads(answered.stdout)
    assert (record["model_requested"], record["effort"]) == ("claude-haiku-5-5", "low")
    assert incomplete.exit_code == 2


def test_the_theory_and_the_files_are_asked_for_and_read_from_the_command_line(
    live_server: LiveServer, live_worker: LiveWorker, live_lab: Lab
) -> None:
    project_id = live_lab.project["id"]
    solver = "examples/heat2d-python/heat2d.py"

    nothing = cli(live_server, "doc", "theory", "-p", project_id)
    written = cli(
        live_server,
        "doc",
        "theory",
        "-p",
        project_id,
        "--write",
        "--instructions",
        f"READ {solver}",
    )
    asked = cli(live_server, "doc", "describe", "-p", project_id, solver)
    live_lab.repo.write(solver, "print('edited')\n")
    stale = cli(live_server, "doc", "theory", "-p", project_id)
    both = cli(live_server, "doc", "describe", "-p", project_id, solver, "--scope", "all")
    planned = cli_json(live_server, "doc", "plan", "-p", project_id, "--write")

    assert "not written yet" in nothing.stdout
    assert written.exit_code == 0, written.output
    assert written.stdout.startswith("# Explicit scheme for the 2D heat equation")
    assert "✓ Read" in written.stderr  # the agent's actions go to stderr while it works
    assert asked.stdout.strip() == "asked for 1 file(s) in 1 turn(s)"
    assert f"(out of date: {solver} changed since)" in stale.stdout
    assert both.exit_code == 2
    assert planned["summary"] == "2 card(s) added, 0 changed"
    listed = cli(live_server, "doc", "files", "-p", project_id)
    assert f"{solver}  [code," in listed.stdout
