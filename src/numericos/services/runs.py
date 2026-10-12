"""Run use cases.

Creating a run records the exact argument vector and the exact code revision under the
experiment's frozen protocol, and queues it. Nothing is executed by the API: a supervisor
process picks queued runs up.
"""

from __future__ import annotations

import hashlib
import json

from numericos.core.enums import EventType, RunStatus
from numericos.core.errors import (
    IdempotencyConflictError,
    NotReproducibleError,
    StaleRevisionError,
)
from numericos.core.experiment import ExperimentProtocol, render_command, resolve_parameters
from numericos.core.ids import new_id
from numericos.core.schemas import RunCreate, RunList, RunOut, RunRecord
from numericos.events.ledger import EventContext, build_event
from numericos.persistence.engine import utcnow
from numericos.persistence.models import Run
from numericos.persistence.unit_of_work import UnitOfWork
from numericos.provenance.code import resolve_at_submission
from numericos.services import experiments
from numericos.services.guards import (
    require_experiment,
    require_project,
    require_run,
    require_trusted_root,
)


def _request_digest(data: RunCreate) -> str:
    canonical = json.dumps(data.model_dump(mode="json"), sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _replay(uow: UnitOfWork, experiment_id: str, key: str | None, digest: str) -> RunOut | None:
    """The run an earlier request with this idempotency key created, if there is one."""
    if key is None:
        return None
    earlier = uow.runs.by_idempotency_key(experiment_id, key)
    if earlier is None:
        return None
    if earlier.request_digest != digest:
        raise IdempotencyConflictError(
            f"idempotency key {key!r} was used for a different request",
            details={"run_id": earlier.id, "idempotency_key": key},
        )
    return RunOut.model_validate(earlier)


def create_run(
    uow: UnitOfWork,
    experiment_id: str,
    data: RunCreate,
    context: EventContext,
    *,
    idempotency_key: str | None = None,
    reproduces_run_id: str | None = None,
) -> tuple[RunOut, bool]:
    """Queue a run. Returns the run and whether this call created it.

    With an idempotency key, repeating the same request returns the run created the first
    time; the same key with a different request is a conflict, never a second run.
    """
    digest = _request_digest(data)

    with uow:  # read what the run is derived from
        experiment = require_experiment(uow, experiment_id)
        replayed = _replay(uow, experiment.id, idempotency_key, digest)
        if replayed is not None:
            return replayed, False
        root = require_trusted_root(require_project(uow, experiment.project_id))
        protocol = ExperimentProtocol.model_validate(experiment.protocol)
        protocol_digest = experiment.protocol_digest
        parameters = resolve_parameters(protocol, data.parameters)
        argv = render_command(protocol, parameters, data.seed)

    # Git is consulted outside any database transaction: the ref becomes a commit now.
    code = resolve_at_submission(root, protocol.execution.code, data.code_ref)

    now = utcnow()
    with uow:
        experiment = require_experiment(uow, experiment_id)
        if experiment.protocol_digest != protocol_digest:
            raise StaleRevisionError(
                f"the protocol of experiment {experiment.id} changed while the run was created",
                details={"resource": "experiment", "id": experiment.id},
            )
        replayed = _replay(uow, experiment.id, idempotency_key, digest)
        if replayed is not None:
            return replayed, False
        run = uow.runs.add(
            Run(
                id=new_id("run"),
                project_id=experiment.project_id,
                experiment_id=experiment.id,
                label=data.label,
                status=RunStatus.QUEUED.value,
                parameters=parameters,
                seed=data.seed,
                argv=argv,
                protocol_digest=protocol_digest,
                idempotency_key=idempotency_key,
                request_digest=digest,
                code=code.model_dump(mode="json"),
                code_sha=code.sha,
                reproduces_run_id=reproduces_run_id,
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


def rerun(
    uow: UnitOfWork, run_id: str, context: EventContext, *, idempotency_key: str | None = None
) -> tuple[RunOut, bool]:
    """Queue a run with the same protocol, parameters, seed and commit as an earlier one.

    Only a run of an exact commit can be repeated this way. A working-tree run is reproduced by
    hand from its recorded commit, patch and untracked files.
    """
    with uow:
        original = require_run(uow, run_id)
        experiment = require_experiment(uow, original.experiment_id)
        protocol = ExperimentProtocol.model_validate(experiment.protocol)
        code = original.code or {}
        if code.get("mode") != "ref" or not code.get("sha"):
            raise NotReproducibleError(
                f"run {original.id} did not execute an exact commit; reproduce it from its "
                "recorded commit, patch and untracked files",
                details={"run_id": original.id, "code_mode": code.get("mode")},
            )
        data = RunCreate(
            parameters={name: original.parameters[name] for name in protocol.independent_variables},
            seed=original.seed,
            label=f"reproduces {original.id}",
            code_ref=code["sha"],
        )
        experiment_id, original_id = experiment.id, original.id
    return create_run(
        uow,
        experiment_id,
        data,
        context,
        idempotency_key=idempotency_key,
        reproduces_run_id=original_id,
    )


def list_runs(uow: UnitOfWork, experiment_id: str) -> RunList:
    with uow:
        experiment = require_experiment(uow, experiment_id)
        return RunList(
            runs=[RunOut.model_validate(run) for run in uow.runs.list_for_experiment(experiment.id)]
        )


def get_run(uow: UnitOfWork, run_id: str) -> RunOut:
    with uow:
        return RunOut.model_validate(require_run(uow, run_id))


def export_record(uow: UnitOfWork, run_id: str) -> RunRecord:
    """The run together with the protocol it ran under: what a third party needs to repeat it."""
    with uow:
        run = require_run(uow, run_id)
        experiment = require_experiment(uow, run.experiment_id)
        count = uow.runs.count_by_experiment([experiment.id]).get(experiment.id, 0)
        return RunRecord(
            exported_at=utcnow(),
            run=RunOut.model_validate(run),
            experiment=experiments.to_out(experiment, count),
        )
