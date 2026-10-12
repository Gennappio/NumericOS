"""Shared fixtures: migrated SQLite engine, unit of work, in-process TestClient, LiveServer."""

from __future__ import annotations

import json
import os
import socket
import subprocess
import sys
import time
from collections.abc import Callable, Iterator
from pathlib import Path

import httpx
import pytest
from fastapi.testclient import TestClient
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker

from numericos.api.app import create_app
from numericos.config import Settings
from numericos.events.notifier import EventNotifier
from numericos.executor.worker import Worker
from numericos.persistence import migrate
from numericos.persistence.engine import make_engine, make_session_factory
from numericos.persistence.unit_of_work import UnitOfWork
from tests.gitrepo import Repo, make_repo
from tests.lab import Lab, end_all_runs, end_all_turns

#: The coding agent of the tests: a script that speaks Claude Code's protocol without a model.
FAKE_CLAUDE = [sys.executable, str(Path(__file__).resolve().parent / "fake_claude.py")]


@pytest.fixture
def settings(tmp_path: Path) -> Settings:
    return Settings(data_dir=tmp_path / "data", claude_command=FAKE_CLAUDE)


@pytest.fixture
def engine(settings: Settings) -> Iterator[Engine]:
    """A freshly migrated database in a temporary data directory."""
    settings.data_dir.mkdir(parents=True, exist_ok=True)
    engine = make_engine(settings.db_path)
    migrate.upgrade(engine)
    yield engine
    engine.dispose()


@pytest.fixture
def session_factory(engine: Engine) -> sessionmaker[Session]:
    return make_session_factory(engine)


@pytest.fixture
def notifier() -> EventNotifier:
    return EventNotifier()


@pytest.fixture
def uow(
    session_factory: sessionmaker[Session], notifier: EventNotifier
) -> Callable[[], UnitOfWork]:
    return lambda: UnitOfWork(session_factory, notifier)


@pytest.fixture
def client(settings: Settings, engine: Engine) -> Iterator[TestClient]:
    with TestClient(create_app(settings)) as test_client:
        yield test_client


@pytest.fixture
def repo(tmp_path: Path) -> Repo:
    """A Git repository with one commit, standing in for a research project's code."""
    return make_repo(tmp_path / "repo")


def free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


class LiveServer:
    """A real ``numericos serve`` subprocess on a free loopback port.

    ``stop()``/``start()`` on the same data directory is how restart persistence is proven.
    """

    def __init__(self, data_dir: Path, log_path: Path, env: dict[str, str] | None = None) -> None:
        self.data_dir = data_dir
        self.log_path = log_path
        # The coding agent of a live server is the stand-in as well (see ``FAKE_CLAUDE``).
        self.env = {"NUMERICOS_CLAUDE_COMMAND": json.dumps(FAKE_CLAUDE), **(env or {})}
        self.port = free_port()
        self.process: subprocess.Popen[str] | None = None
        #: True when the last ``stop()`` had to SIGKILL a server that ignored SIGTERM.
        self.killed = False

    @property
    def base_url(self) -> str:
        return f"http://127.0.0.1:{self.port}"

    def start(self, timeout: float = 30.0) -> None:
        assert self.process is None, "server already running"
        command = [
            sys.executable,
            "-m",
            "numericos",
            "serve",
            "--port",
            str(self.port),
            "--data-dir",
            str(self.data_dir),
        ]
        with self.log_path.open("a") as log:
            self.process = subprocess.Popen(
                command,
                stdout=log,
                stderr=subprocess.STDOUT,
                text=True,
                env={**os.environ, "PYTHONUNBUFFERED": "1", **self.env},
            )
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            if self.process.poll() is not None:
                raise RuntimeError(
                    f"server exited early (code {self.process.returncode}):\n{self.logs()}"
                )
            try:
                if httpx.get(f"{self.base_url}/v1/health", timeout=0.5).status_code == 200:
                    return
            except httpx.TransportError:
                pass
            time.sleep(0.1)
        self.stop()
        raise RuntimeError(f"server not ready after {timeout}s:\n{self.logs()}")

    def stop(self, timeout: float = 10.0) -> None:
        """SIGTERM, as a supervisor or `--reload` would send; SIGKILL only if that is ignored."""
        if self.process is None:
            return
        self.killed = False
        self.process.terminate()
        try:
            self.process.wait(timeout)
        except subprocess.TimeoutExpired:
            self.killed = True
            self.process.kill()
            self.process.wait()
        self.process = None

    def logs(self) -> str:
        return self.log_path.read_text() if self.log_path.exists() else ""


