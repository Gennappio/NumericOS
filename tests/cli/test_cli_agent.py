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
