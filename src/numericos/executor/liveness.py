"""Is a process, or a worker, still there? A process is its PID *and* its start time."""

from __future__ import annotations

from datetime import datetime

import psutil

from numericos.persistence.models import Worker

#: A worker that has not written its heartbeat for this long is considered gone.
WORKER_STALE_SECONDS = 15.0


def process_alive(pid: int | None, create_time: float | None) -> bool:
    """True when the process with this PID is the one that was started at ``create_time``.

    A PID alone is not an identity: the operating system reuses it. A zombie is not alive.
    """
    if pid is None or create_time is None:
        return False
    try:
        process = psutil.Process(pid)
        return (
            abs(process.create_time() - create_time) < 0.01
            and process.status() != psutil.STATUS_ZOMBIE
        )
    except psutil.Error:
        return False


def worker_alive(
    worker: Worker | None, now: datetime, stale_after: float = WORKER_STALE_SECONDS
) -> bool:
    if worker is None or worker.stopped_at is not None:
        return False
    return (now - worker.heartbeat_at).total_seconds() <= stale_after
