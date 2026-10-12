"""Which supervisors exist and whether they are alive."""

from __future__ import annotations

from collections import Counter

from numericos.core.enums import RunStatus
from numericos.core.schemas import WorkerList, WorkerOut
from numericos.executor.liveness import worker_alive
from numericos.persistence.engine import utcnow
from numericos.persistence.unit_of_work import UnitOfWork

ACTIVE = (RunStatus.STARTING.value, RunStatus.RUNNING.value)
#: Every restart leaves a row; only the newest are of interest.
LISTED = 20


def list_workers(uow: UnitOfWork) -> WorkerList:
    """Supervisors, newest first. Without a live one, queued runs wait: the list says so."""
    with uow:
        now = utcnow()
        load = Counter(run.worker_id for run in uow.runs.with_status(ACTIVE))
        workers = [
            WorkerOut(
                id=row.id,
                pid=row.pid,
                hostname=row.hostname,
                version=row.version,
                max_parallel_runs=row.max_parallel_runs,
                started_at=row.started_at,
                heartbeat_at=row.heartbeat_at,
                stopped_at=row.stopped_at,
                alive=worker_alive(row, now),
                active_runs=load.get(row.id, 0),
            )
            for row in uow.workers.list(LISTED)
        ]
    return WorkerList(workers=workers, alive=sum(worker.alive for worker in workers))
