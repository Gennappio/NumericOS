"""What stays true when a supervisor or a monitor goes away, and when two supervisors compete."""

from __future__ import annotations

import os
import signal
import sqlite3
import subprocess
import sys
import threading
import time
from collections.abc import Callable
from datetime import timedelta
from pathlib import Path
from typing import Any

import psutil
import pytest
from sqlalchemy.exc import OperationalError

from numericos.config import Settings
from numericos.executor import launch, layout
from numericos.executor import worker as worker_module
from numericos.executor.liveness import process_alive, worker_alive
from numericos.executor.worker import Worker
from numericos.persistence.engine import utcnow
from numericos.persistence.models import Worker as WorkerRow
from numericos.persistence.unit_of_work import UnitOfWork
from tests.conftest import LiveWorker
from tests.executor.helpers import wait_for
from tests.lab import Lab, drive, end_all_runs

COUNTING = """
    import time
    for step in range(30):
        print("step", step, flush=True)
        time.sleep(0.1)
    """
WAITING = """
    import time
    print("ready", flush=True)
    time.sleep(60)
    """


def test_a_run_survives_the_death_of_its_supervisor_and_is_taken_over(
    lab: Lab, settings: Settings, tmp_path: Path
) -> None:
    first = LiveWorker(settings.data_dir, tmp_path / "worker.log")
    first.start()
    try:
        queued = lab.submit(COUNTING)
        wait_for(lambda: lab.status(queued["id"]) == "running", what="the run to start")
        first.kill()  # no chance to say goodbye
    finally:
        first.stop()
    orphan = lab.run(queued["id"])
    assert psutil.pid_exists(orphan["pid"])  # the program goes on without any supervisor

    second = Worker(settings, poll_interval=0.05, stale_after=0.5)
    second.start()
    try:
        second.run_until_idle()
    finally:
        second.stop()
        end_all_runs(settings.data_dir)

    run = lab.run(queued["id"])
    adopted = lab.event(run["id"], "RUN_ADOPTED")
    assert (run["status"], run["exit_code"]) == ("succeeded", 0)
    assert run["worker_id"] == second.id
    assert adopted["payload"] == {"previous_worker_id": orphan["worker_id"], "worker_id": second.id}
    assert lab.output(run["id"]) == [f"step {step}" for step in range(30)]  # nothing was missed


def test_a_supervisor_that_stops_hands_its_runs_to_the_next_one_at_once(
    lab: Lab, settings: Settings, supervisor: Worker
) -> None:
    queued = lab.submit(COUNTING)
    drive(supervisor, lambda: lab.status(queued["id"]) == "running")

    supervisor.stop()
    successor = Worker(settings, poll_interval=0.05)  # default patience with silent workers: 15 s
    successor.start()
    taken_over_after = time.monotonic()
    try:
        drive(successor, lambda: lab.run(queued["id"])["worker_id"] == successor.id, timeout=5)
        waited = time.monotonic() - taken_over_after
        successor.run_until_idle()
    finally:
        successor.stop()

    run = lab.run(queued["id"])
    assert waited < 3  # a worker that said it stopped is not waited for
    assert run["status"] == "succeeded"
    assert lab.event(run["id"], "RUN_ADOPTED")["payload"]["previous_worker_id"] == supervisor.id
    assert lab.output(run["id"]) == [f"step {step}" for step in range(30)]


def test_a_run_whose_monitor_died_is_reported_and_then_lost_not_guessed(
    lab: Lab, settings: Settings, supervisor: Worker
) -> None:
    queued = lab.submit(WAITING)
    drive(supervisor, lambda: lab.output(queued["id"]) == ["ready"])
    monitor = layout.read_json(layout.run_dir(settings.data_dir, queued["id"]) / layout.MONITOR)
    assert monitor is not None

    os.kill(monitor["pid"], signal.SIGKILL)
    drive(supervisor, lambda: "RUN_MONITOR_LOST" in lab.event_types(queued["id"]))
    unobserved = lab.run(queued["id"])
    supervisor.tick()
    supervisor.tick()
    reported = lab.event_types(queued["id"]).count("RUN_MONITOR_LOST")

    os.killpg(unobserved["pid"], signal.SIGKILL)
    supervisor.run_until_idle()

    run = lab.run(queued["id"])
    assert unobserved["status"] == "running"  # the program is alive: nothing else is known
    assert "monitor" in unobserved["status_reason"]
    assert reported == 1  # said once, not at every round
    assert (run["status"], run["failure_class"]) == ("lost", "unknown")
    assert (run["exit_code"], run["exit_signal"], run["outcome"]) == (None, None, None)
    assert lab.events(run["id"])[-1]["payload"]["status"] == "lost"


