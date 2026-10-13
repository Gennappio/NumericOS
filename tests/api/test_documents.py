"""Documents through the API: what is queued for the agent and what is told meanwhile.
Nothing is executed here; the supervisor tests cover what the agent's answer becomes."""

from __future__ import annotations

from fastapi.testclient import TestClient

from tests.api.helpers import add_card, create_project, error_of, events, trusted_project
from tests.gitrepo import Repo

SOLVER = "examples/heat2d-python/heat2d.py"


def messages_of(client: TestClient, session_id: str) -> list[dict[str, object]]:
    listed: list[dict[str, object]] = client.get(
        f"/v1/agent-sessions/{session_id}/messages"
    ).json()["messages"]
    return listed


def test_the_theory_is_asked_of_the_agent_in_a_session_of_its_own(
    client: TestClient, repo: Repo
) -> None:
    project = trusted_project(client, repo.root, research_question="Is the scheme stable?")
    base = f"/v1/projects/{project['id']}"

    nothing = client.get(f"{base}/theory").json()
    asked = client.post(f"{base}/theory:generate", json={"instructions": "Scrivi in italiano."})
    document = asked.json()
    again = client.post(f"{base}/theory:generate")
    conversations = client.get(f"{base}/agent-sessions").json()["sessions"]
    every = client.get(f"{base}/agent-sessions", params={"task": "all"}).json()["sessions"]
    prompt, turn = messages_of(client, document["session_id"])

    assert nothing == {"document": None}
    assert asked.status_code == 202
    assert (document["kind"], document["key"], document["status"]) == (
        "theory",
        "theory",
        "generating",
    )
    assert document["version"] == 0 and document["markdown"] == ""
    assert document["pending_message_id"] == turn["id"]
    assert document["instructions"] == "Scrivi in italiano."
    assert again.status_code == 409 and error_of(again)["code"] == "GENERATION_PENDING"
    # Its session is not a conversation: it is found among the sessions of its task.
    assert conversations == []
    assert [(s["task"], s["permission_mode"]) for s in every] == [("theory", "read_only")]
    assert str(prompt["markdown"]).startswith("[NumericOS task: theory]")
    assert "Research question: Is the scheme stable?" in str(prompt["markdown"])
    assert str(prompt["markdown"]).rstrip().endswith("Scrivi in italiano.")
    assert turn["status"] == "queued"
    queued = [e for e in events(client, project["id"]) if e["type"] == "DOCUMENT_GENERATION_QUEUED"]
    assert queued[0]["payload"] == {
        "kind": "theory",
        "keys": ["theory"],
        "message_id": turn["id"],
        "session_id": document["session_id"],
    }


def test_a_document_needs_a_trusted_directory_and_tells_when_its_turn_is_cancelled(
    client: TestClient, repo: Repo
) -> None:
    untrusted = create_project(client, root_path=str(repo.root))
    project = trusted_project(client, repo.root)
    base = f"/v1/projects/{project['id']}"

    refused = client.post(f"/v1/projects/{untrusted['id']}/theory:generate")
    document = client.post(f"{base}/theory:generate").json()
    client.post(f"/v1/messages/{document['pending_message_id']}:cancel", json={"reason": "typo"})
    after = client.get(f"{base}/theory").json()["document"]
    retried = client.post(f"{base}/theory:generate")

    assert refused.status_code == 409 and error_of(refused)["code"] == "EXECUTION_NOT_TRUSTED"
    assert (after["status"], after["pending_message_id"]) == ("failed", None)
    assert after["status_reason"] == "the agent's turn ended cancelled: typo"
    assert retried.status_code == 202  # nothing is pending any more
    finished = [
        e for e in events(client, project["id"]) if e["type"] == "DOCUMENT_GENERATION_FINISHED"
    ]
    assert finished[0]["payload"]["failed"] == {"theory": "the agent's turn ended cancelled: typo"}
    assert finished[0]["severity"] == "error"


def test_the_files_of_the_project_are_listed_with_what_is_known_of_them(
    client: TestClient, repo: Repo
) -> None:
    repo.write("results/u_final.csv", "x,u\n0,1\n")
    repo.write("docs/grid.png", "not really a png")
    repo.write("ignored/cache.bin", "x")
    project = trusted_project(client, repo.root)

    listing = client.get(f"/v1/projects/{project['id']}/files").json()

    by_path = {entry["path"]: entry for entry in listing["files"]}
    assert sorted(by_path) == [".gitignore", "docs/grid.png", SOLVER, "results/u_final.csv"]
    assert listing["root"] == str(repo.root)
    assert by_path[SOLVER]["category"] == "code"
    assert by_path["results/u_final.csv"]["category"] == "data"  # read or written: not known yet
    assert by_path["docs/grid.png"]["category"] == "image"
    assert by_path["docs/grid.png"]["viewable_image"] is True
    assert by_path["results/u_final.csv"]["size_bytes"] == 8
    assert by_path[SOLVER]["sha"] == repo.git("rev-parse", f"HEAD:{SOLVER}")
    assert all(entry["description"] is None for entry in listing["files"])
    assert listing["counts"] == {
        "total": 4,
        "described": 0,
        "stale": 0,
        "generating": 0,
        "failed": 0,
        "undescribed": 4,
    }
    assert listing["truncated"] is False


