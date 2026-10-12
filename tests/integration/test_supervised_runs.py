"""A run seen from outside while real processes do the work: API, supervisor, monitor, program."""

from __future__ import annotations

import time

from numericos.config import Settings
from numericos.executor.worker import Worker
from tests.conftest import LiveServer, LiveWorker
from tests.executor.helpers import wait_for
from tests.integration.helpers import event_stream, take
from tests.lab import Lab, end_all_runs


def test_events_written_by_the_supervisor_reach_an_open_stream_without_waiting_for_a_heartbeat(
    live_server: LiveServer, live_lab: Lab
) -> None:
    # The server's streams re-read the ledger only every 15 s. The supervisor commits from
    # another process, so only the ledger watcher can deliver its events sooner than that.
    queued = live_lab.submit('print("observed")')
    cursor = live_lab.events(queued["id"])[-1]["seq"]
    worker = Worker(Settings(data_dir=live_server.data_dir), poll_interval=0.05)
    worker.start()

    try:
        with event_stream(live_server, live_lab.project["id"], after=cursor, timeout=5) as stream:
            worker.run_until_idle()
            committed = time.monotonic()
            streamed = take(stream, 2)
            delay = time.monotonic() - committed
    finally:
        worker.stop()
        end_all_runs(live_server.data_dir)

    assert [event["type"] for event in streamed] == ["RUN_STARTED", "RUN_FINISHED"]
    assert {event["run_id"] for event in streamed} == {queued["id"]}
    assert streamed[-1]["payload"]["status"] == "succeeded"
    assert delay < 3


def test_runs_and_their_records_are_still_there_after_the_api_restarts(
    live_server: LiveServer, live_lab: Lab
) -> None:
    queued = live_lab.submit('print("durable")')
    worker = Worker(Settings(data_dir=live_server.data_dir), poll_interval=0.05)
    worker.start()
    try:
        worker.run_until_idle()
    finally:
        worker.stop()
    before = (
        live_lab.run(queued["id"]),
        live_lab.events(queued["id"]),
        live_lab.output(queued["id"]),
        live_lab.artifacts(queued["id"]),
    )

    live_server.stop()
    live_server.start()

    after = (
        live_lab.run(queued["id"]),
        live_lab.events(queued["id"]),
        live_lab.output(queued["id"]),
        live_lab.artifacts(queued["id"]),
    )
    assert after == before
    assert after[0]["status"] == "succeeded"
    assert after[2] == ["durable"]


def test_a_run_goes_on_while_the_api_is_restarted_and_is_complete_afterwards(
    live_server: LiveServer, live_worker: LiveWorker, live_lab: Lab
) -> None:
    queued = live_lab.submit(
        """
        import time
        for step in range(40):
            print("step", step, flush=True)
            time.sleep(0.1)
        """
    )
    wait_for(lambda: live_lab.output(queued["id"]), what="the first output of the run")

    live_server.stop()
    time.sleep(1.0)  # the program and its supervisor work on with no API at all
    live_server.start()

    during = live_lab.run(queued["id"])
    wait_for(lambda: live_lab.status(queued["id"]) == "succeeded", what="the run to finish")
    run = live_lab.run(queued["id"])
    assert during["status"] == "running"  # it neither stopped nor was it made up as finished
    assert run["pid"] == during["pid"]
    assert live_lab.output(run["id"]) == [f"step {step}" for step in range(40)]
    assert live_lab.event_types(run["id"]) == ["RUN_QUEUED", "RUN_STARTED", "RUN_FINISHED"]