def test_a_run_claimed_by_a_supervisor_that_died_before_starting_it_is_queued_again(
    lab: Lab, supervisor: Worker, uow: Callable[[], UnitOfWork]
) -> None:
    queued = lab.submit('print("second attempt")')
    with uow() as work:
        run = work.runs.get(queued["id"])
        assert run is not None
        run.status = "starting"
        run.worker_id = "wrk_gone"
        run.updated_at = utcnow() - timedelta(seconds=60)
        work.commit()

    supervisor.run_until_idle()

    assert lab.status(queued["id"]) == "succeeded"
    assert lab.output(queued["id"]) == ["second attempt"]
    assert lab.event_types(queued["id"]) == [
        "RUN_QUEUED",
        "RUN_ADOPTED",
        "RUN_REQUEUED",
        "RUN_STARTED",
        "RUN_FINISHED",
    ]


def test_a_monitor_that_cannot_start_fails_the_run_with_what_it_said(
    lab: Lab, supervisor: Worker, monkeypatch: pytest.MonkeyPatch
) -> None:
    def broken_monitor(run_dir: Path) -> subprocess.Popen[bytes]:
        code = (
            "import sys; print('ImportError: no module named psutil', file=sys.stderr); sys.exit(1)"
        )
        with (run_dir / layout.MONITOR_LOG).open("ab") as log:
            return subprocess.Popen([sys.executable, "-c", code], stdout=log, stderr=log)

    monkeypatch.setattr(launch, "spawn_monitor", broken_monitor)
    queued = lab.submit('print("never runs")')

    supervisor.run_until_idle()

    run = lab.run(queued["id"])
    assert (run["status"], run["failure_class"]) == ("failed", "infrastructure")
    assert run["status_reason"] == (
        "the monitor could not start (exit code 1): ImportError: no module named psutil"
    )
    assert run["started_at"] is None


