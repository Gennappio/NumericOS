"""Hypotheses, experiments and runs over the API."""

from __future__ import annotations

from typing import Any

import pytest
from fastapi.testclient import TestClient

from tests import factories
from tests.api.helpers import Json, create_project, error_of, events, trusted_project
from tests.gitrepo import Repo

UNKNOWN = "01J9W2Z4K7QX8YB3N5M6T0R1S2"
HYPOTHESIS = {
    "title": "H01: the blow-up comes from the stability limit",
    "claim": "For dt above the limit of this scheme the residual grows without bound.",
    "prediction": "Residual growth disappears for dt below the limit.",
    "falsification": ["Divergence persists for every smaller dt."],
}


@pytest.fixture
def project(client: TestClient, repo: Repo) -> Json:
    return trusted_project(client, repo.root)


def new_hypothesis(client: TestClient, project_id: str, **fields: Any) -> Json:
    response = client.post(f"/v1/projects/{project_id}/hypotheses", json={**HYPOTHESIS, **fields})
    assert response.status_code == 201, response.text
    body: Json = response.json()
    return body


def new_experiment(client: TestClient, project_id: str, **fields: Any) -> Json:
    body = {"name": "Stability against dt", "protocol": factories.protocol(), **fields}
    response = client.post(f"/v1/projects/{project_id}/experiments", json=body)
    assert response.status_code == 201, response.text
    created: Json = response.json()
    return created


def submit(client: TestClient, experiment_id: str, **body: Any) -> Any:
    headers = body.pop("headers", None)
    return client.post(f"/v1/experiments/{experiment_id}/runs", json=body, headers=headers)


# --------------------------------------------------------------------------- hypotheses


def test_a_hypothesis_starts_proposed_and_records_one_event(
    client: TestClient, project: Json
) -> None:
    hypothesis = new_hypothesis(client, project["id"])

    assert hypothesis["id"].startswith("hyp_")
    assert hypothesis["project_id"] == project["id"]
    assert hypothesis["epistemic_status"] == "proposed"
    assert hypothesis["falsification"] == HYPOTHESIS["falsification"]
    assert hypothesis["assumptions"] == []
    assert hypothesis["version"] == 1
    assert client.get(f"/v1/hypotheses/{hypothesis['id']}").json() == hypothesis
    assert client.get(f"/v1/projects/{project['id']}/hypotheses").json() == {
        "hypotheses": [hypothesis]
    }
    recorded = events(client, project["id"])[-1]
    assert recorded["type"] == "HYPOTHESIS_CREATED"
    assert recorded["subject_id"] == hypothesis["id"]
    assert recorded["payload"] == {"hypothesis": hypothesis}


def test_epistemic_status_cannot_be_set_by_hand(client: TestClient, project: Json) -> None:
    hypothesis = new_hypothesis(client, project["id"])

    created = client.post(
        f"/v1/projects/{project['id']}/hypotheses",
        json={**HYPOTHESIS, "epistemic_status": "supported"},
    )
    patched = client.patch(
        f"/v1/hypotheses/{hypothesis['id']}", json={"version": 1, "epistemic_status": "supported"}
    )

    assert created.status_code == 422
    assert patched.status_code == 422
    assert client.get(f"/v1/hypotheses/{hypothesis['id']}").json()["epistemic_status"] == "proposed"


def test_rewording_a_hypothesis_is_versioned(client: TestClient, project: Json) -> None:
    hypothesis = new_hypothesis(client, project["id"])
    url = f"/v1/hypotheses/{hypothesis['id']}"

    updated = client.patch(url, json={"version": 1, "prediction": "Sharper prediction."})
    stale = client.patch(url, json={"version": 1, "title": "lost update"})
    unchanged = client.patch(url, json={"version": 2, "prediction": "Sharper prediction."})

    assert updated.status_code == 200
    assert (updated.json()["prediction"], updated.json()["version"]) == ("Sharper prediction.", 2)
    assert stale.status_code == 409
    assert error_of(stale)["code"] == "STALE_REVISION"
    assert unchanged.json() == updated.json()
    recorded = [event["type"] for event in events(client, project["id"])]
    assert recorded.count("HYPOTHESIS_UPDATED") == 1


def test_unknown_hypothesis_and_project_are_404(client: TestClient) -> None:
    assert client.get(f"/v1/hypotheses/hyp_{UNKNOWN}").status_code == 404
    assert client.get(f"/v1/projects/prj_{UNKNOWN}/hypotheses").status_code == 404
    response = client.post(f"/v1/projects/prj_{UNKNOWN}/hypotheses", json=HYPOTHESIS)
    assert error_of(response)["details"] == {"resource": "project", "id": f"prj_{UNKNOWN}"}


