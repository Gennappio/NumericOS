"""Hypothesis use cases.

A hypothesis is created ``proposed``. Its epistemic status is not editable here: it changes only
through recorded evidence and decisions, never because a card moved or a run finished.
"""

from __future__ import annotations

from numericos.core.enums import EpistemicStatus, EventType
from numericos.core.ids import new_id
from numericos.core.schemas import (
    HypothesisCreate,
    HypothesisList,
    HypothesisOut,
    HypothesisPatch,
)
from numericos.events.ledger import EventContext, build_event
from numericos.persistence.engine import utcnow
from numericos.persistence.models import Hypothesis
from numericos.persistence.unit_of_work import UnitOfWork
from numericos.services.guards import check_version, require_hypothesis, require_project

PATCHABLE = ("title", "claim", "rationale", "prediction", "falsification", "assumptions")


def create_hypothesis(
    uow: UnitOfWork, project_id: str, data: HypothesisCreate, context: EventContext
) -> HypothesisOut:
    now = utcnow()
    with uow:
        project = require_project(uow, project_id)
        hypothesis = uow.hypotheses.add(
            Hypothesis(
                id=new_id("hyp"),
                project_id=project.id,
                title=data.title,
                claim=data.claim,
                rationale=data.rationale,
                prediction=data.prediction,
                falsification=list(data.falsification),
                assumptions=list(data.assumptions),
                epistemic_status=EpistemicStatus.PROPOSED.value,
                version=1,
                created_at=now,
                updated_at=now,
            )
        )
        out = HypothesisOut.model_validate(hypothesis)
        uow.record(
            build_event(
                event_type=EventType.HYPOTHESIS_CREATED,
                project_id=project.id,
                subject_id=hypothesis.id,
                payload={"hypothesis": out.model_dump(mode="json")},
                context=context,
            )
        )
        uow.commit()
    return out


def list_hypotheses(uow: UnitOfWork, project_id: str) -> HypothesisList:
    with uow:
        project = require_project(uow, project_id)
        return HypothesisList(
            hypotheses=[
                HypothesisOut.model_validate(item)
                for item in uow.hypotheses.list_for_project(project.id)
            ]
        )


def get_hypothesis(uow: UnitOfWork, hypothesis_id: str) -> HypothesisOut:
    with uow:
        return HypothesisOut.model_validate(require_hypothesis(uow, hypothesis_id))


def update_hypothesis(
    uow: UnitOfWork, hypothesis_id: str, patch: HypothesisPatch, context: EventContext
) -> HypothesisOut:
    with uow:
        hypothesis = require_hypothesis(uow, hypothesis_id)
        check_version(
            "hypothesis", hypothesis.id, current=hypothesis.version, provided=patch.version
        )
        changed = [
            field
            for field in PATCHABLE
            if field in patch.model_fields_set
            and getattr(hypothesis, field) != getattr(patch, field)
        ]
        if not changed:
            return HypothesisOut.model_validate(hypothesis)

        for field in changed:
            setattr(hypothesis, field, getattr(patch, field))
        hypothesis.version += 1
        hypothesis.updated_at = utcnow()
        out = HypothesisOut.model_validate(hypothesis)
        uow.record(
            build_event(
                event_type=EventType.HYPOTHESIS_UPDATED,
                project_id=hypothesis.project_id,
                subject_id=hypothesis.id,
                payload={"changed_fields": changed, "hypothesis": out.model_dump(mode="json")},
                context=context,
            )
        )
        uow.commit()
    return out
