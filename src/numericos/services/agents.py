"""Conversations with a coding agent: sessions, prompts and the turns they queue.

The API never starts the agent. Sending a prompt records the user's message and queues the
agent's answer as a turn; a supervisor executes it and records what it observes. A session
serves one turn at a time, as the provider's sessions do.
"""

from __future__ import annotations

import shutil
import subprocess
import uuid
from datetime import datetime

from numericos.agents import claude_code
from numericos.agents.records import finished_payload
from numericos.config import Settings
from numericos.core.agents import AgentCapabilities
from numericos.core.enums import (
    ACTIVE_MESSAGE_STATUSES,
    AgentProvider,
    EventType,
    MessageRole,
    MessageStatus,
    PermissionMode,
    Severity,
)
from numericos.core.errors import AgentUnavailableError, SessionBusyError
from numericos.core.ids import new_id
from numericos.core.schemas import (
    AgentSessionCreate,
    AgentSessionList,
    AgentSessionOut,
    AgentSessionPatch,
    MessageCancel,
    MessageCreate,
    MessageList,
    MessageOut,
)
from numericos.events.ledger import EventContext, build_event
from numericos.persistence.engine import utcnow
from numericos.persistence.models import AgentMessage, AgentSession
from numericos.persistence.unit_of_work import UnitOfWork
from numericos.services.guards import (
    check_version,
    require_agent_session,
    require_message,
    require_project,
    require_trusted_root,
)

ACTIVE = tuple(status.value for status in ACTIVE_MESSAGE_STATUSES)
DEFAULT_TITLE = "New conversation"
TITLE_MAX = 200
EXCERPT_MAX = 120
PATCHABLE = ("title", "permission_mode", "model")

#: Probes that succeeded; a missing command is asked about again, it may get installed.
_probed: dict[tuple[str, ...], AgentCapabilities] = {}


def capabilities(settings: Settings) -> AgentCapabilities:
    """Whether the agent command can be started here, found by running it."""
    command = tuple(settings.claude_command)
    known = _probed.get(command)
    if known is not None:
        return known
    found = _probe(command)
    if found.available:
        _probed[command] = found
    return found


def _probe(command: tuple[str, ...]) -> AgentCapabilities:
    base = AgentCapabilities(
        provider=AgentProvider.CLAUDE_CODE, command=list(command), available=False
    )
    path = shutil.which(command[0])
    if path is None:
        return base.model_copy(
            update={
                "problem": (
                    f"{command[0]!r} was not found on the PATH of the NumericOS processes. "
                    "Install Claude Code, or set NUMERICOS_CLAUDE_COMMAND to its command."
                )
            }
        )
    try:
        completed = subprocess.run(
            [*command, "--version"], capture_output=True, text=True, timeout=20, check=False
        )
    except (OSError, subprocess.TimeoutExpired) as error:
        return base.model_copy(update={"path": path, "problem": f"`--version` failed: {error}"})
    if completed.returncode != 0:
        said = (completed.stderr or completed.stdout).strip().splitlines()
        return base.model_copy(
            update={
                "path": path,
                "problem": (
                    f"`--version` exited with {completed.returncode}: "
                    f"{said[-1] if said else 'no message'}"
                ),
            }
        )
    lines = completed.stdout.strip().splitlines()
    return base.model_copy(
        update={"available": True, "path": path, "version": lines[0] if lines else None}
    )


def _require_available(settings: Settings) -> None:
    found = capabilities(settings)
    if not found.available:
        raise AgentUnavailableError(
            found.problem or "the agent command is not available",
            details={"command": found.command, "path": found.path},
        )


def _excerpt(text: str, limit: int) -> str:
    line = " ".join(text.split())
    return line if len(line) <= limit else line[: limit - 1] + "…"


def _session_out(session: AgentSession, message_count: int) -> AgentSessionOut:
    out = AgentSessionOut.model_validate(session)
    return out.model_copy(update={"message_count": message_count})


def create_session(
    uow: UnitOfWork,
    project_id: str,
    data: AgentSessionCreate,
    context: EventContext,
    *,
    settings: Settings,
) -> AgentSessionOut:
    """Open a conversation. The agent will work in the project's trusted directory."""
    _require_available(settings)
    now = utcnow()
    with uow:
        project = require_project(uow, project_id)
        root = require_trusted_root(project)
        session = uow.agent_sessions.add(
            AgentSession(
                id=new_id("ases"),
                project_id=project.id,
                title=data.title or DEFAULT_TITLE,
                provider=AgentProvider.CLAUDE_CODE.value,
                permission_mode=data.permission_mode.value,
                model=data.model,
                native_session_id=str(uuid.uuid4()),
                cwd=str(root),
                system_prompt=claude_code.system_prompt(project.name, project.research_question),
                version=1,
                created_at=now,
                updated_at=now,
            )
        )
        out = _session_out(session, 0)
        uow.record(
            build_event(
                event_type=EventType.AGENT_SESSION_STARTED,
                project_id=project.id,
                subject_id=session.id,
                payload={"session": out.model_dump(mode="json")},
                context=context,
            )
        )
        uow.commit()
    return out


def list_sessions(uow: UnitOfWork, project_id: str) -> AgentSessionList:
    with uow:
        project = require_project(uow, project_id)
        sessions = uow.agent_sessions.list_for_project(project.id)
        counts = uow.messages.count_by_session([session.id for session in sessions])
        return AgentSessionList(
            sessions=[_session_out(session, counts.get(session.id, 0)) for session in sessions]
        )


