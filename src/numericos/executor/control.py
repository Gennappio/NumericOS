"""Requests to a running monitor. They are files, so they work whoever is alive."""

from __future__ import annotations

from pathlib import Path

from numericos.executor import layout
from numericos.persistence.engine import TIMESTAMP_FORMAT, utcnow


def request_cancel(run_dir: Path, *, reason: str, actor: str) -> None:
    """Ask the monitor of a run to stop its program. Idempotent: the first request stands."""
    run_dir.mkdir(parents=True, exist_ok=True)
    target = run_dir / layout.CANCEL
    if target.exists():
        return
    layout.write_json_atomic(
        target,
        {"reason": reason, "actor": actor, "requested_at": utcnow().strftime(TIMESTAMP_FORMAT)},
    )