@pytest.fixture
def live_server(tmp_path: Path) -> Iterator[LiveServer]:
    server = LiveServer(tmp_path / "data", tmp_path / "server.log")
    server.start()
    try:
        yield server
    finally:
        server.stop()


@pytest.fixture
def fast_heartbeat_server(tmp_path: Path) -> Iterator[LiveServer]:
    """A server whose event streams re-read the ledger every 0.3 s instead of every 15 s."""
    server = LiveServer(
        tmp_path / "data",
        tmp_path / "server.log",
        env={"NUMERICOS_SSE_HEARTBEAT_SECONDS": "0.3"},
    )
    server.start()
    try:
        yield server
    finally:
        server.stop()


class LiveWorker:
    """A real ``numericos worker run`` subprocess serving a data directory."""

    def __init__(self, data_dir: Path, log_path: Path) -> None:
        self.data_dir = data_dir
        self.log_path = log_path
        self.process: subprocess.Popen[str] | None = None

    def start(self, timeout: float = 30.0) -> None:
        assert self.process is None, "worker already running"
        command = [
            sys.executable,
            "-m",
            "numericos",
            "worker",
            "run",
            "--data-dir",
            str(self.data_dir),
            "--poll-interval",
            "0.1",
        ]
        with self.log_path.open("a") as log:
            self.process = subprocess.Popen(
                command,
                stdout=log,
                stderr=subprocess.STDOUT,
                text=True,
                env={
                    **os.environ,
                    "PYTHONUNBUFFERED": "1",
                    "NUMERICOS_CLAUDE_COMMAND": json.dumps(FAKE_CLAUDE),
                },
            )
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            if self.process.poll() is not None:
                raise RuntimeError(
                    f"worker exited early (code {self.process.returncode}):\n{self.logs()}"
                )
            if " serving " in self.logs():
                return
            time.sleep(0.05)
        self.stop()
        raise RuntimeError(f"worker not ready after {timeout}s:\n{self.logs()}")

    def stop(self, timeout: float = 10.0) -> None:
        """SIGTERM: the worker leaves in an orderly way and says so in the database."""
        if self.process is None:
            return
        self.process.terminate()
        try:
            self.process.wait(timeout)
        except subprocess.TimeoutExpired:
            self.process.kill()
            self.process.wait()
        self.process = None

    def kill(self) -> None:
        """SIGKILL: the worker vanishes without a word, as in a crash."""
        assert self.process is not None
        self.process.kill()
        self.process.wait()
        self.process = None

    def logs(self) -> str:
        return self.log_path.read_text() if self.log_path.exists() else ""


@pytest.fixture
def lab(client: TestClient, repo: Repo) -> Lab:
    """A trusted project with a Git repository, reached through the in-process API."""
    return Lab(client, repo)


@pytest.fixture
def supervisor(settings: Settings, engine: Engine) -> Iterator[Worker]:
    """An in-process supervisor on the test database; its monitors are real processes."""
    worker = Worker(settings, poll_interval=0.05, heartbeat_interval=0.2)
    worker.start()
    try:
        yield worker
    finally:
        worker.stop()
        end_all_runs(settings.data_dir)
        end_all_turns(settings.data_dir)


@pytest.fixture
def live_lab(live_server: LiveServer, repo: Repo) -> Iterator[Lab]:
    """A trusted project with a Git repository, reached through a real API process."""
    with httpx.Client(base_url=live_server.base_url, timeout=30) as http:
        yield Lab(http, repo)


@pytest.fixture
def live_worker(live_server: LiveServer, tmp_path: Path) -> Iterator[LiveWorker]:
    worker = LiveWorker(live_server.data_dir, tmp_path / "worker.log")
    worker.start()
    try:
        yield worker
    finally:
        worker.stop()
        end_all_runs(live_server.data_dir)
        end_all_turns(live_server.data_dir)
