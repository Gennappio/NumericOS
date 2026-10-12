"""Run use cases.

Creating a run records the exact argument vector under the experiment's frozen protocol and
queues it. Nothing is executed by the API: a supervisor process picks queued runs up.
"""

from __future__ import annotations

import hashlib
import json

from numericos.core.enums import EventType, RunStatus
from numericos.core.errors import IdempotencyConflictError
from numericos.core.experiment import ExperimentProtocol, render_command, resolve_parameters
from numericos.core.ids import new_id
from numericos.core.schemas import RunCreate, RunList, RunOut
from numericos.events.ledger import EventContext, build_event
from numericos.persistence.engine import utcnow
from numericos.persistence.models import Run
from numericos.persistence.unit_of_work import UnitOfWork
from numericos.services.guards import require_experiment, require_run


def _request_digest(data: RunCreate) -> str:
    canonical = json.dumps(data.model_dump(mode="json"), sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def create_run(
    uow: UnitOfWork,
    experiment_id: str,
    data: RunCreate,
    context: EventContext,
    *,
    idempotency_key: str | None = None,
) -> tuple[RunOut, bool]:
    """Queue a run. Returns the run and whether this call created it.

    With an idempotency key, repeating the same request returns the run created the first
    time; the same key with a different request is a conflict, never a second run.
    """
    digest = _request_digest(data)
    now = utcnow()
    with uow:
        experiment = require_experiment(uow, experiment_id)
        if idempotency_key is not None:
            earlier = uow.runs.by_idempotency_key(experiment.id, idempotency_key)
            if earlier is not None:
                if earlier.request_digest != digest:
                    raise IdempotencyConflictError(
                        f"idempotency key {idempotency_key!r} was used for a different request",
                        details={"run_id": earlier.id, "idempotency_key": idempotency_key},
                    )
                return RunOut.model_validate(earlier), False

        protocol = ExperimentProtocol.model_validate(experiment.protocol)
        parameters = resolve_parameters(protocol, data.parameters)
        run = uow.runs.add(
            Run(
                id=new_id("run"),
                project_id=experiment.project_id,
                experiment_id=experiment.id,
                label=data.label,
                status=RunStatus.QUEUED.value,
                parameters=parameters,
                seed=data.seed,
                argv=render_command(protocol, parameters, data.seed),
                protocol_digest=experiment.protocol_digest,
                idempotency_key=idempotency_key,
                request_digest=digest,
                version=1,
                created_at=now,
                updated_at=now,
            )
        )
        out = RunOut.model_validate(run)
        uow.record(
            build_event(
                event_type=EventType.RUN_QUEUED,
                project_id=run.project_id,
                subject_id=run.id,
                run_id=run.id,
                payload={"run": out.model_dump(mode="json")},
                context=context,
            )
        )
        uow.commit()
    return out, True


def list_runs(uow: UnitOfWork, experiment_id: str) -> RunList:
    with uow:
        experiment = require_experiment(uow, experiment_id)
        return RunList(
            runs=[RunOut.model_validate(run) for run in uow.runs.list_for_experiment(experiment.id)]
        )


def get_run(uow: UnitOfWork, run_id: str) -> RunOut:
    with uow:
        return RunOut.model_validate(require_run(uow, run_id))
