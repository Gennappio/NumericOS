"""Execution trust, the code a run records, the exported record and reruns."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from fastapi.testclient import TestClient

from tests import factories
from tests.api.helpers import Json, create_project, error_of, events, trusted_project
from tests.gitrepo import SOLVER, Repo

SOLVER_PATH = "examples/heat2d-python/heat2d.py"


def trust(client: TestClient, project: Json, **body: Any) -> Any:
    payload = {"version": project["version"], "root_path": project["root_path"], **body}
    return client.post(f"/v1/projects/{project['id']}:trust-execution", json=payload)


def experiment_of(client: TestClient, project_id: str, **protocol: Any) -> Json:
    response = client.post(
        f"/v1/projects/{project_id}/experiments",
        json={"name": "Stability against dt", "protocol": factories.protocol(**protocol)},
    )
    assert response.status_code == 201, response.text
    body: Json = response.json()
    return body


def submit(client: TestClient, experiment_id: str, **body: Any) -> Any:
    return client.post(
        f"/v1/experiments/{experiment_id}/runs", json={"parameters": {"dt": 0.01}, **body}
    )


# --------------------------------------------------------------------------- trust


def test_trust_is_given_explicitly_to_one_directory(client: TestClient, repo: Repo) -> None:
    project = create_project(client, root_path=str(repo.root))
    assert project["execution_trusted_at"] is None

    response = trust(client, project)

    assert response.status_code == 200
    trusted = response.json()
    assert trusted["execution_trusted_at"] is not None
    assert trusted["version"] == 2
    recorded = events(client, project["id"])[-1]
    assert recorded["type"] == "PROJECT_EXECUTION_TRUSTED"
    assert recorded["payload"]["project"] == trusted
    # Asking again changes nothing.
    again = trust(client, trusted)
    assert again.json() == trusted
    assert len(events(client, project["id"])) == 2


def test_trust_needs_the_exact_path_of_a_git_work_tree(
    client: TestClient, repo: Repo, tmp_path: Path
) -> None:
    without_path = create_project(client, name="no path")
    plain = tmp_path / "plain"
    plain.mkdir()
    not_a_repo = create_project(client, name="plain", root_path=str(plain))
    project = create_project(client, name="repo", root_path=str(repo.root))

    no_path = client.post(
        f"/v1/projects/{without_path['id']}:trust-execution",
        json={"version": 1, "root_path": "/somewhere"},
    )
    other_path = trust(client, project, root_path=str(tmp_path))
    plain_directory = trust(client, not_a_repo)
    stale = trust(client, project, version=9)

    assert no_path.status_code == 422
    assert other_path.status_code == 422
    assert error_of(other_path)["details"]["errors"][0]["loc"] == ["body", "root_path"]
    assert plain_directory.status_code == 409
    assert error_of(plain_directory)["code"] == "NOT_A_GIT_REPOSITORY"
    assert stale.status_code == 409
    assert error_of(stale)["code"] == "STALE_REVISION"
    assert client.get(f"/v1/projects/{project['id']}").json()["execution_trusted_at"] is None


def test_trust_can_be_revoked_and_does_not_follow_a_changed_path(
    client: TestClient, repo: Repo, tmp_path: Path
) -> None:
    project = trusted_project(client, repo.root)
    url = f"/v1/projects/{project['id']}"

    revoked = client.post(f"{url}:revoke-execution-trust", json={"version": project["version"]})
    assert revoked.status_code == 200
    assert revoked.json()["execution_trusted_at"] is None
    assert events(client, project["id"])[-1]["type"] == "PROJECT_EXECUTION_TRUST_REVOKED"

    trusted_again = trust(client, revoked.json()).json()
    moved = client.patch(
        url, json={"version": trusted_again["version"], "root_path": str(tmp_path / "elsewhere")}
    )
    assert moved.status_code == 200
    assert moved.json()["execution_trusted_at"] is None  # trust was for the other directory
    assert events(client, project["id"])[-1]["payload"]["changed_fields"] == [
        "root_path",
        "execution_trusted_at",
    ]


def test_no_run_is_queued_for_a_project_that_is_not_trusted(client: TestClient, repo: Repo) -> None:
    project = create_project(client, root_path=str(repo.root))
    experiment = experiment_of(client, project["id"])

    response = submit(client, experiment["id"])

    assert response.status_code == 409
    error = error_of(response)
    assert error["code"] == "EXECUTION_NOT_TRUSTED"
    assert error["details"] == {"project_id": project["id"], "root_path": str(repo.root)}
    assert client.get(f"/v1/experiments/{experiment['id']}/runs").json() == {"runs": []}


# --------------------------------------------------------------------------- code provenance


def test_a_run_records_the_commit_it_will_execute(client: TestClient, repo: Repo) -> None:
    project = trusted_project(client, repo.root)
    experiment = experiment_of(client, project["id"])
    baseline = repo.head

    run = submit(client, experiment["id"]).json()
    repo.write(SOLVER_PATH, SOLVER + "# later\n")
    repo.commit("the branch moves on")

    code = run["code"]
    assert code["mode"] == "ref"
    assert code["sha"] == baseline
    assert code["requested_ref"] == "HEAD"
    assert code["commit"]["subject"] == "baseline solver"
    assert code["dirty"] is False
    assert code["submitted_with_dirty_working_tree"] is False
    assert code["repository_root"] == str(repo.root)
    # The queued run keeps the commit it was created with.
    assert client.get(f"/v1/runs/{run['id']}").json()["code"]["sha"] == baseline
    later = submit(client, experiment["id"]).json()
    assert later["code"]["sha"] == repo.head != baseline


def test_baseline_and_candidate_differ_by_commit_under_one_protocol(
    client: TestClient, repo: Repo
) -> None:
    project = trusted_project(client, repo.root)
    experiment = experiment_of(client, project["id"])
    baseline = repo.head
    repo.write(SOLVER_PATH, SOLVER + "# candidate\n")
    candidate = repo.commit("candidate")
    repo.write(SOLVER_PATH, SOLVER + "# still editing\n")  # uncommitted: reported, not executed

    on_baseline = submit(client, experiment["id"], code_ref=baseline, label="baseline").json()
    on_candidate = submit(client, experiment["id"], code_ref="main", label="candidate").json()
    unknown = submit(client, experiment["id"], code_ref="no-such-branch")

    assert (on_baseline["code"]["sha"], on_candidate["code"]["sha"]) == (baseline, candidate)
    assert on_baseline["protocol_digest"] == on_candidate["protocol_digest"]
    assert on_baseline["argv"] == on_candidate["argv"]
    assert on_candidate["code"]["submitted_with_dirty_working_tree"] is True
    assert on_candidate["code"]["dirty"] is False
    assert unknown.status_code == 422
    assert error_of(unknown)["details"]["errors"][0]["loc"] == ["body", "code_ref"]


def test_a_working_tree_experiment_fixes_its_code_only_when_the_run_starts(
    client: TestClient, repo: Repo
) -> None:
    project = trusted_project(client, repo.root)
    in_place = factories.protocol()
    in_place["execution"]["code"] = {"mode": "working_tree"}
    experiment = experiment_of(client, project["id"], execution=in_place["execution"])

    run = submit(client, experiment["id"]).json()
    with_ref = submit(client, experiment["id"], code_ref="main")

    assert run["code"]["mode"] == "working_tree"
    assert (run["code"]["sha"], run["code"]["dirty"], run["code"]["captured_at"]) == (
        None,
        None,
        None,
    )
    assert with_ref.status_code == 422


def test_a_project_that_stopped_being_a_repository_queues_nothing(
    client: TestClient, repo: Repo
) -> None:
    project = trusted_project(client, repo.root)
    experiment = experiment_of(client, project["id"])
    (repo.root / ".git").rename(repo.root / ".git-moved-away")

    response = submit(client, experiment["id"])

    assert response.status_code == 409
    assert error_of(response)["code"] == "NOT_A_GIT_REPOSITORY"
    assert client.get(f"/v1/experiments/{experiment['id']}/runs").json() == {"runs": []}


# --------------------------------------------------------------------------- record and rerun


def test_the_run_record_bundles_the_run_with_its_protocol(client: TestClient, repo: Repo) -> None:
    project = trusted_project(client, repo.root)
    experiment = experiment_of(client, project["id"])
    run = submit(client, experiment["id"], seed=None, label="baseline").json()

    record = client.get(f"/v1/runs/{run['id']}/record").json()

    assert record["schema"] == "numericos.run-record.v1"
    assert record["exported_at"].endswith("Z")
    assert record["run"] == run
    assert record["experiment"]["protocol"] == experiment["protocol"]
    assert record["experiment"]["protocol_digest"] == run["protocol_digest"]
    assert record["run"]["code"]["sha"] == repo.head


def test_a_rerun_uses_the_same_commit_parameters_and_seed(client: TestClient, repo: Repo) -> None:
    project = trusted_project(client, repo.root)
    seeded = factories.protocol()
    seeded["execution"]["command"] += ["--seed", "{seed}"]
    experiment = experiment_of(client, project["id"], execution=seeded["execution"])
    original = submit(client, experiment["id"], parameters={"dt": 0.005}, seed=11).json()
    repo.write(SOLVER_PATH, SOLVER + "# the branch moves on\n")
    repo.commit("later work")

    response = client.post(
        f"/v1/runs/{original['id']}:rerun", headers={"Idempotency-Key": "repro-1"}
    )
    replay = client.post(f"/v1/runs/{original['id']}:rerun", headers={"Idempotency-Key": "repro-1"})

    assert response.status_code == 201
    repeated = response.json()
    assert repeated["id"] != original["id"]
    assert repeated["reproduces_run_id"] == original["id"]
    assert repeated["status"] == "queued"
    for same in ("parameters", "seed", "argv", "protocol_digest"):
        assert repeated[same] == original[same]
    assert repeated["code"]["sha"] == original["code"]["sha"] != repo.head
    assert replay.status_code == 200
    assert replay.json()["id"] == repeated["id"]


def test_a_working_tree_run_cannot_be_rerun_automatically(client: TestClient, repo: Repo) -> None:
    project = trusted_project(client, repo.root)
    in_place = factories.protocol()
    in_place["execution"]["code"] = {"mode": "working_tree"}
    experiment = experiment_of(client, project["id"], execution=in_place["execution"])
    run = submit(client, experiment["id"]).json()

    response = client.post(f"/v1/runs/{run['id']}:rerun")

    assert response.status_code == 409
    assert error_of(response)["code"] == "NOT_REPRODUCIBLE"
    assert len(client.get(f"/v1/experiments/{experiment['id']}/runs").json()["runs"]) == 1
