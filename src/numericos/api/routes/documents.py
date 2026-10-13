"""Documents the agent writes about a project: its theory, its pipeline, its files, its
plan."""

from __future__ import annotations

from typing import Annotated, Any

from fastapi import APIRouter, Query, Request
from fastapi.responses import FileResponse

from numericos.api.deps import Context, Uow
from numericos.core.enums import DocumentKind
from numericos.core.schemas import (
    DescribeOut,
    DescribeRequest,
    DocumentOut,
    DocumentSlot,
    ErrorEnvelope,
    FileList,
    GenerateRequest,
)
from numericos.services import documents

router = APIRouter()

GENERATION_RESPONSES: dict[int | str, dict[str, Any]] = {
    409: {
        "model": ErrorEnvelope,
        "description": (
            "The agent command is not installed, the project is not trusted for execution, "
            "or the agent is already writing this document"
        ),
    },
}
FilePath = Annotated[
    str, Query(min_length=1, max_length=1000, description="Path relative to the project root.")
]


@router.get(
    "/projects/{project_id}/theory",
    tags=["documents"],
    summary="The theory of the project as the agent wrote it, and whether it is still current",
)
def get_theory(project_id: str, uow: Uow) -> DocumentSlot:
    return documents.get_single(uow, project_id, DocumentKind.THEORY)


@router.post(
    "/projects/{project_id}/theory:generate",
    status_code=202,
    tags=["documents"],
    summary="Ask the agent to write, or write again, the theory of the project",
    responses=GENERATION_RESPONSES,
)
def generate_theory(
    project_id: str,
    uow: Uow,
    context: Context,
    request: Request,
    body: GenerateRequest | None = None,
) -> DocumentOut:
    return documents.generate_theory(
        uow, project_id, body or GenerateRequest(), context, settings=request.app.state.settings
    )


@router.get(
    "/projects/{project_id}/pipeline",
    tags=["documents"],
    summary="The pipeline of the project: what happens when the program runs, as boxes and arrows",
)
def get_pipeline(project_id: str, uow: Uow) -> DocumentSlot:
    return documents.get_single(uow, project_id, DocumentKind.PIPELINE)


@router.post(
    "/projects/{project_id}/pipeline:generate",
    status_code=202,
    tags=["documents"],
    summary="Ask the agent to describe, or describe again, the pipeline of the project",
    responses=GENERATION_RESPONSES,
)
def generate_pipeline(
    project_id: str,
    uow: Uow,
    context: Context,
    request: Request,
    body: GenerateRequest | None = None,
) -> DocumentOut:
    return documents.generate_pipeline(
        uow, project_id, body or GenerateRequest(), context, settings=request.app.state.settings
    )


@router.get(
    "/projects/{project_id}/plan",
    tags=["documents"],
    summary="The notes of the plan the agent last proposed; its cards are on the board",
)
def get_plan(project_id: str, uow: Uow) -> DocumentSlot:
    return documents.get_single(uow, project_id, DocumentKind.PLAN)


@router.post(
    "/projects/{project_id}/plan:generate",
    status_code=202,
    tags=["documents"],
    summary="Ask the agent for a plan; its cards are put on the board when its turn ends",
    responses=GENERATION_RESPONSES,
)
def generate_plan(
    project_id: str,
    uow: Uow,
    context: Context,
    request: Request,
    body: GenerateRequest | None = None,
) -> DocumentOut:
    return documents.generate_plan(
        uow, project_id, body or GenerateRequest(), context, settings=request.app.state.settings
    )


@router.get(
    "/projects/{project_id}/files",
    tags=["documents"],
    summary="The files of the project, each with its description if it has one",
)
def list_files(project_id: str, uow: Uow) -> FileList:
    return documents.list_files(uow, project_id)


@router.post(
    "/projects/{project_id}/files:describe",
    status_code=202,
    tags=["documents"],
    summary="Ask the agent to describe files: the ones named, or all in a state",
    responses=GENERATION_RESPONSES,
)
def describe_files(
    project_id: str, body: DescribeRequest, uow: Uow, context: Context, request: Request
) -> DescribeOut:
    return documents.describe_files(
        uow, project_id, body, context, settings=request.app.state.settings
    )


@router.get(
    "/projects/{project_id}/files/description",
    tags=["documents"],
    summary="The description of one file",
)
def get_file_description(project_id: str, path: FilePath, uow: Uow) -> DocumentOut:
    return documents.file_description(uow, project_id, path)


@router.get(
    "/projects/{project_id}/files/content",
    tags=["documents"],
    summary="The content of one file of the project directory, to show it",
    response_class=FileResponse,
    responses={200: {"content": {"application/octet-stream": {}}, "description": "The file"}},
)
def get_file_content(project_id: str, path: FilePath, uow: Uow) -> FileResponse:
    file, media_type = documents.file_content(uow, project_id, path)
    # Shown in place (an image in a page), never executed: the type is the one of its name.
    return FileResponse(
        file,
        media_type=media_type,
        headers={"X-Content-Type-Options": "nosniff", "Content-Security-Policy": "sandbox"},
    )


@router.get("/documents/{document_id}", tags=["documents"], summary="Get one document")
def get_document(document_id: str, uow: Uow) -> DocumentOut:
    return documents.get_document(uow, document_id)
