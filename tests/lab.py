"""A research project with code, experiments and runs, set up through the API.

Supervisor tests execute real programs. Programs are files in a real Git repository, because
that is what a run executes: an exact commit, or the working tree.
"""

from __future__ import annotations

import contextlib
import os
import shutil
import signal
import sys
import textwrap
import time
from collections.abc import Callable
from pathlib import Path
from typing import Any

import httpx
import yaml

from numericos.agents import layout as agent_layout
from numericos.executor import control, layout
from numericos.executor.liveness import process_alive
from numericos.executor.worker import Worker
from tests.gitrepo import Repo

Json = dict[str, Any]
EXAMPLES = Path(__file__).resolve().parents[1] / "examples"


class Lab:
    def __init__(self, http: httpx.Client, repo: Repo) -> None:
        self.http = http
        self.repo = repo
        self._count = 0
        created = self._send(
            "POST", "/v1/projects", 201, {"name": "Lab", "root_path": str(repo.root)}
        )
        self.project: Json = self._send(
            "POST",
            f"/v1/projects/{created['id']}:trust-execution",
            200,
            {"version": created["version"], "root_path": created["root_path"]},
        )

    def _send(self, method: str, path: str, expected: int, body: Json | None = None) -> Json:
        response = self.http.request(method, path, json=body)
        assert response.status_code == expected, response.text
        result: Json = response.json()
        return result

    def get(self, path: str, **params: Any) -> Json:
        response = self.http.get(path, params=params)
        assert response.status_code == 200, response.text
        result: Json = response.json()
        return result

    # ------------------------------------------------------------------ setting up

    def program(self, code: str, *arguments: str, commit: bool = True) -> list[str]:
        """Add a Python program to the repository; return the command that runs it."""
        self._count += 1
        name = f"job_{self._count}.py"
        self.repo.write(name, textwrap.dedent(code))
        if commit:
            self.repo.commit(f"add {name}")
        return [sys.executable, name, *arguments]

    def experiment(self, command: list[str], **protocol: Any) -> Json:
        """An experiment that runs ``command``. ``execution`` extends the execution section;
        any other keyword replaces that section of the protocol."""
        self._count += 1
        execution = {"command": command, **protocol.pop("execution", {})}
        body = {
            "name": f"experiment {self._count}",
            "protocol": {
                "schema": "numericos.experiment.v1",
                "question": "What does the supervisor record about this program?",
                "execution": execution,
                "limits": {"wall_seconds": 20, "grace_seconds": 0.5},
                "observability": {"resource_interval_seconds": 0.2},
                **protocol,
            },
        }
        return self._send("POST", f"/v1/projects/{self.project['id']}/experiments", 201, body)

    def install_example(self, name: str) -> Json:
        """Commit one of this repository's examples to the project, at the same path, and
        return its experiment contract as written in its ``experiment.yaml``."""
        source = EXAMPLES / name
        # The test repository already has a stand-in at this path: the real files replace it.
        shutil.copytree(source, self.repo.root / "examples" / name, dirs_exist_ok=True)
        self.repo.commit(f"add the {name} example")
        contract: Json = yaml.safe_load((source / "experiment.yaml").read_text())
        return contract

    def register(self, contract: Json) -> Json:
        """Register an experiment from a contract file's content (it may carry a name)."""
        protocol = {key: value for key, value in contract.items() if key != "name"}
        body = {"name": contract.get("name", "experiment"), "protocol": protocol}
        return self._send("POST", f"/v1/projects/{self.project['id']}/experiments", 201, body)

    def queue(self, experiment: Json, **body: Any) -> Json:
        return self._send("POST", f"/v1/experiments/{experiment['id']}/runs", 201, body)

    def submit(self, code: str, **protocol: Any) -> Json:
        """Commit a program, define an experiment that runs it and queue one run of it."""
        return self.queue(self.experiment(self.program(code), **protocol))

    # ------------------------------------------------------------------ looking

    def run(self, run_id: str) -> Json:
        return self.get(f"/v1/runs/{run_id}")

    def status(self, run_id: str) -> str:
        return str(self.run(run_id)["status"])

    def events(self, run_id: str) -> list[Json]:
        events: list[Json] = self.get(f"/v1/runs/{run_id}/events", limit=1000)["events"]
        return events

    def event_types(self, run_id: str) -> list[str]:
        return [event["type"] for event in self.events(run_id)]

    def event(self, run_id: str, event_type: str) -> Json:
        return next(event for event in self.events(run_id) if event["type"] == event_type)

    def output(self, run_id: str, stream: str | None = None) -> list[str]:
        """Recorded output lines, optionally of one stream (stdout, stderr or build)."""
        params = {"limit": 5000} if stream is None else {"limit": 5000, "stream": stream}
        return [line["text"] for line in self.get(f"/v1/runs/{run_id}/logs", **params)["lines"]]

    def metrics(self, run_id: str) -> Json:
        return self.get(f"/v1/runs/{run_id}/metrics")

    def series(self, run_id: str) -> dict[str, Json]:
        return {item["name"]: item for item in self.metrics(run_id)["series"]}

    def samples(self, run_id: str, name: str, **params: Any) -> list[Json]:
        page = self.get(f"/v1/runs/{run_id}/metrics/{name}", **{"limit": 5000, **params})
        samples: list[Json] = page["samples"]
        return samples

    def artifacts(self, run_id: str) -> dict[str, Json]:
        listed: list[Json] = self.get(f"/v1/runs/{run_id}/artifacts")["artifacts"]
        return {item["name"]: item for item in listed}

    def cancel(self, run_id: str, reason: str = "") -> Json:
        return self._send("POST", f"/v1/runs/{run_id}:cancel", 200, {"reason": reason})

    # ------------------------------------------------------------------ the agent

    def open_session(self, **body: Any) -> Json:
        return self._send("POST", f"/v1/projects/{self.project['id']}/agent-sessions", 201, body)

    def ask(self, session: Json, content: str) -> Json:
        """Send a prompt; return the queued assistant message (the turn)."""
        return self._send(
            "POST", f"/v1/agent-sessions/{session['id']}/messages", 201, {"content": content}
        )

    def message(self, message_id: str) -> Json:
        return self.get(f"/v1/messages/{message_id}")

    def turn_status(self, message_id: str) -> str:
        return str(self.message(message_id)["status"])

    def turn_events(self, message_id: str) -> list[Json]:
        page = self.get("/v1/events", project_id=self.project["id"], limit=1000)
        return [event for event in page["events"] if event["subject_id"] == message_id]

    def cancel_turn(self, message_id: str, reason: str = "") -> Json:
        return self._send("POST", f"/v1/messages/{message_id}:cancel", 200, {"reason": reason})

    # ------------------------------------------------------------------ documents

    def generate(self, what: str, instructions: str | None = None) -> Json:
        """Ask the agent for the theory or the plan; returns the document, marked pending."""
        body = {} if instructions is None else {"instructions": instructions}
        return self._send("POST", f"/v1/projects/{self.project['id']}/{what}:generate", 202, body)

    def single(self, what: str) -> Json | None:
        document: Json | None = self.get(f"/v1/projects/{self.project['id']}/{what}")["document"]
        return document

    def files(self) -> Json:
        return self.get(f"/v1/projects/{self.project['id']}/files")

    def file(self, path: str) -> Json:
        return next(entry for entry in self.files()["files"] if entry["path"] == path)

    def describe(self, **body: Any) -> Json:
        return self._send("POST", f"/v1/projects/{self.project['id']}/files:describe", 202, body)

    def description(self, path: str) -> Json:
        response = self.http.get(
            f"/v1/projects/{self.project['id']}/files/description", params={"path": path}
        )
        assert response.status_code == 200, response.text
        result: Json = response.json()
        return result

    # ------------------------------------------------------------------ comments

    def comment(self, target: Json, kind: str, quote: str, body: str = "", **offsets: int) -> Json:
        """Comment on a passage of a document or of an answer (a record with a ``role``)."""
        return self._send(
            "POST",
            "/v1/annotations",
            201,
            {**self._target(target), "kind": kind, "quote": quote, "body": body, **offsets},
        )

    @staticmethod
    def _target(target: Json) -> Json:
        return {
            "target_type": "message" if "role" in target else "document",
            "target_id": target["id"],
        }

    def comments(self, target: Json) -> Json:
        return self.get("/v1/annotations", **self._target(target))

    def comment_by_id(self, target: Json, comment_id: str) -> Json:
        listed: list[Json] = self.comments(target)["annotations"]
        return next(item for item in listed if item["id"] == comment_id)

    def send_comments(self, action: str, target: Json, **body: Any) -> Json:
        """Clarify or resolve the open requests on a text; returns what was queued."""
        return self._send(
            "POST", f"/v1/annotations:{action}", 202, {**self._target(target), **body}
        )

    def workspace(self) -> Json:
        return self.get(f"/v1/projects/{self.project['id']}/workspace")

    def move_created(self, message_id: str, **body: Any) -> Json:
        return self._send("POST", f"/v1/messages/{message_id}:move-created-files", 200, body)

    def board(self) -> list[Json]:
        cards: list[Json] = self.get(f"/v1/projects/{self.project['id']}/board")["cards"]
        return cards