def test_descriptions_are_asked_a_few_files_per_turn(client: TestClient, repo: Repo) -> None:
    for index in range(5):
        repo.write(f"src/m{index}.py", f"x = {index}\n")
    project = trusted_project(client, repo.root)
    client.app.state.settings.agent_files_per_turn = 3  # type: ignore[attr-defined]
    base = f"/v1/projects/{project['id']}"

    asked = client.post(f"{base}/files:describe", json={"scope": "undescribed"})
    answer = asked.json()
    listing = client.get(f"{base}/files").json()
    again = client.post(f"{base}/files:describe", json={"paths": ["src/m0.py", "src/m1.py"]})
    sessions = client.get(f"{base}/agent-sessions", params={"task": "file_description"}).json()
    prompts = [str(messages_of(client, s["id"])[0]["markdown"]) for s in sessions["sessions"]]

    assert asked.status_code == 202
    assert (answer["queued"], answer["turns"], answer["skipped"], answer["left"]) == (7, 3, 0, 0)
    assert listing["counts"]["generating"] == 7 and listing["counts"]["undescribed"] == 0
    state = next(e for e in listing["files"] if e["path"] == "src/m0.py")["description"]
    assert (state["status"], state["pending"], state["stale"]) == ("generating", True, False)
    # Files that are being described are not asked for twice.
    assert again.json() == {"queued": 0, "turns": 0, "skipped": 2, "left": 0, "message_ids": []}
    assert len(prompts) == 3
    # In the order of their paths, three at a time.
    assert sorted(p.split("Files to describe:\n")[1] for p in prompts) == [
        f"- .gitignore\n- {SOLVER}\n- src/m0.py\n",
        "- src/m1.py\n- src/m2.py\n- src/m3.py\n",
        "- src/m4.py\n",
    ]
    assert {s["permission_mode"] for s in sessions["sessions"]} == {"read_only"}


def test_only_files_of_the_project_can_be_described_or_shown(
    client: TestClient, repo: Repo
) -> None:
    repo.write("docs/grid.png", "PNGDATA")
    project = trusted_project(client, repo.root)
    base = f"/v1/projects/{project['id']}"

    unknown = client.post(f"{base}/files:describe", json={"paths": ["nope.py", SOLVER]})
    both = client.post(f"{base}/files:describe", json={"paths": [SOLVER], "scope": "all"})
    shown = client.get(f"{base}/files/content", params={"path": "docs/grid.png"})
    outside = client.get(f"{base}/files/content", params={"path": "../../etc/hosts"})
    folder = client.get(f"{base}/files/content", params={"path": "docs"})
    undescribed = client.get(f"{base}/files/description", params={"path": SOLVER})

    assert unknown.status_code == 422
    assert error_of(unknown)["details"]["errors"][0]["path"] == "nope.py"
    assert both.status_code == 422
    assert shown.status_code == 200 and shown.content == b"PNGDATA"
    assert shown.headers["content-type"] == "image/png"
    assert shown.headers["x-content-type-options"] == "nosniff"
    assert outside.status_code == 404 and error_of(outside)["details"]["resource"] == "file"
    assert folder.status_code == 404
    assert undescribed.status_code == 404


def test_the_pipeline_is_asked_in_a_session_of_its_own_task(client: TestClient, repo: Repo) -> None:
    untrusted = create_project(client, root_path=str(repo.root))
    project = trusted_project(client, repo.root, research_question="Is the scheme stable?")
    base = f"/v1/projects/{project['id']}"

    nothing = client.get(f"{base}/pipeline").json()
    refused = client.post(f"/v1/projects/{untrusted['id']}/pipeline:generate")
    asked = client.post(f"{base}/pipeline:generate", json={"instructions": "In italiano."})
    document = asked.json()
    again = client.post(f"{base}/pipeline:generate")
    every = client.get(f"{base}/agent-sessions", params={"task": "pipeline"}).json()["sessions"]
    prompt, turn = messages_of(client, document["session_id"])
    slot = client.get(f"{base}/pipeline").json()["document"]

    assert nothing == {"document": None}
    assert refused.status_code == 409 and error_of(refused)["code"] == "EXECUTION_NOT_TRUSTED"
    assert asked.status_code == 202
    assert (document["kind"], document["key"], document["status"]) == (
        "pipeline",
        "pipeline",
        "generating",
    )
    # Nothing is drawn before the agent answered.
    assert (document["version"], document["markdown"], document["pipeline"]) == (0, "", None)
    assert again.status_code == 409 and error_of(again)["code"] == "GENERATION_PENDING"
    assert [(s["task"], s["permission_mode"], s["title"]) for s in every] == [
        ("pipeline", "read_only", f"Pipeline of {project['name']}")
    ]
    assert str(prompt["markdown"]).startswith("[NumericOS task: pipeline]")
    assert "Research question: Is the scheme stable?" in str(prompt["markdown"])
    assert str(prompt["markdown"]).rstrip().endswith("In italiano.")
    assert slot["pending_message_id"] == turn["id"] and turn["status"] == "queued"
    queued = [e for e in events(client, project["id"]) if e["type"] == "DOCUMENT_GENERATION_QUEUED"]
    assert (queued[0]["payload"]["kind"], queued[0]["payload"]["keys"]) == (
        "pipeline",
        ["pipeline"],
    )


def test_a_plan_is_asked_with_the_board_as_it_is(client: TestClient, repo: Repo) -> None:
    project = trusted_project(client, repo.root)
    card = add_card(client, project["id"], "Port the solver", status="active")
    base = f"/v1/projects/{project['id']}"

    asked = client.post(f"{base}/plan:generate", json={"instructions": "Focus on stability."})
    document = asked.json()
    prompt, turn = messages_of(client, document["session_id"])
    slot = client.get(f"{base}/plan").json()["document"]

    assert asked.status_code == 202
    assert (document["kind"], document["status"]) == ("plan", "generating")
    assert f"- [{card['id']}] (task, active) Port the solver\n" in str(prompt["markdown"])
    assert str(prompt["markdown"]).rstrip().endswith("Focus on stability.")
    assert turn["status"] == "queued"
    assert slot["pending_message_id"] == turn["id"]
    assert card["origin"] == "user"
