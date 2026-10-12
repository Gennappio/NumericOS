"""Turns of the agent under a real supervisor, with the stand-in for Claude Code as the agent:
what is observed, what the permission mode refuses, how a turn ends, stopping and recovery."""

from __future__ import annotations

import json
from pathlib import Path

import psutil
import pytest

from numericos.agents import layout
from numericos.agents import supervisor as supervisor_module
from numericos.config import Settings
from numericos.executor.worker import Worker
from tests.lab import Lab, drive, end_all_turns


def ended(lab: Lab, message_id: str) -> bool:
    return lab.turn_status(message_id) not in ("queued", "running")


def test_a_turn_is_executed_and_everything_observed_is_recorded(
    lab: Lab, supervisor: Worker, settings: Settings
) -> None:
    lab.repo.write("notes.md", "explicit Euler\n")
    session = lab.open_session()
    turn = lab.ask(session, "Explain the scheme.\nREAD notes.md")

    drive(supervisor, lambda: ended(lab, turn["id"]))

    answer = lab.message(turn["id"])
    assert answer["status"] == "final"
    assert answer["markdown"].startswith("You asked: Explain the scheme.")
    assert "$$" in answer["markdown"]
    assert answer["model"] == "fake-model"
    assert answer["cost_usd"] == 0.0123
    assert answer["usage"]["output_tokens"] == 34
    assert answer["num_turns"] == 2
    assert answer["files_read"] == ["notes.md"] and answer["files_written"] == []
    assert answer["permission_denials"] == []
    assert answer["started_at"] is not None and answer["finished_at"] is not None
    assert answer["exit_code"] == 0
    assert [item["kind"] for item in answer["activity"]] == ["text", "tool"]
    assert answer["activity"][0]["text"] == "Looking at the repository."
    tool = answer["activity"][1]["tool"]
    assert (tool["name"], tool["summary"], tool["ok"]) == ("Read", "notes.md", True)
    assert [e["type"] for e in lab.turn_events(turn["id"])] == [
        "AGENT_TURN_QUEUED",
        "AGENT_TURN_STARTED",
        "AGENT_TURN_FINISHED",
    ]
    finished = lab.turn_events(turn["id"])[-1]
    assert finished["payload"]["status"] == "final"
    assert finished["payload"]["cost_usd"] == 0.0123
    assert finished["producer"] == "worker"

    # The turn's files: the prompt as sent, the argument vector, the complete stream.
    turn_dir = layout.turn_dir(settings.data_dir, turn["id"])
    prompt = (turn_dir / layout.PROMPT).read_text()
    assert prompt.startswith("Explain the scheme.\nREAD notes.md")
    assert "permission mode edit" in prompt
    spec = json.loads((turn_dir / layout.SPEC).read_text())
    assert spec["cwd"] == str(lab.repo.root) and spec["resume"] is False
    assert "--session-id" in spec["argv"] and "--resume" not in spec["argv"]
    assert spec["argv"][spec["argv"].index("--permission-mode") + 1] == "acceptEdits"
    records = [json.loads(line) for line in (turn_dir / layout.STREAM).read_text().splitlines()]
    assert records[0]["type"] == "init" or records[0]["subtype"] == "init"
    assert records[-1]["type"] == "result"
    assert records[0]["session_id"] == session["native_session_id"]


def test_the_next_turn_resumes_the_same_provider_session(
    lab: Lab, supervisor: Worker, settings: Settings
) -> None:
    session = lab.open_session()
    first = lab.ask(session, "ECHO one")
    drive(supervisor, lambda: ended(lab, first["id"]))

    second = lab.ask(session, "ECHO two")
    drive(supervisor, lambda: ended(lab, second["id"]))

    assert lab.message(first["id"])["markdown"] == "one"
    assert lab.message(second["id"])["markdown"] == "two"
    spec = json.loads((layout.turn_dir(settings.data_dir, second["id"]) / layout.SPEC).read_text())
    assert spec["resume"] is True
    assert spec["argv"][spec["argv"].index("--resume") + 1] == session["native_session_id"]
    assert lab.turn_events(second["id"])[1]["payload"]["resume"] is True


