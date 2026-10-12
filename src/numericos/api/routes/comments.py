"""Comments on what the agent wrote; Clarify and Resolve."""

from __future__ import annotations

from typing import Annotated, Any

from fastapi import APIRouter, Query, Request

from numericos.api.deps import Context, Uow
from numericos.api.errors import CONFLICT_RESPONSES
from numericos.core.enums import AgentTask, TargetType
from numericos.core.schemas import (
    AnnotationCreate,
    AnnotationList,
    AnnotationOut,
    AnnotationPatch,
    AnnotationsSend,
    AnnotationsSent,
    ErrorEnvelope,
)
from numericos.services import comments

router = APIRouter()

SEND_RESPONSES: dict[int | str, dict[str, Any]] = {
    409: {
        "model": ErrorEnvelope,
        "description": (
            "The agent command is not installed, the project is not trusted for execution, "
            "or the agent is still answering the previous requests on this text"
        ),
    },
}


@router.get(
    "/annotations",
    tags=["annotations"],
    summary="The comments on one text, in the order of their passages",
)
def list_annotations(
    uow: Uow,
    target_type: TargetType,
    target_id: Annotated[str, Query(min_length=1, max_length=40)],
) -> AnnotationList:
    return comments.list_annotations(uow, target_type, target_id)


@router.post(
    "/annotations",
    status_code=201,
    tags=["annotations"],
    summary="Comment on a passage of an answer or of a document",
)
def create_annotation(body: AnnotationCreate, uow: Uow, context: Context) -> AnnotationOut:
    return comments.create_annotation(uow, body, context)


@router.post(
    "/annotations:clarify",
    status_code=202,
    tags=["annotations"],
    summary="Send every open clarification request on a text to the agent, in one turn",
    responses=SEND_RESPONSES,
)
def clarify_annotations(
    body: AnnotationsSend, uow: Uow, context: Context, request: Request
) -> AnnotationsSent:
    return comments.send(uow, AgentTask.CLARIFY, body, context, settings=request.app.state.settings)


@router.post(
    "/annotations:resolve",
    status_code=202,
    tags=["annotations"],
    summary="Send every open change request on a text to the agent, which edits the files",
    responses=SEND_RESPONSES,
)
def resolve_annotations(
    body: AnnotationsSend, uow: Uow, context: Context, request: Request
) -> AnnotationsSent:
    return comments.send(uow, AgentTask.RESOLVE, body, context, settings=request.app.state.settings)


@router.patch(
    "/annotations/{annotation_id}",
    tags=["annotations"],
    summary="Reword an open comment or change what it asks for (requires its version)",
    responses=CONFLICT_RESPONSES,
)
def update_annotation(
    annotation_id: str, body: AnnotationPatch, uow: Uow, context: Context
) -> AnnotationOut:
    return comments.update_annotation(uow, annotation_id, body, context)


@router.post(
    "/annotations/{annotation_id}:dismiss",
    tags=["annotations"],
    summary="Withdraw a comment; it is kept, dismissed",
)
def dismiss_annotation(annotation_id: str, uow: Uow, context: Context) -> AnnotationOut:
    return comments.dismiss_annotation(uow, annotation_id, context)