# --------------------------------------------------------------------------- experiments


def test_an_experiment_stores_its_protocol_and_digest(client: TestClient, project: Json) -> None:
    hypothesis = new_hypothesis(client, project["id"])

    experiment = new_experiment(client, project["id"], hypothesis_id=hypothesis["id"])

    assert experiment["id"].startswith("exp_")
    assert experiment["hypothesis_id"] == hypothesis["id"]
    assert experiment["run_count"] == 0
    assert len(experiment["protocol_digest"]) == 64
    protocol = experiment["protocol"]
    assert protocol["schema"] == "numericos.experiment.v1"
    assert protocol["independent_variables"] == {"dt": [0.02, 0.01, 0.005]}
    assert protocol["execution"]["code"] == {"mode": "ref", "ref": "HEAD"}  # defaults are explicit
    assert client.get(f"/v1/experiments/{experiment['id']}").json() == experiment
    assert client.get(f"/v1/projects/{project['id']}/experiments").json() == {
        "experiments": [experiment]
    }
    recorded = events(client, project["id"])[-1]
    assert recorded["type"] == "EXPERIMENT_CREATED"
    assert recorded["payload"] == {"experiment": experiment}


def test_an_invalid_protocol_is_rejected_with_the_reason(client: TestClient, project: Json) -> None:
    broken = factories.protocol(controls={"grid": 32})  # the command also needs {steps}

    response = client.post(
        f"/v1/projects/{project['id']}/experiments", json={"name": "broken", "protocol": broken}
    )

    assert response.status_code == 422
    assert "steps" in error_of(response)["details"]["errors"][0]["msg"]
    assert client.get(f"/v1/projects/{project['id']}/experiments").json() == {"experiments": []}


def test_an_experiment_can_only_test_a_hypothesis_of_its_project(
    client: TestClient, project: Json
) -> None:
    other = create_project(client, name="other")
    foreign = new_hypothesis(client, other["id"])
    url = f"/v1/projects/{project['id']}/experiments"
    body = {"name": "x", "protocol": factories.protocol()}

    mismatch = client.post(url, json={**body, "hypothesis_id": foreign["id"]})
    missing = client.post(url, json={**body, "hypothesis_id": f"hyp_{UNKNOWN}"})

    assert mismatch.status_code == 409
    assert error_of(mismatch)["code"] == "PROJECT_MISMATCH"
    assert missing.status_code == 404


def test_the_protocol_is_replaceable_until_the_first_run_then_frozen(
    client: TestClient, project: Json
) -> None:
    experiment = new_experiment(client, project["id"])
    url = f"/v1/experiments/{experiment['id']}"
    stricter = factories.protocol(limits={"wall_seconds": 30})

    replaced = client.patch(url, json={"version": 1, "protocol": stricter})
    assert replaced.status_code == 200
    assert replaced.json()["protocol_digest"] != experiment["protocol_digest"]
    assert replaced.json()["protocol"]["limits"]["wall_seconds"] == 30

    assert submit(client, experiment["id"], parameters={"dt": 0.01}).status_code == 201
    frozen = client.patch(url, json={"version": 2, "protocol": factories.protocol()})
    same = client.patch(url, json={"version": 2, "protocol": stricter})
    renamed = client.patch(url, json={"version": 2, "name": "Renamed", "hypothesis_id": None})

    assert frozen.status_code == 409
    assert error_of(frozen)["code"] == "PROTOCOL_FROZEN"
    assert error_of(frozen)["details"]["run_count"] == 1
    assert same.status_code == 200  # the same contract is not a change
    assert same.json()["version"] == 2
    assert renamed.status_code == 200
    assert (renamed.json()["name"], renamed.json()["run_count"]) == ("Renamed", 1)
    assert events(client, project["id"])[-1]["payload"]["changed_fields"] == ["name"]


# --------------------------------------------------------------------------- runs


def test_a_run_is_queued_with_its_exact_argument_vector(client: TestClient, project: Json) -> None:
    experiment = new_experiment(client, project["id"])

    response = submit(client, experiment["id"], parameters={"dt": 0.01}, label="baseline")

    assert response.status_code == 201
    run = response.json()
    assert run["id"].startswith("run_")
    assert run["status"] == "queued"
    assert (run["status_reason"], run["failure_class"]) == (None, None)
    assert run["label"] == "baseline"
    assert run["parameters"] == {"grid": 32, "steps": 100, "dt": 0.01}
    assert run["argv"] == [
        "python3",
        "heat2d.py",
        "--dt",
        "0.01",
        "--grid",
        "32",
        "--steps",
        "100",
    ]
    assert run["protocol_digest"] == experiment["protocol_digest"]
    assert (run["inputs"], run["environment"], run["reproduces_run_id"]) == (None, None, None)
    assert client.get(f"/v1/runs/{run['id']}").json() == run
    assert client.get(f"/v1/experiments/{experiment['id']}/runs").json() == {"runs": [run]}
    assert client.get(f"/v1/experiments/{experiment['id']}").json()["run_count"] == 1


