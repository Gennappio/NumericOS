"""Experiment contracts as files of the project: found, registered, and looked at together."""

from __future__ import annotations

from typing import Any

import yaml

from numericos.executor.worker import Worker
from tests import factories
from tests.api.helpers import create_project, error_of
from tests.lab import Lab

Json = dict[str, Any]
UNKNOWN_EXPERIMENT = "exp_01J9W2Z4K7QX8YB3N5M6T0R1S2"


def by_path(listing: Json) -> dict[str, Json]:
    return {item["path"]: item for item in listing["files"]}


def test_contract_files_of_the_repository_are_found_and_told_apart(lab: Lab) -> None:
    lab.install_example("heat2d-python")
    lab.repo.write("config/solver.yaml", "tolerance: 1.0e-9\n")  # YAML, but not a contract
    lab.repo.write(
        "experiments/broken.yaml",
        yaml.safe_dump({**factories.protocol(), "limits": {}}),  # no wall-clock limit
    )
    lab.repo.write("ignored/local.yaml", yaml.safe_dump(factories.protocol()))  # git-ignored
    path = f"/v1/projects/{lab.project['id']}/contract-files"

    listing = lab.get(path)

    found = by_path(listing)
    assert sorted(found) == [
        "examples/heat2d-python/experiment-fine.yaml",
        "examples/heat2d-python/experiment.yaml",
        "experiments/broken.yaml",  # new and not committed yet: found all the same
    ]
    heat = found["examples/heat2d-python/experiment.yaml"]
    assert (heat["name"], heat["valid"], heat["experiment_id"]) == ("heat2d-stability", True, None)
    assert heat["question"].startswith("On a 32 x 32 grid")
    broken = found["experiments/broken.yaml"]
    assert (broken["valid"], broken["name"]) == (False, "broken")
    assert any("wall_seconds" in problem for problem in broken["problems"])
    assert listing["truncated"] is False


def test_a_contract_file_is_registered_once_and_then_recognised(lab: Lab) -> None:
    lab.install_example("heat2d-python")
    project = lab.project["id"]
    request = {"path": "examples/heat2d-python/experiment.yaml"}

    first = lab.http.post(f"/v1/projects/{project}/experiments:import", json=request)
    again = lab.http.post(f"/v1/projects/{project}/experiments:import", json=request)
    listing = by_path(lab.get(f"/v1/projects/{project}/contract-files"))

    assert (first.status_code, again.status_code) == (201, 200)
    assert again.json()["id"] == first.json()["id"]
    assert first.json()["name"] == "heat2d-stability"
    assert first.json()["protocol"]["controls"]["grid"] == 32
    assert listing["examples/heat2d-python/experiment.yaml"]["experiment_id"] == first.json()["id"]
    assert listing["examples/heat2d-python/experiment-fine.yaml"]["experiment_id"] is None


def test_a_contract_can_be_registered_from_its_text(lab: Lab) -> None:
    path = f"/v1/projects/{lab.project['id']}/experiments:import"
    text = yaml.safe_dump({"name": "From text", **factories.protocol()})

    created = lab.http.post(path, json={"text": text})
    unnamed = lab.http.post(path, json={"text": yaml.safe_dump(factories.protocol())})

    assert created.status_code == 201
    assert created.json()["name"] == "From text"
    assert unnamed.json()["name"] == "experiment"


def test_what_cannot_be_registered_is_refused_with_its_reason(lab: Lab) -> None:
    lab.repo.write("big.yaml", "x: 1\n" + "# padding\n" * 40000)
    path = f"/v1/projects/{lab.project['id']}/experiments:import"

    def refusal(body: Json) -> Json:
        response = lab.http.post(path, json=body)
        assert response.status_code == 422, response.text
        return error_of(response)

    not_yaml = refusal({"text": "question: [unclosed"})
    not_a_mapping = refusal({"text": "- a\n- b\n"})
    incomplete = refusal({"text": "schema: numericos.experiment.v1\nquestion: Why?\n"})
    outside = refusal({"path": "../outside.yaml"})
    absent = refusal({"path": "experiments/nowhere.yaml"})
    too_big = refusal({"path": "big.yaml"})
    both = refusal({"path": "a.yaml", "text": "x: 1"})
    neither = refusal({})

    assert "not valid YAML" in not_yaml["message"]
    assert not_a_mapping["details"]["errors"][0]["type"] == "invalid_contract"
    missing = {tuple(issue["loc"]) for issue in incomplete["details"]["errors"]}
    assert ("body", "text", "protocol", "execution") in missing
    assert ("body", "text", "protocol", "limits") in missing
    assert outside["details"]["errors"][0]["type"] == "invalid_path"
    assert absent["details"]["errors"][0]["type"] == "unreadable"
    assert too_big["details"]["errors"][0]["type"] == "unreadable"
    assert "exactly one of 'path' and 'text'" in str(both["details"])
    assert "exactly one of 'path' and 'text'" in str(neither["details"])
    assert lab.get(f"/v1/projects/{lab.project['id']}/experiments")["experiments"] == []


def test_a_project_without_a_code_path_has_no_contract_files(lab: Lab) -> None:
    bare = create_project(lab.http, name="No code")  # type: ignore[arg-type]

    listing = lab.get(f"/v1/projects/{bare['id']}/contract-files")
    refused = lab.http.post(
        f"/v1/projects/{bare['id']}/experiments:import", json={"path": "experiment.yaml"}
    )

    assert listing == {"files": [], "scanned": 0, "truncated": False}
    assert refused.status_code == 422
    assert error_of(refused)["details"]["errors"][0]["type"] == "no_root"


def test_the_metrics_of_all_runs_of_an_experiment_are_read_in_one_request(
    lab: Lab, supervisor: Worker
) -> None:
    experiment = lab.register(lab.install_example("heat2d-python"))
    stable = lab.queue(experiment, parameters={"dt": 0.0002})
    unstable = lab.queue(experiment, parameters={"dt": 0.0003})
    supervisor.run_until_idle()

    series = lab.get(f"/v1/experiments/{experiment['id']}/series")["series"]
    unknown = lab.http.get(f"/v1/experiments/{UNKNOWN_EXPERIMENT}/series")

    final = {(item["run_id"], item["name"]): item["last_value"] for item in series}
    assert {item["run_id"] for item in series} == {stable["id"], unstable["id"]}
    assert len(series) == 12  # six metrics for each of the two runs
    assert final[(stable["id"], "max_abs_u")] < 0.1
    assert final[(unstable["id"], "max_abs_u")] > 1.0
    assert final[(stable["id"], "wall_time")] > 0
    assert unknown.status_code == 404


def test_a_browser_may_send_an_idempotency_key(lab: Lab) -> None:
    preflight = lab.http.options(
        "/v1/experiments/exp_x/runs",
        headers={
            "Origin": "http://localhost:5173",
            "Access-Control-Request-Method": "POST",
            "Access-Control-Request-Headers": "content-type,idempotency-key,x-actor",
        },
    )

    assert preflight.status_code == 200
    assert "idempotency-key" in preflight.headers["access-control-allow-headers"].lower()
