"""Conversations with the agent through the API: sessions, prompts, queued turns, cancellation.
Nothing is executed here; the supervisor tests cover that."""

from __future__ import annotations

import sys
from pathlib import Path

from fastapi.testclient import TestClient

from numericos.api.app import create_app
from numericos.config import Settings
from tests.api.helpers import create_project, error_of, events, trusted_project
from tests.gitrepo import Repo


def test_capabilities_are_found_by_running_the_command(client: TestClient) -> None:
    found = client.get("/v1/agents/capabilities").json()

    assert found["provider"] == "claude_code"
    assert found["available"] is True
    assert found["version"] == "9.9.9 (fake claude)"
    assert found["path"] == sys.executable
    assert found["problem"] is None


def test_a_missing_command_is_reported_and_blocks_a_conversation(
    tmp_path: Path, repo: Repo
) -> None:
    settings = Settings(data_dir=tmp_path / "data", claude_command=["no-such-agent-command"])
    settings.data_dir.mkdir(parents=True)
    from numericos.persistence import migrate
    from numericos.persistence.engine import make_engine

    migrate.upgrade(make_engine(settings.db_path))
    with TestClient(create_app(settings)) as client:
        found = client.get("/v1/agents/capabilities").json()
        project = trusted_project(client, repo.root)
        refused = client.post(f"/v1/projects/{project['id']}/agent-sessions", json={})

    assert found["available"] is False
    assert "not found on the PATH" in found["problem"]
    assert refused.status_code == 409
    assert error_of(refused)["code"] == "AGENT_UNAVAILABLE"
    assert error_of(refused)["details"]["command"] == ["no-such-agent-command"]


def test_a_conversation_needs_a_trusted_directory(client: TestClient, repo: Repo) -> None:
    untrusted = create_project(client, root_path=str(repo.root))

    refused = client.post(f"/v1/projects/{untrusted['id']}/agent-sessions", json={})

    assert refused.status_code == 409
    assert error_of(refused)["code"] == "EXECUTION_NOT_TRUSTED"


def test_a_session_is_opened_listed_and_renamed(client: TestClient, repo: Repo) -> None:
    project = trusted_project(client, repo.root, research_question="Is the scheme stable?")

    created = client.post(
        f"/v1/projects/{project['id']}/agent-sessions",
        json={"permission_mode": "read_only", "model": "opus"},
    )
    session = created.json()
    listed = client.get(f"/v1/projects/{project['id']}/agent-sessions").json()
    renamed = client.patch(
        f"/v1/agent-sessions/{session['id']}",
        json={"version": 1, "title": "Stability", "permission_mode": "full"},
    ).json()
    stale = client.patch(f"/v1/agent-sessions/{session['id']}", json={"version": 1, "title": "x"})

    assert created.status_code == 201
    assert session["title"] == "New conversation"
    assert session["permission_mode"] == "read_only"
    assert session["model"] == "opus"
    assert session["cwd"] == str(repo.root)
    assert len(session["native_session_id"]) == 36
    assert session["message_count"] == 0
    assert [item["id"] for item in listed["sessions"]] == [session["id"]]
    assert (renamed["title"], renamed["permission_mode"], renamed["version"]) == (
        "Stability",
        "full",
        2,
    )
    assert stale.status_code == 409 and error_of(stale)["code"] == "STALE_REVISION"
    kinds = [event["type"] for event in events(client, project["id"])]
    assert kinds[-2:] == ["AGENT_SESSION_STARTED", "AGENT_SESSION_UPDATED"]


def test_a_prompt_records_the_question_and_queues_the_answer(
    client: TestClient, repo: Repo
) -> None:
    project = trusted_project(client, repo.root)
    session = client.post(f"/v1/projects/{project['id']}/agent-sessions", json={}).json()

    sent = client.post(
        f"/v1/agent-sessions/{session['id']}/messages",
        json={"content": "Why is the explicit scheme unstable for large dt?"},
    )
    turn = sent.json()
    messages = client.get(f"/v1/agent-sessions/{session['id']}/messages").json()["messages"]
    again = client.post(f"/v1/agent-sessions/{session['id']}/messages", json={"content": "And?"})
    renamed = client.get(f"/v1/agent-sessions/{session['id']}").json()

    assert sent.status_code == 201
    assert (turn["role"], turn["status"], turn["markdown"]) == ("assistant", "queued", "")
    assert [(m["role"], m["status"]) for m in messages] == [
        ("user", "final"),
        ("assistant", "queued"),
    ]
    assert messages[0]["markdown"] == "Why is the explicit scheme unstable for large dt?"
    assert turn["prompt_message_id"] == messages[0]["id"]
    assert turn["activity"] == [] and turn["files_read"] == []
    # One turn at a time per session, as the provider's sessions work.
    assert again.status_code == 409
    assert error_of(again)["code"] == "SESSION_BUSY"
    assert error_of(again)["details"]["message_id"] == turn["id"]
    # The first prompt names the conversation.
    assert renamed["title"] == "Why is the explicit scheme unstable for large dt?"
    assert renamed["message_count"] == 2
    queued = [e for e in events(client, project["id"]) if e["type"] == "AGENT_TURN_QUEUED"]
    assert queued[0]["subject_id"] == turn["id"]
    assert queued[0]["payload"]["prompt_excerpt"].startswith("Why is the explicit")


def test_a_queued_turn_is_cancelled_at_once(client: TestClient, repo: Repo) -> None:
    project = trusted_project(client, repo.root)
    session = client.post(f"/v1/projects/{project['id']}/agent-sessions", json={}).json()
    turn = client.post(
        f"/v1/agent-sessions/{session['id']}/messages", json={"content": "Hello"}
    ).json()

    cancelled = client.post(f"/v1/messages/{turn['id']}:cancel", json={"reason": "typo"}).json()
    repeated = client.post(f"/v1/messages/{turn['id']}:cancel").json()
    free_again = client.post(
        f"/v1/agent-sessions/{session['id']}/messages", json={"content": "Hello, again"}
    )

    assert (cancelled["status"], cancelled["status_reason"]) == ("cancelled", "typo")
    assert cancelled["cancel_requested_at"] is not None
    assert repeated["version"] == cancelled["version"]  # nothing changed the second time
    assert free_again.status_code == 201
    kinds = [e["type"] for e in events(client, project["id"]) if e["subject_id"] == turn["id"]]
    assert kinds == ["AGENT_TURN_QUEUED", "AGENT_TURN_CANCEL_REQUESTED", "AGENT_TURN_FINISHED"]


def test_requests_are_validated(client: TestClient, repo: Repo) -> None:
    project = trusted_project(client, repo.root)
    session = client.post(f"/v1/projects/{project['id']}/agent-sessions", json={}).json()

    empty = client.post(f"/v1/agent-sessions/{session['id']}/messages", json={"content": ""})
    unknown_mode = client.post(
        f"/v1/projects/{project['id']}/agent-sessions", json={"permission_mode": "yolo"}
    )
    missing = client.get("/v1/messages/msg_01J9W2Z4K7QX8YB3N5M6T0R1S2")

    assert empty.status_code == 422
    assert unknown_mode.status_code == 422
    assert missing.status_code == 404 and error_of(missing)["details"]["resource"] == "message"