def test_a_supervisor_does_not_start_a_run_taken_from_it_while_it_prepared_it(
    lab: Lab,
    supervisor: Worker,
    settings: Settings,
    uow: Callable[[], UnitOfWork],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    queued = lab.submit('print("must be started once, by its new owner")')
    prepare = launch.prepare

    def slow_prepare(**arguments: Any) -> launch.Prepared:
        prepared = prepare(**arguments)
        with uow() as work:  # meanwhile another supervisor takes the run over
            run = work.runs.get(queued["id"])
            assert run is not None
            run.worker_id = "wrk_other"
            work.commit()
        return prepared

    monkeypatch.setattr(launch, "prepare", slow_prepare)
    claimed = supervisor._claim_next()
    assert claimed is not None and claimed == queued["id"]
    supervisor._launch(claimed)

    run = lab.run(queued["id"])
    run_dir = layout.run_dir(settings.data_dir, queued["id"])
    assert (run["status"], run["worker_id"]) == ("starting", "wrk_other")
    assert supervisor._monitors == {}
    assert not (run_dir / layout.MONITOR).exists()
    assert lab.event_types(queued["id"]) == ["RUN_QUEUED"]


def test_a_reading_that_was_overtaken_is_dropped_not_applied_twice(
    lab: Lab,
    supervisor: Worker,
    settings: Settings,
    uow: Callable[[], UnitOfWork],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    queued = lab.submit('print("done")')
    drive(
        supervisor, lambda: (layout.run_dir(settings.data_dir, queued["id"]) / layout.EXIT).exists()
    )
    read = worker_module.read_run_files

    def overtaken(run_dir: Path, offsets: dict[str, Any]) -> worker_module.Reading:
        reading = read(run_dir, offsets)
        with uow() as work:  # somebody else records the same files first
            run = work.runs.get(queued["id"])
            assert run is not None
            run.ingest = {**reading.offsets, "seen_by": "somebody else"}
            work.commit()
        return reading

    with monkeypatch.context() as patched:
        patched.setattr(worker_module, "read_run_files", overtaken)
        before = lab.status(queued["id"])
        supervisor._ingest(queued["id"])
        dropped = lab.status(queued["id"])
    supervisor.run_until_idle()

    assert before == dropped  # the overtaken reading changed nothing
    assert lab.status(queued["id"]) == "succeeded"
    assert lab.event_types(queued["id"]).count("RUN_FINISHED") == 1
    assert len(lab.artifacts(queued["id"])) == len(set(lab.artifacts(queued["id"])))


def test_a_supervisor_busy_with_a_long_step_is_still_seen_alive(
    lab: Lab, settings: Settings, uow: Callable[[], UnitOfWork]
) -> None:
    busy = Worker(settings, heartbeat_interval=0.1)
    busy.start()
    try:
        with uow() as work:
            first = work.workers.get(busy.id)
            assert first is not None
            registered = first.heartbeat_at
        time.sleep(0.6)  # no round is made: the worker is "busy"
        with uow() as work:
            later = work.workers.get(busy.id)
            assert later is not None
            beating = later.heartbeat_at
            alive = worker_alive(later, utcnow(), stale_after=0.5)
    finally:
        busy.stop()

    assert beating > registered
    assert alive


def test_two_supervisors_never_start_the_same_run(lab: Lab, settings: Settings) -> None:
    experiment = lab.experiment(lab.program('print("once")'))
    queued = [lab.queue(experiment)["id"] for _ in range(8)]
    workers = [Worker(settings, max_parallel=2, poll_interval=0.01) for _ in range(2)]
    failures: list[BaseException] = []

    def serve(worker: Worker) -> None:
        try:
            worker.run_until_idle(timeout=60)
        except BaseException as error:  # reported by the assertion below, not lost in a thread
            failures.append(error)

    for worker in workers:
        worker.start()
    threads = [threading.Thread(target=serve, args=(worker,)) for worker in workers]
    try:
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join(90)
    finally:
        for worker in workers:
            worker.stop()
        end_all_runs(settings.data_dir)

    assert failures == []
    for run_id in queued:
        assert lab.status(run_id) == "succeeded"
        assert lab.event_types(run_id) == ["RUN_QUEUED", "RUN_STARTED", "RUN_FINISHED"]
        assert lab.output(run_id) == ["once"]
    assert {lab.run(run_id)["worker_id"] for run_id in queued} <= {worker.id for worker in workers}


def test_a_busy_database_does_not_end_the_supervisor_but_other_errors_do(
    supervisor: Worker, monkeypatch: pytest.MonkeyPatch
) -> None:
    rounds: list[str] = []

    def busy_once() -> None:
        rounds.append("round")
        if len(rounds) == 1:
            raise OperationalError("UPDATE", {}, sqlite3.OperationalError("database is locked"))

    monkeypatch.setattr(supervisor, "tick", busy_once)
    supervisor.run_forever(lambda: len(rounds) >= 2)
    assert rounds == ["round", "round"]

    def broken() -> None:
        raise OperationalError("SELECT", {}, sqlite3.OperationalError("no such table: runs"))

    monkeypatch.setattr(supervisor, "tick", broken)
    with pytest.raises(OperationalError, match="no such table"):
        supervisor.run_forever(lambda: False)


def test_a_process_is_its_pid_and_its_start_time() -> None:
    me = psutil.Process()
    finished = subprocess.Popen([sys.executable, "-c", "pass"])
    finished.wait()

    assert process_alive(me.pid, me.create_time())
    assert not process_alive(me.pid, me.create_time() - 100)  # same PID, another process
    assert not process_alive(finished.pid, time.time())
    assert not process_alive(None, None)


def test_a_worker_is_alive_while_it_keeps_its_heartbeat_and_has_not_stopped() -> None:
    now = utcnow()

    def worker(*, silent_for: float, stopped: bool = False) -> WorkerRow:
        return WorkerRow(
            id="wrk_test",
            pid=1,
            hostname="host",
            version="0",
            max_parallel_runs=1,
            started_at=now - timedelta(hours=1),
            heartbeat_at=now - timedelta(seconds=silent_for),
            stopped_at=now if stopped else None,
        )

    assert worker_alive(worker(silent_for=1), now)
    assert not worker_alive(worker(silent_for=60), now)
    assert not worker_alive(worker(silent_for=1, stopped=True), now)
    assert not worker_alive(None, now)
