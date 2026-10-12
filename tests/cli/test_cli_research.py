"""Hypotheses, experiments and runs through the CLI, against a real API process."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import httpx
import yaml
from typer.testing import CliRunner, Result

from numericos.cli.main import EXIT_API_ERROR, app
from tests import factories
from tests.conftest import LiveServer
from tests.gitrepo import Repo

runner = CliRunner()


def run(server: LiveServer, *args: str) -> Result:
    return runner.invoke(app, [*args, "--api-url", server.base_url])


def run_json(server: LiveServer, *args: str) -> Any:
    result = run(server, *args, "--json")
    assert result.exit_code == 0, result.output
    assert result.stderr == ""
    return json.loads(result.stdout)


def trusted_project(server: LiveServer, repo: Repo) -> Any:
    project = run_json(server, "project", "add", "Heat 2D", "--root-path", str(repo.root))
    return run_json(server, "project", "trust", project["id"], "--yes")


def contract_file(tmp_path: Path, **extra: Any) -> Path:
    path = tmp_path / "stability.yaml"
    path.write_text(yaml.safe_dump({**factories.protocol(), **extra}, sort_keys=False))
    return path


def test_an_experiment_is_registered_from_a_contract_file_and_a_run_is_queued(
    live_server: LiveServer, tmp_path: Path, repo: Repo
) -> None:
    project = trusted_project(live_server, repo)
    hypothesis = run_json(
        live_server,
        "hypothesis",
        "add",
        "-p",
        project["id"],
        "--title",
        "H01",
        "--claim",
        "The blow-up comes from the stability limit.",
        "--falsification",
        "Divergence persists for every smaller dt.",
    )
    path = contract_file(tmp_path, name="Stability against dt", hypothesis_id=hypothesis["id"])

    experiment = run_json(live_server, "experiment", "add", str(path), "-p", project["id"])
    queued = run_json(
        live_server, "run", "submit", experiment["id"], "-P", "dt=0.01", "--label", "baseline"
    )

    assert experiment["name"] == "Stability against dt"
    assert experiment["hypothesis_id"] == hypothesis["id"]
    assert experiment["protocol"]["controls"] == {"grid": 32, "steps": 100}
    assert queued["status"] == "queued"
    assert queued["parameters"] == {"grid": 32, "steps": 100, "dt": 0.01}
    assert queued["argv"][:4] == ["python3", "heat2d.py", "--dt", "0.01"]
    # The API holds exactly what the CLI reported.
    via_api = httpx.get(f"{live_server.base_url}/v1/runs/{queued['id']}").json()
    assert via_api == queued
    assert run_json(live_server, "run", "show", queued["id"]) == queued
    assert run_json(live_server, "run", "list", "-e", experiment["id"]) == {"runs": [queued]}
    listed = run_json(live_server, "experiment", "list", "-p", project["id"])
    assert [(item["id"], item["run_count"]) for item in listed["experiments"]] == [
        (experiment["id"], 1)
    ]
    assert run_json(live_server, "hypothesis", "list", "-p", project["id"]) == {
        "hypotheses": [hypothesis]
    }


def test_the_file_name_names_an_experiment_that_has_no_name(
    live_server: LiveServer, tmp_path: Path, repo: Repo
) -> None:
    project = trusted_project(live_server, repo)

    experiment = run_json(
        live_server, "experiment", "add", str(contract_file(tmp_path)), "-p", project["id"]
    )

    assert experiment["name"] == "stability"
    assert experiment["hypothesis_id"] is None


def test_repeating_a_submission_with_a_key_returns_the_same_run(
    live_server: LiveServer, tmp_path: Path, repo: Repo
) -> None:
    project = trusted_project(live_server, repo)
    experiment = run_json(
        live_server, "experiment", "add", str(contract_file(tmp_path)), "-p", project["id"]
    )
    command = ("run", "submit", experiment["id"], "-P", "dt=0.02", "--idempotency-key", "k-1")

    first = run_json(live_server, *command)
    again = run_json(live_server, *command)

    assert again == first
    assert len(run_json(live_server, "run", "list", "-e", experiment["id"])["runs"]) == 1


def test_errors_keep_the_cli_contract(live_server: LiveServer, tmp_path: Path, repo: Repo) -> None:
    project = trusted_project(live_server, repo)
    experiment = run_json(
        live_server, "experiment", "add", str(contract_file(tmp_path)), "-p", project["id"]
    )
    broken = tmp_path / "broken.yaml"
    broken.write_text("- not\n- a mapping\n")

    undeclared = run(live_server, "run", "submit", experiment["id"], "-P", "dt=0.5", "--json")
    not_an_assignment = run(live_server, "run", "submit", experiment["id"], "-P", "dt")
    not_a_mapping = run(live_server, "experiment", "add", str(broken), "-p", project["id"])
    missing_file = run(
        live_server, "experiment", "add", str(tmp_path / "absent.yaml"), "-p", project["id"]
    )

    assert undeclared.exit_code == EXIT_API_ERROR
    assert undeclared.stdout == ""
    assert json.loads(undeclared.stderr)["error"]["code"] == "VALIDATION_ERROR"
    for usage_error in (not_an_assignment, not_a_mapping, missing_file):
        assert usage_error.exit_code == 2, usage_error.output
        assert usage_error.stdout == ""


def test_human_output_names_what_matters(
    live_server: LiveServer, tmp_path: Path, repo: Repo
) -> None:
    project = trusted_project(live_server, repo)
    experiment = run_json(
        live_server, "experiment", "add", str(contract_file(tmp_path)), "-p", project["id"]
    )

    shown = run(live_server, "experiment", "show", experiment["id"])
    submitted = run(live_server, "run", "submit", experiment["id"], "-P", "dt=0.005")

    assert "dt in [0.02, 0.01, 0.005]" in shown.stdout
    assert "python3 heat2d.py --dt {dt}" in shown.stdout
    assert "queued" in submitted.stdout
    assert "'dt': 0.005" in submitted.stdout


def test_trust_is_an_explicit_step_and_can_be_withdrawn(
    live_server: LiveServer, repo: Repo
) -> None:
    project = run_json(live_server, "project", "add", "Heat 2D", "--root-path", str(repo.root))
    assert project["execution_trusted_at"] is None

    declined = runner.invoke(
        app, ["project", "trust", project["id"], "--api-url", live_server.base_url], input="n\n"
    )
    trusted = run_json(live_server, "project", "trust", project["id"], "--yes")
    shown = run(live_server, "project", "show", project["id"])
    untrusted = run_json(live_server, "project", "untrust", project["id"])
    no_path = run_json(live_server, "project", "add", "No code")
    refused = run(live_server, "project", "trust", no_path["id"], "--yes")

    assert declined.exit_code == 1  # asked, answered no: nothing changes
    assert str(repo.root) in declined.stderr
    assert trusted["execution_trusted_at"] is not None
    assert "trusted since" in shown.stdout
    assert untrusted["execution_trusted_at"] is None
    assert refused.exit_code == 2


def test_runs_name_their_commit_and_can_be_exported_and_rerun(
    live_server: LiveServer, tmp_path: Path, repo: Repo
) -> None:
    project = trusted_project(live_server, repo)
    experiment = run_json(
        live_server, "experiment", "add", str(contract_file(tmp_path)), "-p", project["id"]
    )
    baseline = repo.head
    repo.write("examples/heat2d-python/heat2d.py", "print('candidate')\n")
    candidate = repo.commit("candidate")

    on_baseline = run_json(
        live_server, "run", "submit", experiment["id"], "-P", "dt=0.01", "--code-ref", baseline
    )
    on_candidate = run_json(live_server, "run", "submit", experiment["id"], "-P", "dt=0.01")
    record_file = tmp_path / "out" / "record.json"
    exported = run(live_server, "run", "export", on_baseline["id"], "-o", str(record_file))
    printed = run(live_server, "run", "export", on_baseline["id"])
    repeated = run_json(live_server, "run", "rerun", on_baseline["id"])
    shown = run(live_server, "run", "show", on_candidate["id"])

    assert (on_baseline["code"]["sha"], on_candidate["code"]["sha"]) == (baseline, candidate)
    assert exported.exit_code == 0
    assert exported.stdout == ""
    record = json.loads(record_file.read_text())
    on_stdout = json.loads(printed.stdout)
    assert {**record, "exported_at": None} == {**on_stdout, "exported_at": None}
    assert record["schema"] == "numericos.run-record.v1"
    assert record["run"]["code"]["sha"] == baseline
    assert repeated["reproduces_run_id"] == on_baseline["id"]
    assert repeated["code"]["sha"] == baseline
    assert f"commit {candidate} (HEAD) candidate" in shown.stdout
