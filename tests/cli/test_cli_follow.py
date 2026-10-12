"""`numericos events follow` as a real subprocess: JSON Lines out, exact resume point on loss."""

from __future__ import annotations

import json
import subprocess
import sys
import threading
from collections.abc import Iterator
from contextlib import contextmanager
from typing import Any

from tests.conftest import LiveServer, free_port
from tests.integration.helpers import ledger, new_card, new_project


@contextmanager
def follow(base_url: str, *args: str, watchdog: float = 20.0) -> Iterator[subprocess.Popen[str]]:
    """Run the command; a hung process is killed after ``watchdog`` seconds instead of blocking."""
    process = subprocess.Popen(
        [sys.executable, "-m", "numericos", "events", "follow", *args, "--api-url", base_url],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    timer = threading.Timer(watchdog, process.kill)
    timer.start()
    try:
        yield process
    finally:
        timer.cancel()
        if process.poll() is None:
            process.kill()
        process.wait()


def read_event(process: subprocess.Popen[str]) -> dict[str, Any]:
    assert process.stdout is not None
    line = process.stdout.readline()
    assert line, f"no event was printed; stderr: {process.stderr.read() if process.stderr else ''}"
    event: dict[str, Any] = json.loads(line)
    return event


def stderr_of(process: subprocess.Popen[str]) -> str:
    assert process.stderr is not None
    return process.stderr.read()


def test_follow_replays_the_ledger_then_prints_new_events_as_json_lines(
    live_server: LiveServer,
) -> None:
    project = new_project(live_server)
    new_card(live_server, project["id"], "replayed")

    with follow(live_server.base_url, "-p", project["id"], "--json", "--limit", "3") as process:
        replayed = [read_event(process), read_event(process)]
        new_card(live_server, project["id"], "live")
        live = read_event(process)
        assert process.wait(10) == 0
        assert stderr_of(process) == ""

    assert [*replayed, live] == ledger(live_server, project["id"])
    assert live["payload"]["card"]["title"] == "live"


def test_follow_resumes_after_a_cursor(live_server: LiveServer) -> None:
    project = new_project(live_server)
    for title in ("a", "b"):
        new_card(live_server, project["id"], title)
    recorded = ledger(live_server, project["id"])
    cursor = str(recorded[1]["seq"])

    with follow(
        live_server.base_url, "-p", project["id"], "--json", "--after", cursor, "--limit", "1"
    ) as process:
        assert read_event(process) == recorded[2]
        assert process.wait(10) == 0


def test_follow_says_where_to_resume_when_the_stream_breaks(live_server: LiveServer) -> None:
    project = new_project(live_server)
    new_card(live_server, project["id"], "last one seen")

    with follow(live_server.base_url, "-p", project["id"], "--json") as process:
        last = [read_event(process), read_event(process)][-1]
        live_server.stop()

        assert process.wait(10) == 3
        assert f"resume with --after {last['seq']}" in stderr_of(process)


def test_follow_reports_api_errors_and_an_unreachable_backend(live_server: LiveServer) -> None:
    unknown = "prj_01J9W2Z4K7QX8YB3N5M6T0R1S2"

    with follow(live_server.base_url, "-p", unknown, "--json") as process:
        assert process.wait(10) == 1
        assert json.loads(stderr_of(process))["error"]["code"] == "NOT_FOUND"
        assert process.stdout is not None
        assert process.stdout.read() == ""

    with follow(f"http://127.0.0.1:{free_port()}", "-p", unknown) as process:
        assert process.wait(10) == 3
        assert "resume with --after 0" in stderr_of(process)


def test_follow_prints_readable_lines_by_default(live_server: LiveServer) -> None:
    project = new_project(live_server)

    with follow(live_server.base_url, "-p", project["id"], "--limit", "1") as process:
        assert process.wait(10) == 0
        assert process.stdout is not None
        line = process.stdout.read()

    assert "PROJECT_CREATED" in line
    assert project["id"] in line
