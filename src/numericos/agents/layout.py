"""Files of a turn directory, shared by the supervisor and the API readers."""

from __future__ import annotations

from pathlib import Path

PROMPT = "prompt.md"  # supervisor: what was sent to the agent, as its standard input
SPEC = "spec.json"  # supervisor: the argument vector and working directory
STREAM = "stream.jsonl"  # the agent's standard output: one JSON record per line
STDERR = "stderr.log"  # the agent's standard error
PROCESS = "process.json"  # supervisor: identity of the agent process, written right after start
UNTRACKED = "untracked.json"  # supervisor: untracked files of the repository before the turn


def turns_root(data_dir: Path) -> Path:
    return data_dir / "agent-turns"


def turn_dir(data_dir: Path, message_id: str) -> Path:
    return turns_root(data_dir) / message_id
