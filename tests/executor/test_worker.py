"""The supervisor with real programs: what it records, how it stops a run, what it refuses."""

from __future__ import annotations

import hashlib
import json
import stat
import sys
from datetime import datetime
from pathlib import Path

import pytest

from numericos.config import Settings
from numericos.executor import layout
from numericos.executor.worker import Worker
from tests.lab import Lab, drive

WAITING = """
    import time
    print("ready", flush=True)
    time.sleep(60)
    """


def moment(stamp: str) -> datetime:
    return datetime.fromisoformat(stamp)


def test_a_run_is_executed_observed_and_recorded(lab: Lab, supervisor: Worker) -> None:
    queued = lab.submit(
        """
        import os, sys
        print("solving")
        print("careful", file=sys.stderr)
        with open(os.path.join(os.environ["NUMERICOS_OUTPUT_DIR"], "field.txt"), "w") as handle:
            handle.write("42\\n")
        """
    )

    supervisor.run_until_idle()

    run = lab.run(queued["id"])
    assert run["status"] == "succeeded"
    assert (run["exit_code"], run["exit_signal"], run["failure_class"]) == (0, None, None)
    assert run["status_reason"] is None
    assert run["started_at"] < run["finished_at"]
    assert run["wall_seconds"] > 0
    assert run["worker_id"] == supervisor.id
    assert run["outcome"]["termination"]["reason"] == "exited"
    assert run["outcome"]["output"]["stdout_lines"] == 1
    assert 0 < run["outcome"]["program_seconds"] <= run["wall_seconds"]
    assert run["outcome"]["rusage"]["max_rss_bytes"] > 0
    assert run["code"]["sha"] == lab.repo.head
    assert run["environment"]["executable"]["path"] == str(Path(sys.executable).resolve())
    assert run["environment"]["variables"]["NUMERICOS_RUN_ID"] == run["id"]
    assert lab.output(run["id"], "stdout") == ["solving"]
    assert lab.output(run["id"], "stderr") == ["careful"]

    events = lab.events(run["id"])
    assert [event["type"] for event in events] == ["RUN_QUEUED", "RUN_STARTED", "RUN_FINISHED"]
    assert {event["producer"] for event in events[1:]} == {"worker"}
    assert {event["actor"] for event in events[1:]} == {f"worker:{supervisor.id}"}
    assert len({event["correlation_id"] for event in events}) == 1  # the request that queued it
    assert events[-1]["severity"] == "info"
    assert events[-1]["payload"]["status"] == "succeeded"
    assert events[-1]["payload"]["program_started"] is True
    # The ledger's own time is when the supervisor read the files; the payload has the facts.
    assert moment(events[1]["payload"]["started_at"]) == moment(run["started_at"])
    assert moment(events[-1]["payload"]["finished_at"]) == moment(run["finished_at"])
    assert events[-1]["payload"]["program_seconds"] == run["outcome"]["program_seconds"]
    assert moment(events[1]["timestamp_utc"]) >= moment(run["started_at"])

    artifacts = lab.artifacts(run["id"])
    assert {"exit.json", "output.jsonl", "journal.jsonl"} <= set(artifacts)
    assert "resources.jsonl" not in artifacts  # it ended before the first sample: nothing to keep
    assert run["resources"] is None
    field = artifacts["outputs/field.txt"]
    assert field["kind"] == "result"
    assert field["sha256"] == hashlib.sha256(b"42\n").hexdigest()
    assert lab.http.get(f"/v1/artifacts/{field['id']}/content").content == b"42\n"