def drive(worker: Worker, until: Callable[[], Any], timeout: float = 20.0) -> Any:
    """Let an in-process supervisor work until ``until()`` is truthy; return that value."""
    deadline = time.monotonic() + timeout
    while True:
        worker.tick()
        value = until()
        if value:
            return value
        if time.monotonic() > deadline:
            raise AssertionError(f"the supervisor did not get there within {timeout} s")
        time.sleep(0.05)


def end_all_turns(data_dir: Path) -> None:
    """Leave no agent process of a test behind."""
    root = agent_layout.turns_root(data_dir)
    if not root.is_dir():
        return
    for turn_dir in root.iterdir():
        identity = layout.read_json(turn_dir / agent_layout.PROCESS)
        if identity is not None and process_alive(identity["pid"], identity["create_time"]):
            with contextlib.suppress(ProcessLookupError, PermissionError):
                os.killpg(identity["pgid"], signal.SIGKILL)


def end_all_runs(data_dir: Path, timeout: float = 10.0) -> None:
    """Leave no program of a test behind: cancel what a monitor still watches, kill the rest."""
    root = layout.runs_root(data_dir)
    if not root.is_dir():
        return
    watched = []
    for run_dir in root.iterdir():
        monitor = layout.read_json(run_dir / layout.MONITOR)
        if monitor is None or (run_dir / layout.EXIT).exists():
            continue
        if process_alive(monitor["pid"], monitor["create_time"]):
            control.request_cancel(run_dir, reason="end of the test", actor="test:teardown")
            watched.append(run_dir)
            continue
        started = layout.read_json(run_dir / layout.STARTED)
        if started is not None:
            with contextlib.suppress(ProcessLookupError, PermissionError):
                os.killpg(started["pgid"], signal.SIGKILL)
    deadline = time.monotonic() + timeout
    while watched and time.monotonic() < deadline:
        watched = [run_dir for run_dir in watched if not (run_dir / layout.EXIT).exists()]
        time.sleep(0.05)