def get_session(uow: UnitOfWork, session_id: str) -> AgentSessionOut:
    with uow:
        session = require_agent_session(uow, session_id)
        return _session_out(session, uow.messages.count_by_session([session.id]).get(session.id, 0))


def update_session(
    uow: UnitOfWork, session_id: str, patch: AgentSessionPatch, context: EventContext
) -> AgentSessionOut:
    with uow:
        session = require_agent_session(uow, session_id)
        check_version("agent_session", session.id, current=session.version, provided=patch.version)
        changed = [
            field
            for field in PATCHABLE
            if field in patch.model_fields_set and getattr(session, field) != _value(patch, field)
        ]
        count = uow.messages.count_by_session([session.id]).get(session.id, 0)
        if not changed:
            return _session_out(session, count)
        for field in changed:
            setattr(session, field, _value(patch, field))
        session.version += 1
        session.updated_at = utcnow()
        out = _session_out(session, count)
        uow.record(
            build_event(
                event_type=EventType.AGENT_SESSION_UPDATED,
                project_id=session.project_id,
                subject_id=session.id,
                payload={"changed_fields": changed, "session": out.model_dump(mode="json")},
                context=context,
            )
        )
        uow.commit()
    return out


def _value(patch: AgentSessionPatch, field: str) -> str | None:
    value = getattr(patch, field)
    return value.value if isinstance(value, PermissionMode) else value


def send_message(
    uow: UnitOfWork,
    session_id: str,
    data: MessageCreate,
    context: EventContext,
    *,
    settings: Settings,
) -> MessageOut:
    """Record the prompt and queue the agent's turn. Returns the queued assistant message."""
    _require_available(settings)
    now = utcnow()
    with uow:
        session = require_agent_session(uow, session_id)
        busy = uow.messages.active_in_session(session.id, ACTIVE)
        if busy is not None:
            raise SessionBusyError(
                f"session {session.id} is still answering; wait for message {busy.id} to end",
                details={"session_id": session.id, "message_id": busy.id, "status": busy.status},
            )
        count = uow.messages.count_by_session([session.id]).get(session.id, 0)
        prompt = uow.messages.add(
            _message(session, MessageRole.USER, MessageStatus.FINAL, data.content, context, now)
        )
        turn = uow.messages.add(
            _message(session, MessageRole.ASSISTANT, MessageStatus.QUEUED, "", context, now)
        )
        turn.prompt_message_id = prompt.id
        if count == 0 and session.title == DEFAULT_TITLE:
            session.title = _excerpt(data.content, TITLE_MAX)
            session.version += 1
            session.updated_at = now
        out = MessageOut.model_validate(turn)
        uow.record(
            build_event(
                event_type=EventType.AGENT_TURN_QUEUED,
                project_id=session.project_id,
                subject_id=turn.id,
                payload={
                    "session_id": session.id,
                    "prompt_message_id": prompt.id,
                    "prompt_excerpt": _excerpt(data.content, EXCERPT_MAX),
                    "permission_mode": session.permission_mode,
                },
                context=context,
            )
        )
        uow.commit()
    return out


def _message(
    session: AgentSession,
    role: MessageRole,
    status: MessageStatus,
    markdown: str,
    context: EventContext,
    now: datetime,
) -> AgentMessage:
    return AgentMessage(
        id=new_id("msg"),
        session_id=session.id,
        project_id=session.project_id,
        role=role.value,
        status=status.value,
        markdown=markdown,
        correlation_id=context.correlation_id,
        activity=[],
        activity_dropped=0,
        files_read=[],
        files_written=[],
        permission_denials=[],
        version=1,
        created_at=now,
        updated_at=now,
    )


def list_messages(uow: UnitOfWork, session_id: str) -> MessageList:
    with uow:
        session = require_agent_session(uow, session_id)
        return MessageList(
            messages=[
                MessageOut.model_validate(item)
                for item in uow.messages.list_for_session(session.id)
            ]
        )


def get_message(uow: UnitOfWork, message_id: str) -> MessageOut:
    with uow:
        return MessageOut.model_validate(require_message(uow, message_id))


def cancel_message(
    uow: UnitOfWork, message_id: str, body: MessageCancel, context: EventContext
) -> MessageOut:
    """Ask for a turn to be stopped.

    A queued turn is cancelled at once. For a running one the intent is recorded; the
    supervisor stops the agent process and the message becomes ``cancelled`` when it is gone.
    Cancelling a message that already ended, or a user message, changes nothing.
    """
    reason = body.reason or "cancelled on request"
    with uow:
        message = require_message(uow, message_id)
        if message.status not in ACTIVE or message.cancel_requested_at is not None:
            return MessageOut.model_validate(message)
        now = utcnow()
        message.cancel_requested_at = now
        message.cancel_reason = reason
        message.updated_at = now
        message.version += 1
        uow.record(
            build_event(
                event_type=EventType.AGENT_TURN_CANCEL_REQUESTED,
                project_id=message.project_id,
                subject_id=message.id,
                payload={"reason": reason, "status_when_requested": message.status},
                context=context,
                severity=Severity.WARNING,
            )
        )
        if message.status == MessageStatus.QUEUED.value and message.worker_id is None:
            message.status = MessageStatus.CANCELLED.value
            message.status_reason = reason
            message.finished_at = now
            uow.record(
                build_event(
                    event_type=EventType.AGENT_TURN_FINISHED,
                    project_id=message.project_id,
                    subject_id=message.id,
                    payload=finished_payload(message),
                    context=context,
                    severity=Severity.WARNING,
                )
            )
        out = MessageOut.model_validate(message)
        uow.commit()
    return out
