"""Running and observing experiments from the command line, with real API and supervisor
processes: what a script or an external agent would do."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path
from typing import Any

import yaml
from typer.testing import CliRunner, Result

from numericos.cli.main import EXIT_STILL_RUNNING, RUN_EXIT_CODES, app
from tests.conftest import LiveServer, LiveWorker
from tests.lab import Lab

runner = CliRunner()

WAITING = """
    import time
    print("working", flush=True)
    time.sleep(60)
    """


def cli(server: LiveServer, *args: str) -> Result:
    return runner.invoke(app, [*args, "--api-url", server.base_url])


def cli_json(server: LiveServer, *args: str) -> Any:
    result = cli(server, *args, "--json")
    assert result.exit_code == 0, result.output
    return json.loads(result.stdout)


def test_submit_and_watch_ends_with_how_the_run_ended(
    live_server: LiveServer, live_worker: LiveWorker, live_lab: Lab
) -> None:
    converging = live_lab.experiment(live_lab.program('print("residual 1e-9")'))
    failing = live_lab.experiment(
        live_lab.program(
            """
            import sys
            print("residual nan", file=sys.stderr)
            sys.exit(4)
            """
        )
    )

    succeeded = cli(live_server, "run", "submit", converging["id"], "--watch", "--json")
    failed = cli(live_server, "run", "submit", failing["id"], "--watch")

    run = json.loads(succeeded.stdout)  # machine mode: stdout is exactly one document
    assert succeeded.exit_code == RUN_EXIT_CODES["succeeded"] == 0
    assert (run["status"], run["exit_code"]) == ("succeeded", 0)
    assert "out | residual 1e-9" in succeeded.stderr
    assert f"run {run['id']}: succeeded" in succeeded.stderr
    assert failed.exit_code == RUN_EXIT_CODES["failed"] == 10
    assert "err | residual nan" in failed.stdout  # for a person the output is the content
    assert "failure:    code_error" in failed.stdout
    assert "the program exited with code 4" in failed.stdout


def test_watching_can_give_up_and_a_cancelled_run_ends_with_its_own_code(
    live_server: LiveServer, live_worker: LiveWorker, live_lab: Lab
) -> None:
    queued = live_lab.submit(WAITING)

    gave_up = cli(live_server, "run", "watch", queued["id"], "--timeout", "3")
    requested = cli_json(live_server, "run", "cancel", queued["id"], "--reason", "enough seen")
    ended = cli(live_server, "run", "watch", queued["id"], "--quiet", "--json")

    assert gave_up.exit_code == EXIT_STILL_RUNNING == 14
    assert "out | working" in gave_up.stdout
    assert "it keeps going" in gave_up.stderr
    assert requested["cancel_requested_at"] is not None
    assert ended.exit_code == RUN_EXIT_CODES["cancelled"] == 11
    assert json.loads(ended.stdout)["status_reason"] == "enough seen"
    assert "working" not in ended.stderr  # --quiet


def test_a_queued_run_without_any_supervisor_says_why_it_waits(
    live_server: LiveServer, live_lab: Lab
) -> None:
    queued = live_lab.submit('print("nobody runs me")')

    result = cli(live_server, "run", "watch", queued["id"], "--timeout", "0.5")
    workers = cli(live_server, "worker", "list")

    assert result.exit_code == EXIT_STILL_RUNNING
    assert "no supervisor is alive" in result.stderr
    assert "numericos worker run" in workers.stdout


def test_everything_observed_of_a_run_can_be_read_back(
    live_server: LiveServer, live_worker: LiveWorker, live_lab: Lab, tmp_path: Path
) -> None:
    experiment = live_lab.experiment(
        live_lab.program(
            """
            import os, sys, time
            print("step 1")
            print("step 2")
            print("slow convergence", file=sys.stderr)
            time.sleep(0.5)
            with open(os.path.join(os.environ["NUMERICOS_OUTPUT_DIR"], "u.txt"), "w") as handle:
                handle.write("0.5\\n")
            """
        )
    )
    finished = cli(live_server, "run", "submit", experiment["id"], "--watch", "--quiet", "--json")
    run_id = json.loads(finished.stdout)["id"]

    logs = cli_json(live_server, "run", "logs", run_id)
    plain = cli(live_server, "run", "logs", run_id, "--plain", "--stream", "stdout")
    tail = cli(live_server, "run", "logs", run_id, "--tail", "1", "--stream", "stderr")
    followed = cli(live_server, "run", "logs", run_id, "--follow", "--json")
    resources = cli_json(live_server, "run", "resources", run_id)
    events = cli_json(live_server, "run", "events", run_id)
    listed = cli_json(live_server, "artifact", "list", "--run", run_id)
    shown = cli(live_server, "run", "show", run_id)
    project_runs = cli_json(live_server, "run", "list", "--project", live_lab.project["id"])
    supervisors = cli_json(live_server, "worker", "list")

    assert sorted(line["text"] for line in logs["lines"]) == [
        "slow convergence",
        "step 1",
        "step 2",
    ]
    assert logs["complete"] is True
    assert plain.stdout.splitlines() == ["step 1", "step 2"]
    assert tail.stdout.strip().endswith("err | slow convergence")
    assert [json.loads(line) for line in followed.stdout.splitlines()] == logs["lines"]
    assert len(resources["samples"]) >= 2
    assert [event["type"] for event in events["events"]] == [
        "RUN_QUEUED",
        "RUN_STARTED",
        "RUN_FINISHED",
    ]
    result_file = next(item for item in listed["artifacts"] if item["name"] == "outputs/u.txt")
    assert "ended:      exit code 0" in shown.stdout
    assert "measured:" in shown.stdout and "from the system at its exit" in shown.stdout
    assert "sampled:    at most" in shown.stdout
    too_late = cli(live_server, "run", "cancel", run_id)
    assert too_late.exit_code == 0
    assert "had already ended (succeeded); nothing was cancelled" in too_late.stderr
    assert [item["id"] for item in project_runs["runs"]] == [run_id]
    assert (supervisors["alive"], supervisors["workers"][0]["alive"]) == (1, True)

    target = tmp_path / "downloads" / "u.txt"
    downloaded = cli(live_server, "artifact", "get", result_file["id"], "--output", str(target))
    to_stdout = cli(live_server, "artifact", "get", result_file["id"])
    missing = cli(live_server, "artifact", "get", "art_01J9W2Z4K7QX8YB3N5M6T0R1S2")

    assert downloaded.exit_code == 0
    assert target.read_text() == "0.5\n"
    assert to_stdout.stdout == "0.5\n"
    assert missing.exit_code == 1
    assert "NOT_FOUND" in missing.stderr


def test_run_list_needs_exactly_one_scope(live_server: LiveServer) -> None:
    neither = cli(live_server, "run", "list")
    both = cli(live_server, "run", "list", "--experiment", "exp_x", "--project", "prj_x")

    assert (neither.exit_code, both.exit_code) == (2, 2)
    assert "exactly one of --experiment and --project" in neither.stderr


def test_registering_a_contract_twice_with_reuse_returns_the_same_experiment(
    live_server: LiveServer, live_lab: Lab, tmp_path: Path
) -> None:
    contract = tmp_path / "contract.yaml"
    contract.write_text(
        "schema: numericos.experiment.v1\n"
        "name: Scripted\n"
        "question: Is registration repeatable?\n"
        "execution: {command: [python3, solver.py]}\n"
        "limits: {wall_seconds: 5}\n"
    )
    arguments = ("experiment", "add", str(contract), "-p", live_lab.project["id"], "--reuse")

    first = cli_json(live_server, *arguments)
    again = cli_json(live_server, *arguments)

    assert again == first


def test_a_contract_file_is_run_in_one_command_and_again_under_the_same_experiment(
    live_server: LiveServer, live_worker: LiveWorker, live_lab: Lab, tmp_path: Path
) -> None:
    command = live_lab.program(
        """
        import sys
        print("grid", sys.argv[1])
        """,
        "{grid}",
    )
    contract = tmp_path / "grid-study.yaml"
    contract.write_text(
        yaml.safe_dump(
            {
                "schema": "numericos.experiment.v1",
                "question": "Does the result change with the grid?",
                "independent_variables": {"grid": [32, 64]},
                "execution": {"command": command},
                "limits": {"wall_seconds": 20},
            }
        )
    )
    project = live_lab.project["id"]

    coarse = cli(live_server, "experiment", "run", str(contract), "-p", project, "-P", "grid=32")
    fine = cli(
        live_server,
        "experiment",
        "run",
        str(contract),
        "-p",
        project,
        "-P",
        "grid=64",
        "--detach",
        "--json",
    )
    undeclared = cli(live_server, "experiment", "run", str(contract), "-p", project, "-P", "grid=7")
    detached = json.loads(fine.stdout)
    waited = cli(live_server, "run", "watch", detached["id"], "--quiet")
    status = cli(live_server, "run", "status", detached["id"])
    experiments = cli_json(live_server, "experiment", "list", "-p", project)["experiments"]

    assert coarse.exit_code == 0
    assert "out | grid 32" in coarse.stdout
    assert (fine.exit_code, detached["status"]) == (0, "queued")
    assert undeclared.exit_code == 1  # refused by the protocol, nothing queued
    assert waited.exit_code == 0
    assert status.stdout.strip() == "succeeded"
    assert [(item["name"], item["run_count"]) for item in experiments] == [("grid-study", 2)]


def test_the_heat_example_runs_from_its_contract_file_and_its_metrics_are_read_back(
    live_server: LiveServer, live_worker: LiveWorker, live_lab: Lab
) -> None:
    live_lab.install_example("heat2d-python")
    contract = str(live_lab.repo.root / "examples" / "heat2d-python" / "experiment.yaml")
    project = live_lab.project["id"]

    stable = cli(
        live_server, "experiment", "run", contract, "-p", project, "-P", "dt=0.0002", "--json"
    )
    unstable = cli(live_server, "experiment", "run", contract, "-p", project, "-P", "dt=0.0003")
    run_id = json.loads(stable.stdout)["id"]
    shown = cli(live_server, "run", "metrics", run_id)
    document = cli_json(live_server, "run", "metrics", run_id)
    tail = cli(live_server, "run", "metric", run_id, "l2_error", "--tail", "2")
    followed = cli(live_server, "run", "metric", run_id, "norm_l2", "--follow", "--json")
    unknown = cli(live_server, "run", "metric", run_id, "enthalpy")

    assert stable.exit_code == 0
    assert "out | step    600" in stable.stderr  # the parsed progress lines are output
    assert "numericos.metric.v1" not in stable.stderr  # the records are not
    assert unstable.exit_code == RUN_EXIT_CODES["failed"]
    assert "failure:    numerical_instability" in unstable.stdout
    assert "metric max_abs_u was above 1.0 for 3 consecutive sample(s)" in unstable.stdout

    assert "L0 Process          observed" in shown.stdout
    assert "L1 Output parsers   observed" in shown.stdout
    assert "L2 Instrumentation  observed" in shown.stdout
    assert "L3 Validators       not configured" in shown.stdout
    assert "says whether the result is valid" in shown.stdout
    lines = {line.split()[0]: line for line in shown.stdout.splitlines() if " sample" in line}
    assert "parser" in lines["norm_l2"] and "61 samples" in lines["norm_l2"]
    assert "at step 600" in lines["l2_error"] and "[1]" in lines["l2_error"]
    assert "supervisor" in lines["wall_time"] and "[s]" in lines["wall_time"]
    assert " 1 sample " in lines["wall_time"]
    assert len(document["series"]) == 6

    steps = [line.split()[0] for line in tail.stdout.splitlines()]
    assert steps == ["590", "600"]
    streamed = [json.loads(line) for line in followed.stdout.splitlines()]
    assert len(streamed) == 61 and streamed[-1]["step"] == 600
    assert unknown.exit_code == 1 and "NOT_FOUND" in unknown.stderr


def test_a_supervisor_does_not_start_against_a_database_of_another_schema(tmp_path: Path) -> None:
    completed = subprocess.run(
        [
            sys.executable,
            "-m",
            "numericos",
            "worker",
            "run",
            "--data-dir",
            str(tmp_path / "never-migrated"),
            "--schema-timeout",
            "0.6",
        ],
        capture_output=True,
        text=True,
        timeout=60,
        check=False,
    )

    assert completed.returncode == 1
    assert "waiting for" in completed.stderr
    assert "numericos db upgrade" in completed.stderr
    assert "serving" not in completed.stderr


def test_a_stopped_supervisor_says_so_and_leaves_in_an_orderly_way(
    live_server: LiveServer, live_worker: LiveWorker
) -> None:
    before = cli_json(live_server, "worker", "list")

    live_worker.stop()
    after = cli_json(live_server, "worker", "list")

    assert before["alive"] == 1
    assert after["alive"] == 0
    assert after["workers"][0]["stopped_at"] is not None
    assert "runs in progress continue under their monitors" in live_worker.logs()