def test_an_inherited_secret_reaches_the_program_but_not_the_record(
    lab: Lab, supervisor: Worker, settings: Settings, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("SOLVER_API_TOKEN", "s3cret-value")
    monkeypatch.setenv("NOT_ASKED_FOR", "stays with the supervisor")
    queued = lab.submit(
        """
        import os
        print(len(os.environ["SOLVER_API_TOKEN"]), os.environ["OMP_NUM_THREADS"])
        print("HOME" in os.environ, "NOT_ASKED_FOR" in os.environ)
        """,
        execution={"env": {"OMP_NUM_THREADS": "1"}, "inherit_env": ["SOLVER_API_TOKEN"]},
    )

    supervisor.run_until_idle()

    run = lab.run(queued["id"])
    record = lab.get(f"/v1/runs/{run['id']}/record")
    spec = layout.run_dir(settings.data_dir, run["id"]) / layout.SPEC
    assert lab.output(run["id"]) == ["12 1", "True False"]
    assert run["environment"]["variables"]["SOLVER_API_TOKEN"] == "<redacted>"
    assert run["environment"]["variables"]["OMP_NUM_THREADS"] == "1"
    assert "s3cret-value" not in json.dumps(run) + json.dumps(record)
    assert stat.S_IMODE(spec.stat().st_mode) == 0o600  # the one place that holds the value


def test_a_run_executes_its_commit_even_when_the_working_tree_has_moved_on(
    lab: Lab, supervisor: Worker
) -> None:
    command = lab.program('print("committed version")')
    experiment = lab.experiment(command)
    (lab.repo.root / command[1]).write_text('print("uncommitted edit")\n')
    queued = lab.queue(experiment)

    supervisor.run_until_idle()

    run = lab.run(queued["id"])
    assert lab.output(run["id"]) == ["committed version"]
    assert (run["code"]["mode"], run["code"]["dirty"]) == ("ref", False)
    assert run["code"]["submitted_with_dirty_working_tree"] is True


def test_a_working_tree_run_executes_the_edit_and_keeps_what_reproduces_it(
    lab: Lab, supervisor: Worker
) -> None:
    command = lab.program('print("committed version")')
    experiment = lab.experiment(command, execution={"code": {"mode": "working_tree"}})
    (lab.repo.root / command[1]).write_text('print("uncommitted edit")\n')
    lab.repo.write("notes/untracked.txt", "scratch\n")
    queued = lab.queue(experiment)

    supervisor.run_until_idle()

    run = lab.run(queued["id"])
    code = run["code"]
    assert lab.output(run["id"]) == ["uncommitted edit"]
    assert (code["dirty"], code["sha"]) == (True, lab.repo.head)
    assert code["diff_sha256"] is not None
    assert [item["path"] for item in code["untracked"]] == ["notes/untracked.txt"]
    assert code["changed_during_run"] is False
    assert {"code_diff", "untracked_files"} <= {
        item["kind"] for item in lab.artifacts(run["id"]).values()
    }


def test_editing_the_working_tree_while_a_run_is_in_progress_is_noticed(
    lab: Lab, supervisor: Worker
) -> None:
    command = lab.program(
        """
        import time
        print("started", flush=True)
        time.sleep(1.0)
        """
    )
    queued = lab.queue(lab.experiment(command, execution={"code": {"mode": "working_tree"}}))
    drive(supervisor, lambda: lab.output(queued["id"]) == ["started"])

    (lab.repo.root / command[1]).write_text("# edited while the program runs\n")
    supervisor.run_until_idle()

    run = lab.run(queued["id"])
    assert run["status"] == "succeeded"
    assert run["code"]["changed_during_run"] is True
    assert lab.event(run["id"], "RUN_SOURCE_CHANGED")["severity"] == "warning"


def test_a_program_writing_next_to_its_sources_in_the_working_tree_is_not_an_edit(
    lab: Lab, supervisor: Worker
) -> None:
    command = lab.program(
        """
        with open("field.dat", "w") as handle:
            handle.write("1 2 3")
        """
    )
    queued = lab.queue(lab.experiment(command, execution={"code": {"mode": "working_tree"}}))

    supervisor.run_until_idle()

    run = lab.run(queued["id"])
    assert (lab.repo.root / "field.dat").read_text() == "1 2 3"  # where the user expects it
    assert run["code"]["changed_during_run"] is False
    assert "RUN_SOURCE_CHANGED" not in lab.event_types(run["id"])
    assert not any(name.endswith("field.dat") for name in lab.artifacts(run["id"]))


def test_what_a_program_writes_next_to_its_sources_is_listed_with_its_results(
    lab: Lab, supervisor: Worker
) -> None:
    lab.repo.write("helpers.py", "SCALE = 2\n")
    lab.repo.write("notes.md", "committed, and appended to by the program\n")
    command = lab.program(
        """
        import os
        import helpers  # importing it leaves a __pycache__ behind
        os.makedirs("results")
        with open("results/u_final.txt", "w") as handle:
            handle.write(str(21 * helpers.SCALE))
        with open("notes.md", "a") as handle:
            handle.write("converged\\n")
        print(open("compiled.txt").read())
        """
    )
    build = [sys.executable, "-c", "open('compiled.txt', 'w').write('object code')"]
    queued = lab.queue(lab.experiment(command, execution={"build": [build]}))

    supervisor.run_until_idle()

    run = lab.run(queued["id"])
    results = {name for name, item in lab.artifacts(run["id"]).items() if item["kind"] == "result"}
    assert lab.output(run["id"], "stdout") == ["object code"]
    assert results == {"code/results/u_final.txt", "code/notes.md"}  # created, and changed
    written = lab.artifacts(run["id"])["code/results/u_final.txt"]
    assert lab.http.get(f"/v1/artifacts/{written['id']}/content").content == b"42"
    assert not (lab.repo.root / "results").exists()  # the project directory was not touched


def test_a_compiled_program_is_identified_by_the_binary_that_ran(
    lab: Lab, supervisor: Worker, settings: Settings
) -> None:
    lab.repo.write("solver.c.txt", "stands in for a source file\n")
    lab.repo.commit("source")
    script = "#!/bin/sh\necho built-solver-ran\n"
    compile_it = f"import os; open('solver', 'w').write({script!r}); os.chmod('solver', 0o755)"
    queued = lab.queue(
        lab.experiment(["./solver"], execution={"build": [[sys.executable, "-c", compile_it]]})
    )

    supervisor.run_until_idle()

    run = lab.run(queued["id"])
    executable = run["environment"]["executable"]
    binary = layout.run_dir(settings.data_dir, run["id"]) / "code" / "solver"
    assert lab.output(run["id"], "stdout") == ["built-solver-ran"]
    assert executable["argv0"] == "./solver"
    assert executable["path"] == str(binary.resolve())
    assert executable["sha256"] == hashlib.sha256(script.encode()).hexdigest()


def test_a_failing_program_is_a_code_error_with_its_exit_code(lab: Lab, supervisor: Worker) -> None:
    queued = lab.submit(
        """
        import sys
        print("about to fail", file=sys.stderr)
        sys.exit(3)
        """
    )

    supervisor.run_until_idle()

    run = lab.run(queued["id"])
    assert (run["status"], run["failure_class"], run["exit_code"]) == ("failed", "code_error", 3)
    assert run["status_reason"] == "the program exited with code 3"
    assert lab.output(run["id"], "stderr") == ["about to fail"]
    assert lab.events(run["id"])[-1]["severity"] == "error"


def test_a_run_over_its_wall_clock_limit_is_stopped_and_timed_out(
    lab: Lab, supervisor: Worker
) -> None:
    queued = lab.submit(WAITING, limits={"wall_seconds": 0.6, "grace_seconds": 0.5})

    supervisor.run_until_idle()

    run = lab.run(queued["id"])
    exceeded = lab.event(run["id"], "RUN_LIMIT_EXCEEDED")
    assert (run["status"], run["failure_class"]) == ("timed_out", "resource_limit")
    assert run["exit_signal"] == "SIGTERM"
    assert run["outcome"]["termination"]["sigterm_sent"] is True
    assert exceeded["payload"]["limit"] == "wall_seconds"
    assert exceeded["payload"]["threshold"] == 0.6
    assert exceeded["severity"] == "error"


def test_output_beyond_the_limit_is_cut_and_the_run_says_so(lab: Lab, supervisor: Worker) -> None:
    queued = lab.submit(
        """
        for _ in range(30000):
            print("x" * 60)
        """,
        limits={"wall_seconds": 20, "max_output_mb": 1},
    )

    supervisor.run_until_idle()

    run = lab.run(queued["id"])
    assert run["status"] == "succeeded"
    assert run["outcome"]["output"]["truncated"] is True
    assert run["outcome"]["output"]["stdout_lines"] == 30000  # all were seen
    assert len(lab.output(run["id"])) < 30000  # not all were stored
    assert lab.event(run["id"], "RUN_OUTPUT_TRUNCATED")["payload"]["limit_bytes"] == 1024 * 1024


def test_cancelling_a_running_program_stops_it_and_is_recorded(
    lab: Lab, supervisor: Worker
) -> None:
    queued = lab.submit(WAITING)
    drive(supervisor, lambda: lab.status(queued["id"]) == "running")

    requested = lab.cancel(queued["id"], "wrong mesh")
    again = lab.cancel(queued["id"], "second thoughts")
    supervisor.run_until_idle()

    run = lab.run(queued["id"])
    assert requested["status"] == "running"  # the request returns before the program is gone
    assert requested["cancel_requested_at"] is not None
    assert again["cancel_requested_at"] == requested["cancel_requested_at"]
    assert (run["status"], run["failure_class"]) == ("cancelled", None)
    assert run["status_reason"] == "wrong mesh"
    assert run["exit_signal"] == "SIGTERM"
    assert lab.event_types(run["id"]) == [
        "RUN_QUEUED",
        "RUN_STARTED",
        "RUN_CANCEL_REQUESTED",
        "RUN_FINISHED",
    ]
    assert lab.events(run["id"])[-1]["severity"] == "warning"


def test_a_queued_run_is_cancelled_at_once_and_never_started(lab: Lab, supervisor: Worker) -> None:
    queued = lab.submit('print("must not run")')

    cancelled = lab.cancel(queued["id"])
    supervisor.run_until_idle()

    run = lab.run(queued["id"])
    assert cancelled["status"] == "cancelled"
    assert (run["status"], run["started_at"], run["worker_id"]) == ("cancelled", None, None)
    assert run["status_reason"] == "cancelled on request"
    assert lab.event_types(run["id"]) == ["RUN_QUEUED", "RUN_CANCEL_REQUESTED", "RUN_FINISHED"]
    assert lab.events(run["id"])[-1]["payload"]["program_started"] is False
    assert lab.output(run["id"]) == []


def test_a_run_cancelled_after_it_was_claimed_is_not_started(lab: Lab, supervisor: Worker) -> None:
    queued = lab.submit('print("must not run")')
    claimed = supervisor._claim_next()

    requested = lab.cancel(queued["id"])
    assert claimed is not None
    supervisor._launch(claimed)

    run = lab.run(queued["id"])
    assert requested["status"] == "starting"
    assert (run["status"], run["started_at"]) == ("cancelled", None)
    assert lab.output(run["id"]) == []


def test_cancelling_a_finished_run_changes_nothing(lab: Lab, supervisor: Worker) -> None:
    queued = lab.submit('print("done")')
    supervisor.run_until_idle()
    before = lab.run(queued["id"])

    after = lab.cancel(queued["id"], "too late")

    assert after == before
    assert "RUN_CANCEL_REQUESTED" not in lab.event_types(queued["id"])


def test_a_queued_run_is_not_started_once_trust_is_withdrawn(lab: Lab, supervisor: Worker) -> None:
    queued = lab.submit('print("must not run")')
    project = lab.get(f"/v1/projects/{lab.project['id']}")
    revoked = lab.http.post(
        f"/v1/projects/{project['id']}:revoke-execution-trust", json={"version": project["version"]}
    )
    assert revoked.status_code == 200, revoked.text

    supervisor.run_until_idle()

    run = lab.run(queued["id"])
    assert (run["status"], run["failure_class"]) == ("failed", "infrastructure")
    assert "trust" in run["status_reason"]
    assert run["started_at"] is None
    assert lab.events(run["id"])[-1]["payload"]["program_started"] is False


def test_an_input_that_is_not_the_expected_file_stops_the_run_before_it_starts(
    lab: Lab, supervisor: Worker
) -> None:
    lab.repo.write("data/mesh.txt", "nodes 4\n")
    command = lab.program('print(open("data/mesh.txt").read().strip())')
    expected = hashlib.sha256(b"nodes 4\n").hexdigest()
    accepted = lab.queue(
        lab.experiment(
            command, execution={"inputs": [{"path": "data/mesh.txt", "sha256": expected}]}
        )
    )
    refused = lab.queue(
        lab.experiment(
            command, execution={"inputs": [{"path": "data/mesh.txt", "sha256": "0" * 64}]}
        )
    )

    supervisor.run_until_idle()

    good, bad = lab.run(accepted["id"]), lab.run(refused["id"])
    assert lab.output(good["id"]) == ["nodes 4"]
    assert good["inputs"] == [
        {"path": "data/mesh.txt", "base": "code", "sha256": expected, "size_bytes": 8}
    ]
    assert (bad["status"], bad["failure_class"]) == ("failed", "data_problem")
    assert "the protocol expects" in bad["status_reason"]
    assert bad["started_at"] is None


def test_a_command_that_cannot_be_started_is_a_code_error(lab: Lab, supervisor: Worker) -> None:
    no_program = lab.queue(lab.experiment(["no-such-solver-binary", "--steps", "10"]))
    no_directory = lab.queue(
        lab.experiment(lab.program('print("x")'), execution={"workdir": "not/there"})
    )

    supervisor.run_until_idle()

    first, second = lab.run(no_program["id"]), lab.run(no_directory["id"])
    assert (first["status"], first["failure_class"]) == ("failed", "code_error")
    assert "could not be started" in first["status_reason"]
    assert first["environment"]["executable"]["path"] is None
    assert first["started_at"] is None
    assert lab.events(first["id"])[-1]["payload"]["program_started"] is False
    assert (second["status"], second["failure_class"]) == ("failed", "code_error")
    assert "working directory" in second["status_reason"]


def test_build_commands_run_before_the_program_and_a_failed_build_fails_the_run(
    lab: Lab, supervisor: Worker
) -> None:
    program = lab.program('print(open("built.txt").read())')
    write = "open('built.txt', 'w').write('built for n={n}')"
    built = lab.queue(
        lab.experiment(
            program,
            independent_variables={"n": [8, 16]},
            execution={"build": [[sys.executable, "-c", f"print('compiling'); {write}"]]},
        ),
        parameters={"n": 16},
    )
    broken = lab.queue(
        lab.experiment(
            program,
            execution={
                "build": [[sys.executable, "-c", "import sys; print('no compiler'); sys.exit(2)"]]
            },
        )
    )

    supervisor.run_until_idle()

    good, bad = lab.run(built["id"]), lab.run(broken["id"])
    assert good["status"] == "succeeded"
    assert lab.output(good["id"], "build") == ["compiling"]
    assert lab.output(good["id"], "stdout") == ["built for n=16"]
    assert (bad["status"], bad["failure_class"]) == ("failed", "code_error")
    assert lab.output(bad["id"], "build") == ["no compiler"]
    assert bad["started_at"] is None


def test_no_more_runs_than_allowed_execute_at_the_same_time(
    lab: Lab, settings: Settings, supervisor: Worker
) -> None:
    experiment = lab.experiment(
        lab.program(
            """
            import time
            time.sleep(0.5)
            """
        )
    )
    queued = [lab.queue(experiment)["id"] for _ in range(5)]
    pair = Worker(settings, max_parallel=2, poll_interval=0.05)
    pair.start()
    busy: list[int] = []

    def all_ended() -> bool:
        statuses = [lab.status(run_id) for run_id in queued]
        busy.append(sum(status in ("starting", "running") for status in statuses))
        return all(status == "succeeded" for status in statuses)

    try:
        drive(pair, all_ended)
    finally:
        pair.stop()

    assert max(busy) == 2
    assert {lab.run(run_id)["worker_id"] for run_id in queued} == {pair.id}
