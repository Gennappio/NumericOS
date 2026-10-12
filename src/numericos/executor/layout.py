"""Files of a run directory, shared by the monitor, the worker and the API readers."""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

SPEC = "spec.json"  # worker: what to execute and within which limits
MONITOR = "monitor.json"  # monitor: its own identity, written first of all
LAUNCH = "launch.stamp"  # monitor: touched just before the program starts
STARTED = "started.json"  # monitor: identity of the program's process
OUTPUT = "output.jsonl"  # monitor: output lines with arrival time and stream
RESOURCES = "resources.jsonl"  # monitor: samples of the process tree
JOURNAL = "journal.jsonl"  # monitor: what it did (limits, signals, ...)
EXIT = "exit.json"  # monitor: how the program ended
CANCEL = "cancel.json"  # API or worker: a request to stop the program
MONITOR_LOG = "monitor.log"  # the monitor's own stderr
CODE = "code"  # the exported commit (ref mode)
OUTPUTS = "outputs"  # where the program is told to write results
ENVIRONMENT = "environment"  # outputs of the environment probes


def runs_root(data_dir: Path) -> Path:
    return data_dir / "runs"


def run_dir(data_dir: Path, run_id: str) -> Path:
    return runs_root(data_dir) / run_id


def write_json_atomic(path: Path, payload: Any, *, mode: int = 0o644) -> None:
    """Write a JSON file so that readers see either nothing or the complete document."""
    temporary = path.with_name(f".{path.name}.tmp")
    descriptor = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, mode)
    with os.fdopen(descriptor, "w") as handle:
        json.dump(payload, handle, sort_keys=True)
        handle.flush()
        os.fsync(handle.fileno())
    os.replace(temporary, path)


def read_json(path: Path) -> Any | None:
    """The document in ``path``, or None while it does not exist."""
    try:
        return json.loads(path.read_bytes())
    except FileNotFoundError:
        return None
