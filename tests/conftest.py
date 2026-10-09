"""Shared fixtures: an in-process TestClient and a real API subprocess (``LiveServer``)."""

from __future__ import annotations

import os
import socket
import subprocess
import sys
import time
from collections.abc import Iterator
from pathlib import Path

import httpx
import pytest
from fastapi.testclient import TestClient

from numericos.api.app import create_app
from numericos.config import Settings


@pytest.fixture
def settings(tmp_path: Path) -> Settings:
    return Settings(data_dir=tmp_path / "data")


@pytest.fixture
def client(settings: Settings) -> Iterator[TestClient]:
    with TestClient(create_app(settings)) as test_client:
        yield test_client


def free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


class LiveServer:
    """A real ``numericos serve`` subprocess on a free loopback port.

    ``stop()``/``start()`` on the same data directory is how restart persistence is proven.
    """

    def __init__(self, data_dir: Path, log_path: Path) -> None:
        self.data_dir = data_dir
        self.log_path = log_path
        self.port = free_port()
        self.process: subprocess.Popen[str] | None = None

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
                env={**os.environ, "PYTHONUNBUFFERED": "1"},
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
        if self.process is None:
            return
        self.process.terminate()
        try:
            self.process.wait(timeout)
        except subprocess.TimeoutExpired:
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
