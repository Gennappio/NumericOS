"""Conversations with the coding agent: sessions, prompts, turns and their observation."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Request

from numericos.api.deps import Context, Uow
from numericos.api.errors import CONFLICT_RESPONSES
from numericos.core.agents import AgentCapabilities
from numericos.core.schemas import (
    AgentSessionCreate,
    AgentSessionList,
    AgentSessionOut,
    AgentSessionPatch,
    ErrorEnvelope,
    MessageCancel,
    MessageCreate,
    MessageList,
    MessageOut,
)
from numericos.services import agents

router = APIRouter()

UNAVAILABLE_RESPONSES: dict[int | str, dict[str, Any]] = {
    409: {
        "model": ErrorEnvelope,
        "description": (
            "The agent command is not installed, the project is not trusted for execution, "
            "or the session is still answering"
        ),
    },
}


@router.get(
    "/agents/capabilities",
    tags=["agents"],
    summary="Whether the coding agent can be started where NumericOS runs",
)
def agent_capabilities(request: Request) -> AgentCapabilities:
    return agents.capabilities(request.app.state.settings)


@router.post(
    "/projects/{project_id}/agent-sessions",
    status_code=201,
    tags=["agents"],
    summary="Open a conversation with the agent about a project",
    responses=UNAVAILABLE_RESPONSES,
)
def create_agent_session(
    project_id: str, body: AgentSessionCreate, uow: Uow, context: Context, request: Request
) -> AgentSessionOut:
    return agents.create_session(
        uow, project_id, body, context, settings=request.app.state.settings
    )


@router.get(
    "/projects/{project_id}/agent-sessions",
    tags=["agents"],
    summary="List a project's conversations, newest first",
)
def list_agent_sessions(project_id: str, uow: Uow) -> AgentSessionList:
    return agents.list_sessions(uow, project_id)


@router.get("/agent-sessions/{session_id}", tags=["agents"], summary="Get one conversation")
def get_agent_session(session_id: str, uow: Uow) -> AgentSessionOut:
    return agents.get_session(uow, session_id)


@router.patch(
    "/agent-sessions/{session_id}",
    tags=["agents"],
    summary="Rename a conversation or change its permission mode (requires its version)",
    responses=CONFLICT_RESPONSES,
)
def update_agent_session(
    session_id: str, body: AgentSessionPatch, uow: Uow, context: Context
) -> AgentSessionOut:
    return agents.update_session(uow, session_id, body, context)


@router.post(
    "/agent-sessions/{session_id}/messages",
    status_code=201,
    tags=["agents"],
    summary="Send a prompt; the agent's answer is queued as a turn for a supervisor",
    responses=UNAVAILABLE_RESPONSES,
)
def send_message(
    session_id: str, body: MessageCreate, uow: Uow, context: Context, request: Request
) -> MessageOut:
    return agents.send_message(uow, session_id, body, context, settings=request.app.state.settings)


@router.get(
    "/agent-sessions/{session_id}/messages",
    tags=["agents"],
    summary="The messages of a conversation in order",
)
def list_messages(session_id: str, uow: Uow) -> MessageList:
    return agents.list_messages(uow, session_id)


@router.get("/messages/{message_id}", tags=["agents"], summary="Get one message")
def get_message(message_id: str, uow: Uow) -> MessageOut:
    return agents.get_message(uow, message_id)


@router.post(
    "/messages/{message_id}:cancel",
    tags=["agents"],
    summary="Ask for a turn to be stopped; returns at once",
)
def cancel_message(
    message_id: str, uow: Uow, context: Context, body: MessageCancel | None = None
) -> MessageOut:
    return agents.cancel_message(uow, message_id, body or MessageCancel(), context)
