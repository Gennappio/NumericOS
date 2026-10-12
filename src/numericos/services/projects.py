"""Project use cases."""

from __future__ import annotations

from pathlib import Path

from numericos.core.enums import EventType
from numericos.core.errors import InvalidRequestError, NotAGitRepositoryError
from numericos.core.ids import new_id
from numericos.core.schemas import (
    ExecutionTrust,
    ProjectCreate,
    ProjectList,
    ProjectOut,
    ProjectPatch,
    ProjectVersion,
)
from numericos.events.ledger import EventContext, build_event
from numericos.persistence.engine import utcnow
from numericos.persistence.models import Project
from numericos.persistence.unit_of_work import UnitOfWork
from numericos.provenance import git
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
        if "root_path" in changed and project.execution_trusted_at is not None:
            # Trust was given to a directory. Another directory has to earn it again.
            project.execution_trusted_at = None
            changed.append("execution_trusted_at")
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


def _field_issue(field: str, message: str) -> dict[str, object]:
    return {"errors": [{"loc": ["body", field], "msg": message, "type": "execution_trust"}]}


def trust_execution(
    uow: UnitOfWork, project_id: str, body: ExecutionTrust, context: EventContext
) -> ProjectOut:
    """Allow commands to be executed in the project directory.

    Running an experiment means running the project's code with the user's permissions, so it
    needs an explicit decision about one exact directory, which must be a Git work tree.
    """
    with uow:
        project = require_project(uow, project_id)
        check_version("project", project.id, current=project.version, provided=body.version)
        if project.root_path is None:
            raise InvalidRequestError(
                "the project has no code path to trust; set root_path first",
                details=_field_issue("root_path", "the project has no root_path"),
            )
        if body.root_path != project.root_path:
            raise InvalidRequestError(
                "root_path does not match the project's code path",
                details=_field_issue(
                    "root_path", f"the project's root_path is {project.root_path}"
                ),
            )
        if not git.is_toplevel(Path(project.root_path)):
            raise NotAGitRepositoryError(
                f"{project.root_path} is not the top directory of a Git work tree",
                details={"root_path": project.root_path},
            )
        if project.execution_trusted_at is not None:
            return ProjectOut.model_validate(project)

        project.execution_trusted_at = utcnow()
        project.version += 1
        project.updated_at = project.execution_trusted_at
        out = ProjectOut.model_validate(project)
        uow.record(
            build_event(
                event_type=EventType.PROJECT_EXECUTION_TRUSTED,
                project_id=project.id,
                subject_id=project.id,
                payload={"project": out.model_dump(mode="json")},
                context=context,
            )
        )
        uow.commit()
    return out


def revoke_execution_trust(
    uow: UnitOfWork, project_id: str, body: ProjectVersion, context: EventContext
) -> ProjectOut:
    """Stop accepting new runs for the project. Runs that already started are not touched."""
    with uow:
        project = require_project(uow, project_id)
        check_version("project", project.id, current=project.version, provided=body.version)
        if project.execution_trusted_at is None:
            return ProjectOut.model_validate(project)

        project.execution_trusted_at = None
        project.version += 1
        project.updated_at = utcnow()
        out = ProjectOut.model_validate(project)
        uow.record(
            build_event(
                event_type=EventType.PROJECT_EXECUTION_TRUST_REVOKED,
                project_id=project.id,
                subject_id=project.id,
                payload={"project": out.model_dump(mode="json")},
                context=context,
            )
        )
        uow.commit()
    return out
