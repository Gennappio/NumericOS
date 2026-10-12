"""Run directories and monitors for tests, with real processes."""

from __future__ import annotations

import json
import os
import subprocess
import sys
import textwrap
import time
from pathlib import Path
from typing import Any

from numericos.executor import layout

Json = dict[str, Any]


def python(code: str, *arguments: str) -> list[str]:
    """Argument vector that runs a snippet with the interpreter of the test session."""
    return [sys.executable, "-c", textwrap.dedent(code), *arguments]


def write_spec(run_dir: Path, argv: list[str], **overrides: Any) -> None:
    run_dir.mkdir(parents=True, exist_ok=True)
    payload: Json = {
        "schema": "numericos.run-spec.v1",
        "run_id": "run_test",
        "argv": argv,
        "cwd": str(run_dir),
        "env": {"PATH": os.environ["PATH"], "PYTHONUNBUFFERED": "1"},
        "build": [],
        "wall_seconds": 30,
        "max_rss_bytes": None,
        "grace_seconds": 1.0,
        "max_output_bytes": 10_000_000,
        "resource_interval_seconds": 0.2,
        **overrides,
    }
    (run_dir / layout.SPEC).write_text(json.dumps(payload))


def start_monitor(run_dir: Path) -> subprocess.Popen[bytes]:
    return subprocess.Popen(
        [sys.executable, "-m", "numericos.executor.monitor", str(run_dir)],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.PIPE,
    )


def run_monitor(run_dir: Path, timeout: float = 30) -> Json:
    """Run a monitor to completion and return its ``exit.json``."""
    process = start_monitor(run_dir)
    _out, err = process.communicate(timeout=timeout)
    assert process.returncode == 0, err.decode()
    return exit_of(run_dir)


def read_jsonl(path: Path) -> list[Json]:
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text().splitlines() if line]


def exit_of(run_dir: Path) -> Json:
    document: Json = json.loads((run_dir / layout.EXIT).read_text())
    return document


def output(run_dir: Path, stream: str | None = None) -> list[str]:
    """Recorded output lines, optionally of one stream ("o", "e" or "b")."""
    records = read_jsonl(run_dir / layout.OUTPUT)
    return [record["l"] for record in records if stream is None or record["s"] == stream]


def journal(run_dir: Path) -> list[str]:
    return [entry["type"] for entry in read_jsonl(run_dir / layout.JOURNAL)]


def wait_for(condition: Any, timeout: float = 15.0, what: str = "condition") -> Any:
    """Poll until ``condition()`` is truthy and return its value."""
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        value = condition()
        if value:
            return value
        time.sleep(0.05)
    raise AssertionError(f"timed out after {timeout} s waiting for {what}")