def test_what_the_permission_mode_refuses_is_recorded_not_hidden(
    lab: Lab, supervisor: Worker
) -> None:
    cautious = lab.open_session(permission_mode="read_only")
    refused = lab.ask(cautious, "WRITE out.txt::hello")
    drive(supervisor, lambda: ended(lab, refused["id"]))

    trusting = lab.open_session(permission_mode="edit")
    allowed = lab.ask(trusting, "WRITE out.txt::hello")
    drive(supervisor, lambda: ended(lab, allowed["id"]))

    first = lab.message(refused["id"])
    assert first["status"] == "final"
    assert first["files_written"] == []
    assert [d["tool_name"] for d in first["permission_denials"]] == ["Write"]
    assert first["permission_denials"][0]["summary"] == "out.txt"
    assert (
        not (lab.repo.root / "out.txt").exists()
        or (lab.repo.root / "out.txt").read_text() == "hello"
    )
    second = lab.message(allowed["id"])
    assert second["files_written"] == ["out.txt"]
    assert second["permission_denials"] == []
    assert (lab.repo.root / "out.txt").read_text() == "hello"
    assert lab.turn_events(allowed["id"])[-1]["payload"]["files_written"] == 1


def test_a_failed_turn_and_an_agent_that_leaves_without_answering(
    lab: Lab, supervisor: Worker
) -> None:
    session = lab.open_session()
    failed = lab.ask(session, "FAIL the model refused")
    drive(supervisor, lambda: ended(lab, failed["id"]))
    gone = lab.ask(session, "EXIT 3")
    drive(supervisor, lambda: ended(lab, gone["id"]))

    first = lab.message(failed["id"])
    assert first["status"] == "failed"
    assert first["status_reason"] == "error_during_execution: the model refused"
    assert first["markdown"] == "the model refused"
    assert first["cost_usd"] == 0.0123  # what it cost is known even when it failed
    second = lab.message(gone["id"])
    assert second["status"] == "interrupted"
    assert second["status_reason"] == (
        "the agent process ended without a final answer: fake claude: leaving without an answer"
    )
    assert second["exit_code"] == 3
    assert second["cost_usd"] is None
    assert [e["severity"] for e in lab.turn_events(gone["id"])][-1] == "error"


def test_a_running_turn_is_stopped_on_request(lab: Lab, supervisor: Worker) -> None:
    session = lab.open_session()
    turn = lab.ask(session, "SLEEP 60")
    # Running, and already heard from: what was observed before the stop must survive it.
    drive(supervisor, lambda: lab.message(turn["id"])["activity"])
    pid = lab.message(turn["id"])["pid"]

    requested = lab.cancel_turn(turn["id"], "seen enough")
    drive(supervisor, lambda: ended(lab, turn["id"]))

    assert requested["status"] == "running" and requested["cancel_requested_at"] is not None
    stopped = lab.message(turn["id"])
    assert (stopped["status"], stopped["status_reason"]) == ("cancelled", "seen enough")
    assert stopped["activity"][0]["text"] == "Looking at the repository."
    assert [e["type"] for e in lab.turn_events(turn["id"])] == [
        "AGENT_TURN_QUEUED",
        "AGENT_TURN_STARTED",
        "AGENT_TURN_CANCEL_REQUESTED",
        "AGENT_TURN_FINISHED",
    ]
    assert not psutil.pid_exists(pid)
    # The session is free again.
    assert lab.ask(session, "ECHO after")["status"] == "queued"


def test_sessions_are_served_in_parallel_but_each_one_in_order(
    lab: Lab, supervisor: Worker
) -> None:
    one, two = lab.open_session(), lab.open_session()
    slow = lab.ask(one, "SLEEP 1.5\nECHO slow")
    quick = lab.ask(two, "ECHO quick")

    drive(supervisor, lambda: ended(lab, quick["id"]))

    assert lab.turn_status(slow["id"]) == "running"  # the quick one did not wait for the slow one
    drive(supervisor, lambda: ended(lab, slow["id"]))
    assert lab.message(slow["id"])["markdown"] == "slow"


