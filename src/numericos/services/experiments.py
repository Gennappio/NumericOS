"""Experiment use cases.

The protocol of an experiment is its contract. It can be replaced only while no run exists:
once something has been executed under it, a different protocol is a different experiment.
"""

from __future__ import annotations

from numericos.core.enums import EventType
from numericos.core.errors import ProjectMismatchError, ProtocolFrozenError
from numericos.core.experiment import ExperimentProtocol, protocol_digest
from numericos.core.ids import new_id
from numericos.core.schemas import (
    ExperimentCreate,
    ExperimentList,
    ExperimentOut,
    ExperimentPatch,
)
from numericos.events.ledger import EventContext, build_event
from numericos.persistence.engine import utcnow
from numericos.persistence.models import Experiment
from numericos.persistence.unit_of_work import UnitOfWork
from numericos.services.guards import (
    check_version,
    require_experiment,
    require_hypothesis,
    require_project,
)


def to_out(experiment: Experiment, run_count: int) -> ExperimentOut:
    return ExperimentOut(
        id=experiment.id,
        project_id=experiment.project_id,
        hypothesis_id=experiment.hypothesis_id,
        name=experiment.name,
        protocol=ExperimentProtocol.model_validate(experiment.protocol),
        protocol_digest=experiment.protocol_digest,
        run_count=run_count,
        version=experiment.version,
        created_at=experiment.created_at,
        updated_at=experiment.updated_at,
    )


def _event_payload(out: ExperimentOut) -> dict[str, object]:
    return {"experiment": out.model_dump(mode="json", by_alias=True)}


def _require_hypothesis_of_project(uow: UnitOfWork, hypothesis_id: str, project_id: str) -> None:
    hypothesis = require_hypothesis(uow, hypothesis_id)
    if hypothesis.project_id != project_id:
        raise ProjectMismatchError(
            f"hypothesis {hypothesis.id} does not belong to project {project_id}",
            details={
                "hypothesis_id": hypothesis.id,
                "hypothesis_project_id": hypothesis.project_id,
                "requested_project_id": project_id,
            },
        )


def create_experiment(
    uow: UnitOfWork, project_id: str, data: ExperimentCreate, context: EventContext
) -> ExperimentOut:
    now = utcnow()
    with uow:
        project = require_project(uow, project_id)
        if data.hypothesis_id is not None:
            _require_hypothesis_of_project(uow, data.hypothesis_id, project.id)
        experiment = uow.experiments.add(
            Experiment(
                id=new_id("exp"),
                project_id=project.id,
                hypothesis_id=data.hypothesis_id,
                name=data.name,
                protocol=data.protocol.to_json(),
                protocol_digest=protocol_digest(data.protocol),
                version=1,
                created_at=now,
                updated_at=now,
            )
        )
        out = to_out(experiment, run_count=0)
        uow.record(
            build_event(
                event_type=EventType.EXPERIMENT_CREATED,
                project_id=project.id,
                subject_id=experiment.id,
                payload=_event_payload(out),
                context=context,
            )
        )
        uow.commit()
    return out


def list_experiments(uow: UnitOfWork, project_id: str) -> ExperimentList:
    with uow:
        project = require_project(uow, project_id)
        experiments = uow.experiments.list_for_project(project.id)
        counts = uow.runs.count_by_experiment([experiment.id for experiment in experiments])
        return ExperimentList(
            experiments=[to_out(item, counts.get(item.id, 0)) for item in experiments]
        )


def get_experiment(uow: UnitOfWork, experiment_id: str) -> ExperimentOut:
    with uow:
        experiment = require_experiment(uow, experiment_id)
        count = uow.runs.count_by_experiment([experiment.id]).get(experiment.id, 0)
        return to_out(experiment, count)


def update_experiment(
    uow: UnitOfWork, experiment_id: str, patch: ExperimentPatch, context: EventContext
) -> ExperimentOut:
    with uow:
        experiment = require_experiment(uow, experiment_id)
        check_version(
            "experiment", experiment.id, current=experiment.version, provided=patch.version
        )
        run_count = uow.runs.count_by_experiment([experiment.id]).get(experiment.id, 0)
        fields = patch.model_fields_set
        changed: list[str] = []

        if "name" in fields and patch.name != experiment.name:
            assert patch.name is not None
            experiment.name = patch.name
            changed.append("name")
        if "hypothesis_id" in fields and patch.hypothesis_id != experiment.hypothesis_id:
            if patch.hypothesis_id is not None:
                _require_hypothesis_of_project(uow, patch.hypothesis_id, experiment.project_id)
            experiment.hypothesis_id = patch.hypothesis_id
            changed.append("hypothesis_id")
        if patch.protocol is not None:
            digest = protocol_digest(patch.protocol)
            if digest != experiment.protocol_digest:
                if run_count:
                    raise ProtocolFrozenError(
                        f"experiment {experiment.id} has {run_count} run(s); its protocol is "
                        "frozen. Create a new experiment for a different protocol",
                        details={"experiment_id": experiment.id, "run_count": run_count},
                    )
                experiment.protocol = patch.protocol.to_json()
                experiment.protocol_digest = digest
                changed.append("protocol")

        if not changed:
            return to_out(experiment, run_count)

        experiment.version += 1
        experiment.updated_at = utcnow()
        out = to_out(experiment, run_count)
        uow.record(
            build_event(
                event_type=EventType.EXPERIMENT_UPDATED,
                project_id=experiment.project_id,
                subject_id=experiment.id,
                payload={"changed_fields": changed, **_event_payload(out)},
                context=context,
            )
        )
        uow.commit()
    return out