def test_run_events_are_correlated_with_the_run(client: TestClient, project: Json) -> None:
    experiment = new_experiment(client, project["id"])
    first = submit(client, experiment["id"], parameters={"dt": 0.02}).json()
    second = submit(client, experiment["id"], parameters={"dt": 0.01}).json()

    of_first = events(client, project["id"], run_id=first["id"])
    everything = events(client, project["id"])

    assert [(event["type"], event["run_id"]) for event in of_first] == [("RUN_QUEUED", first["id"])]
    assert of_first[0]["payload"] == {"run": first}
    assert [event["run_id"] for event in everything][-2:] == [first["id"], second["id"]]
    assert {event["run_id"] for event in everything[:3]} == {None}  # project events have no run


@pytest.mark.parametrize(
    ("parameters", "field"),
    [
        ({}, "dt"),
        ({"dt": 0.5}, "dt"),
        ({"dt": 0.01, "grid": 64}, "grid"),
        ({"dt": 0.01, "tol": 1e-6}, "tol"),
    ],
)
def test_parameters_outside_the_protocol_queue_nothing(
    client: TestClient, project: Json, parameters: dict[str, Any], field: str
) -> None:
    experiment = new_experiment(client, project["id"])

    response = submit(client, experiment["id"], parameters=parameters)

    assert response.status_code == 422
    assert error_of(response)["code"] == "VALIDATION_ERROR"
    assert error_of(response)["details"]["errors"][0]["loc"] == ["body", "parameters", field]
    assert client.get(f"/v1/experiments/{experiment['id']}/runs").json() == {"runs": []}


def test_a_command_that_uses_the_seed_requires_one(client: TestClient, project: Json) -> None:
    seeded = factories.protocol()
    seeded["execution"]["command"] += ["--seed", "{seed}"]
    experiment = new_experiment(client, project["id"], protocol=seeded)

    missing = submit(client, experiment["id"], parameters={"dt": 0.01})
    given = submit(client, experiment["id"], parameters={"dt": 0.01}, seed=7)

    assert missing.status_code == 422
    assert error_of(missing)["details"]["errors"][0]["loc"] == ["body", "seed"]
    assert given.status_code == 201
    assert given.json()["argv"][-2:] == ["--seed", "7"]
    assert given.json()["seed"] == 7


def test_an_idempotency_key_makes_a_submission_repeatable(
    client: TestClient, project: Json
) -> None:
    experiment = new_experiment(client, project["id"])
    key = {"Idempotency-Key": "lab-quest-012:dt-0.01"}
    before = len(events(client, project["id"]))

    first = submit(client, experiment["id"], parameters={"dt": 0.01}, headers=key)
    replay = submit(client, experiment["id"], parameters={"dt": 0.01}, headers=key)
    conflict = submit(client, experiment["id"], parameters={"dt": 0.02}, headers=key)
    without_key = submit(client, experiment["id"], parameters={"dt": 0.01})

    assert first.status_code == 201
    assert replay.status_code == 200
    assert replay.headers["idempotency-replayed"] == "true"
    assert replay.json() == first.json()
    assert conflict.status_code == 409
    assert error_of(conflict)["code"] == "IDEMPOTENCY_CONFLICT"
    assert error_of(conflict)["details"]["run_id"] == first.json()["id"]
    assert without_key.status_code == 201
    assert without_key.json()["id"] != first.json()["id"]
    assert len(events(client, project["id"])) == before + 2  # two runs, not four


def test_a_malformed_idempotency_key_is_rejected(client: TestClient, project: Json) -> None:
    experiment = new_experiment(client, project["id"])

    response = submit(
        client, experiment["id"], parameters={"dt": 0.01}, headers={"Idempotency-Key": "a b"}
    )

    assert response.status_code == 422
    assert error_of(response)["details"]["errors"][0]["loc"] == ["header", "idempotency-key"]


def test_unknown_experiment_and_run_are_404(client: TestClient) -> None:
    assert client.get(f"/v1/experiments/exp_{UNKNOWN}").status_code == 404
    assert client.get(f"/v1/experiments/exp_{UNKNOWN}/runs").status_code == 404
    assert submit(client, f"exp_{UNKNOWN}", parameters={}).status_code == 404
    response = client.get(f"/v1/runs/run_{UNKNOWN}")
    assert error_of(response)["details"] == {"resource": "run", "id": f"run_{UNKNOWN}"}
