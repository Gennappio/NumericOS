"""Project use cases."""

from __future__ import annotations

from numericos.core.enums import EventType
from numericos.core.ids import new_id
from numericos.core.schemas import ProjectCreate, ProjectList, ProjectOut, ProjectPatch
from numericos.events.ledger import EventContext, build_event
from numericos.persistence.engine import utcnow
from numericos.persistence.models import Project
from numericos.persistence.unit_of_work import UnitOfWork
from numericos.services.guards import check_version, require_project

#: Fields a PATCH may change, in the order they are reported in ``changed_fields``.
PATCHABLE = ("name", "research_question", "description", "root_path")


def create_project(uow: UnitOfWork, data: ProjectCreate, context: EventContext) -> ProjectOut:
    now = utcnow()
    with uow:
        project = uow.projects.add(
            Project(
                id=new_id("prj"),
                name=data.name,
                research_question=data.research_question,
                description=data.description,
                root_path=data.root_path,
                is_demo=data.is_demo,
                version=1,
                created_at=now,
                updated_at=now,
            )
        )
        out = ProjectOut.model_validate(project)
        uow.record(
            build_event(
                event_type=EventType.PROJECT_CREATED,
                project_id=project.id,
                subject_id=project.id,
                payload={"project": out.model_dump(mode="json")},
                context=context,
            )
        )
        uow.commit()
    return out


def list_projects(uow: UnitOfWork) -> ProjectList:
    with uow:
        return ProjectList(
            projects=[ProjectOut.model_validate(project) for project in uow.projects.list()]
        )


def get_project(uow: UnitOfWork, project_id: str) -> ProjectOut:
    with uow:
        return ProjectOut.model_validate(require_project(uow, project_id))


def update_project(
    uow: UnitOfWork, project_id: str, patch: ProjectPatch, context: EventContext
) -> ProjectOut:
    with uow:
        project = require_project(uow, project_id)
        check_version("project", project.id, current=project.version, provided=patch.version)

        changed = [
            field
            for field in PATCHABLE
            if field in patch.model_fields_set and getattr(project, field) != getattr(patch, field)
        ]
        if not changed:
            return ProjectOut.model_validate(project)

        for field in changed:
            setattr(project, field, getattr(patch, field))
        project.version += 1
        project.updated_at = utcnow()
        out = ProjectOut.model_validate(project)
        uow.record(
            build_event(
                event_type=EventType.PROJECT_UPDATED,
                project_id=project.id,
                subject_id=project.id,
                payload={"changed_fields": changed, "project": out.model_dump(mode="json")},
                context=context,
            )
        )
        uow.commit()
    return out
