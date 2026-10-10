from __future__ import annotations

from fastapi import APIRouter

from numericos.api.deps import Context, Uow
from numericos.api.errors import CONFLICT_RESPONSES
from numericos.core.schemas import (
    BoardOut,
    CardCreate,
    CardOut,
    ProjectCreate,
    ProjectList,
    ProjectOut,
    ProjectPatch,
)
from numericos.services import cards, projects

router = APIRouter(tags=["projects"])


@router.post("/projects", status_code=201, summary="Create a research project")
def create_project(body: ProjectCreate, uow: Uow, context: Context) -> ProjectOut:
    return projects.create_project(uow, body, context)


@router.get("/projects", summary="List projects in creation order")
def list_projects(uow: Uow) -> ProjectList:
    return projects.list_projects(uow)


@router.get("/projects/{project_id}", summary="Get one project")
def get_project(project_id: str, uow: Uow) -> ProjectOut:
    return projects.get_project(uow, project_id)


@router.patch(
    "/projects/{project_id}",
    summary="Update a project (requires its current version)",
    responses=CONFLICT_RESPONSES,
)
def update_project(project_id: str, body: ProjectPatch, uow: Uow, context: Context) -> ProjectOut:
    return projects.update_project(uow, project_id, body, context)


@router.get(
    "/projects/{project_id}/board",
    summary="Cards of a project in board order (column, then rank)",
)
def get_board(project_id: str, uow: Uow) -> BoardOut:
    return cards.get_board(uow, project_id)


@router.post(
    "/projects/{project_id}/cards",
    status_code=201,
    summary="Create a typed card at the end of its column",
)
def create_card(project_id: str, body: CardCreate, uow: Uow, context: Context) -> CardOut:
    return cards.create_card(uow, project_id, body, context)
