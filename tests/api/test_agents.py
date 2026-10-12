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
    assert [choice["id"] for choice in found["models"]] == [
        "claude-fable-5-1",
        "claude-opus-5-5",
        "claude-sonnet-5-5",
        "claude-haiku-5-5",
    ]
    assert found["efforts"] == ["low", "medium", "high", "xhigh", "max"]


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
        json={"permission_mode": "read_only", "model": "claude-opus-5-5", "effort": "low"},
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
    assert (session["model"], session["effort"], session["task"]) == (
        "claude-opus-5-5",
        "low",
        "conversation",
    )
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


def test_the_policy_names_a_model_and_effort_per_task(client: TestClient, repo: Repo) -> None:
    project = trusted_project(client, repo.root)
    path = f"/v1/projects/{project['id']}/agent-policy"

    before = client.get(path).json()
    saved = client.put(
        path,
        json={
            "version": 0,
            "tasks": {
                "conversation": {"model": "claude-sonnet-5-5", "effort": "low"},
                "file_description": {"model": "claude-haiku-5-5"},
            },
        },
    )
    again = client.get(path).json()
    stale = client.put(path, json={"version": 0, "tasks": {}})
    unknown = client.put(
        path,
        json={"version": 1, "tasks": {"conversation": {"model": "gpt-9", "effort": "turbo"}}},
    )
    unchanged = client.put(path, json={"version": 1, "tasks": again["tasks"]})

    assert before["version"] == 0 and before["updated_at"] is None
    assert set(before["tasks"]) == {
        "conversation",
        "clarify",
        "resolve",
        "theory",
        "file_description",
        "execution_description",
        "plan",
    }
    # Before anything is saved the provider's suggestions apply: light models where a task is
    # many small turns or a short structured answer, the provider's default elsewhere.
    assert before["tasks"]["conversation"] == {"model": None, "effort": None}
    assert before["tasks"]["theory"] == {"model": None, "effort": None}
    assert before["tasks"]["file_description"] == {"model": "claude-sonnet-5-5", "effort": "low"}
    assert before["tasks"]["plan"] == {"model": "claude-sonnet-5-5", "effort": "medium"}
    assert before["available"] == ["conversation", "theory", "file_description", "plan"]
    assert saved.status_code == 200, saved.text
    assert saved.json()["version"] == 1
    assert again["tasks"]["conversation"] == {"model": "claude-sonnet-5-5", "effort": "low"}
    assert again["tasks"]["file_description"] == {"model": "claude-haiku-5-5", "effort": None}
    assert again["tasks"]["theory"] == {"model": None, "effort": None}
    assert stale.status_code == 409 and error_of(stale)["code"] == "STALE_REVISION"
    assert unknown.status_code == 422
    assert [e["type"] for e in error_of(unknown)["details"]["errors"]] == [
        "unknown_model",
        "unknown_effort",
    ]
    assert unchanged.json()["version"] == 1  # saving the same choices changes nothing
    kinds = [e["type"] for e in events(client, project["id"])]
    assert kinds.count("AGENT_POLICY_UPDATED") == 1


def test_a_session_may_override_the_policy_with_what_the_provider_offers(
    client: TestClient, repo: Repo
) -> None:
    project = trusted_project(client, repo.root)

    refused = client.post(
        f"/v1/projects/{project['id']}/agent-sessions", json={"effort": "extreme"}
    )
    session = client.post(f"/v1/projects/{project['id']}/agent-sessions", json={}).json()
    patched = client.patch(
        f"/v1/agent-sessions/{session['id']}",
        json={"version": 1, "model": "claude-haiku-5-5", "effort": "medium"},
    ).json()
    cleared = client.patch(
        f"/v1/agent-sessions/{session['id']}", json={"version": 2, "model": None}
    ).json()

    assert refused.status_code == 422
    assert (session["model"], session["effort"]) == (None, None)
    assert (patched["model"], patched["effort"]) == ("claude-haiku-5-5", "medium")
    assert (cleared["model"], cleared["effort"]) == (None, "medium")