def test_a_claimed_turn_whose_worker_died_is_queued_again_and_served(
    lab: Lab, settings: Settings, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(supervisor_module, "STARTUP_GRACE_SECONDS", 0.0)
    first = Worker(settings, poll_interval=0.05, heartbeat_interval=0.2)
    first.start()
    monkeypatch.setattr(first.turns, "_launch", lambda message_id: None)  # claims, never starts
    session = lab.open_session()
    turn = lab.ask(session, "ECHO recovered")
    first.tick()
    claimed = lab.message(turn["id"])
    first.stop()

    second = Worker(settings, poll_interval=0.05, heartbeat_interval=0.2, stale_after=0.0)
    second.start()
    try:
        drive(second, lambda: ended(lab, turn["id"]))
    finally:
        second.stop()
        end_all_turns(settings.data_dir)

    assert claimed["status"] == "queued" and claimed["worker_id"] == first.id
    answer = lab.message(turn["id"])
    assert answer["status"] == "final" and answer["markdown"] == "recovered"
    assert answer["worker_id"] == second.id
    kinds = [e["type"] for e in lab.turn_events(turn["id"])]
    assert kinds == [
        "AGENT_TURN_QUEUED",
        "AGENT_TURN_ADOPTED",
        "AGENT_TURN_REQUEUED",
        "AGENT_TURN_STARTED",
        "AGENT_TURN_FINISHED",
    ]


def test_a_running_turn_outlives_its_supervisor_and_is_taken_over(
    lab: Lab, settings: Settings
) -> None:
    first = Worker(settings, poll_interval=0.05, heartbeat_interval=0.2)
    first.start()
    session = lab.open_session()
    turn = lab.ask(session, "SLEEP 1\nECHO survived")
    drive(first, lambda: lab.turn_status(turn["id"]) == "running")
    first.stop()  # the agent process keeps going

    second = Worker(settings, poll_interval=0.05, heartbeat_interval=0.2, stale_after=0.0)
    second.start()
    try:
        drive(second, lambda: ended(lab, turn["id"]))
    finally:
        second.stop()
        end_all_turns(settings.data_dir)

    answer = lab.message(turn["id"])
    assert answer["status"] == "final" and answer["markdown"] == "survived"
    assert answer["worker_id"] == second.id
    adopted = next(e for e in lab.turn_events(turn["id"]) if e["type"] == "AGENT_TURN_ADOPTED")
    assert adopted["payload"] == {"previous_worker_id": first.id, "worker_id": second.id}


def test_a_turn_cancelled_before_it_started_never_starts(lab: Lab, settings: Settings) -> None:
    worker = Worker(settings, poll_interval=0.05, heartbeat_interval=0.2)
    worker.start()
    try:
        session = lab.open_session()
        turn = lab.ask(session, "ECHO never")
        lab.cancel_turn(turn["id"], "changed my mind")
        worker.tick()
    finally:
        worker.stop()

    answer = lab.message(turn["id"])
    assert (answer["status"], answer["status_reason"]) == ("cancelled", "changed my mind")
    assert not Path(layout.turn_dir(settings.data_dir, turn["id"])).exists()


def test_the_policy_of_the_project_chooses_model_and_effort_unless_the_session_does(
    lab: Lab, supervisor: Worker, settings: Settings
) -> None:
    path = f"/v1/projects/{lab.project['id']}/agent-policy"
    lab.http.put(
        path,
        json={
            "version": 0,
            "tasks": {"conversation": {"model": "claude-sonnet-5-5", "effort": "low"}},
        },
    )
    by_policy = lab.ask(lab.open_session(), "ECHO by policy")
    drive(supervisor, lambda: ended(lab, by_policy["id"]))
    by_session = lab.ask(
        lab.open_session(model="claude-haiku-5-5", effort="max"), "ECHO by session"
    )
    drive(supervisor, lambda: ended(lab, by_session["id"]))

    first = lab.message(by_policy["id"])
    assert (first["model_requested"], first["effort"]) == ("claude-sonnet-5-5", "low")
    assert first["model"] == "claude-sonnet-5-5"  # what the agent reported it used
    spec = json.loads(
        (layout.turn_dir(settings.data_dir, by_policy["id"]) / layout.SPEC).read_text()
    )
    assert spec["argv"][spec["argv"].index("--model") + 1] == "claude-sonnet-5-5"
    assert spec["argv"][spec["argv"].index("--effort") + 1] == "low"
    assert lab.turn_events(by_policy["id"])[1]["payload"]["model"] == "claude-sonnet-5-5"
    second = lab.message(by_session["id"])
    assert (second["model_requested"], second["effort"]) == ("claude-haiku-5-5", "max")
    # What the turn consumed of the plan, as the provider reported it.
    assert first["plan_usage"]["five_hour"]["utilization"] == 0.21
    assert first["plan_usage"]["seven_day"]["utilization"] == 0.04
    assert first["plan_usage"]["using_overage"] is False
