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
from pathlib import Path
from typing import Any

from numericos.agents import claude_code, workspace
from numericos.agents import comments as agent_comments
from numericos.agents import documents as agent_documents
from numericos.agents.records import finished_payload
from numericos.config import Settings
from numericos.core.agents import AgentCapabilities
from numericos.core.enums import (
    ACTIVE_MESSAGE_STATUSES,
    AVAILABLE_TASKS,
    AgentProvider,
    AgentTask,
    EventType,
    MessageRole,
    MessageStatus,
    PermissionMode,
    Severity,
)
from numericos.core.errors import AgentUnavailableError, InvalidRequestError, SessionBusyError
from numericos.core.ids import new_id
from numericos.core.schemas import (
    AgentPolicyOut,
    AgentPolicyPut,
    AgentSessionCreate,
    AgentSessionList,
    AgentSessionOut,
    AgentSessionPatch,
    MessageCancel,
    MessageCreate,
    MessageList,
    MessageOut,
    MoveCreatedFiles,
    TaskPolicy,
    WorkspaceOut,
)
from numericos.events.ledger import EventContext, build_event
from numericos.persistence.engine import utcnow
from numericos.persistence.models import (
    AgentMessage,
    AgentPolicy,
    AgentSession,
    Event,
    Project,
)
from numericos.persistence.unit_of_work import UnitOfWork
from numericos.provenance import git
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
PATCHABLE = ("title", "permission_mode", "model", "effort")

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
        update={
            "available": True,
            "path": path,
            "version": lines[0] if lines else None,
            "models": list(claude_code.MODELS),
            "efforts": list(claude_code.EFFORTS),
        }
    )


def require_available(settings: Settings) -> AgentCapabilities:
    found = capabilities(settings)
    if not found.available:
        raise AgentUnavailableError(
            found.problem or "the agent command is not available",
            details={"command": found.command, "path": found.path},
        )
    return found


def _check_choice(
    found: AgentCapabilities, model: str | None, effort: str | None, where: list[str | int]
) -> None:
    """A model or effort must be one the provider offers; null is its default."""
    errors = []
    if model is not None and model not in {choice.id for choice in found.models}:
        errors.append(
            {
                "loc": [*where, "model"],
                "msg": f"not a model of {found.provider.value}: "
                f"{', '.join(choice.id for choice in found.models)}",
                "type": "unknown_model",
            }
        )
    if effort is not None and effort not in found.efforts:
        errors.append(
            {
                "loc": [*where, "effort"],
                "msg": f"not an effort level of {found.provider.value}: {', '.join(found.efforts)}",
                "type": "unknown_effort",
            }
        )
    if errors:
        raise InvalidRequestError(
            "the model or effort is not one the provider offers", details={"errors": errors}
        )


def _policy_out(project_id: str, row: AgentPolicy | None) -> AgentPolicyOut:
    # Until a policy is saved, the provider's suggestions are what turns are started with.
    stored = row.tasks if row is not None else claude_code.SUGGESTED_POLICY
    return AgentPolicyOut(
        project_id=project_id,
        provider=AgentProvider(row.provider) if row is not None else AgentProvider.CLAUDE_CODE,
        tasks={task: TaskPolicy.model_validate(stored.get(task.value) or {}) for task in AgentTask},
        available=sorted(AVAILABLE_TASKS, key=list(AgentTask).index),
        version=row.version if row is not None else 0,
        updated_at=row.updated_at if row is not None else None,
    )


def get_policy(uow: UnitOfWork, project_id: str) -> AgentPolicyOut:
    """The model and effort per task; the provider's defaults until something was saved."""
    with uow:
        project = require_project(uow, project_id)
        return _policy_out(project.id, uow.agent_policies.get(project.id))


def put_policy(
    uow: UnitOfWork,
    project_id: str,
    data: AgentPolicyPut,
    context: EventContext,
    *,
    settings: Settings,
) -> AgentPolicyOut:
    found = require_available(settings)
    for task, choice in data.tasks.items():
        _check_choice(found, choice.model, choice.effort, ["body", "tasks", task.value])
    # Stored in one shape for every task, so that saving the same choices again is a no-op.
    tasks = {
        task.value: data.tasks.get(task, TaskPolicy()).model_dump(mode="json") for task in AgentTask
    }
    now = utcnow()
    with uow:
        project = require_project(uow, project_id)
        row = uow.agent_policies.get(project.id)
        current = row.version if row is not None else 0
        check_version("agent_policy", project.id, current=current, provided=data.version)
        if row is None:
            row = uow.agent_policies.add(
                AgentPolicy(
                    project_id=project.id,
                    provider=found.provider.value,
                    tasks=tasks,
                    version=1,
                    created_at=now,
                    updated_at=now,
                )
            )
        else:
            if row.tasks == tasks:
                return _policy_out(project.id, row)
            row.tasks = tasks
            row.version += 1
            row.updated_at = now
        out = _policy_out(project.id, row)
        uow.record(
            build_event(
                event_type=EventType.AGENT_POLICY_UPDATED,
                project_id=project.id,
                subject_id=project.id,
                payload={"tasks": tasks, "version": row.version},
                context=context,
            )
        )
        uow.commit()
    return out


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
    found = require_available(settings)
    _check_choice(found, data.model, data.effort, ["body"])
    with uow:
        project = require_project(uow, project_id)
        root = require_trusted_root(project)
        session = open_session(
            uow,
            project,
            root,
            task=AgentTask.CONVERSATION,
            mode=data.permission_mode,
            title=data.title or DEFAULT_TITLE,
            context=context,
            model=data.model,
            effort=data.effort,
        )
        out = _session_out(session, 0)
        uow.commit()
    return out


def open_session(
    uow: UnitOfWork,
    project: Project,
    root: Path,
    *,
    task: AgentTask,
    mode: PermissionMode,
    title: str,
    context: EventContext,
    model: str | None = None,
    effort: str | None = None,
    target: tuple[str, str, int] | None = None,
) -> AgentSession:
    """Add a session of ``task`` to the open transaction, with its event. ``target`` is the
    text a Clarify or Resolve session is about: its type, ID and version."""
    now = utcnow()
    session = uow.agent_sessions.add(
        AgentSession(
            id=new_id("ases"),
            project_id=project.id,
            title=_excerpt(title, TITLE_MAX),
            provider=AgentProvider.CLAUDE_CODE.value,
            permission_mode=mode.value,
            task=task.value,
            model=model,
            effort=effort,
            target_type=target[0] if target else None,
            target_id=target[1] if target else None,
            target_version=target[2] if target else None,
            native_session_id=str(uuid.uuid4()),
            cwd=str(root),
            system_prompt=claude_code.system_prompt(project.name, project.research_question),
            version=1,
            created_at=now,
            updated_at=now,
        )
    )
    uow.record(
        build_event(
            event_type=EventType.AGENT_SESSION_STARTED,
            project_id=project.id,
            subject_id=session.id,
            payload={"session": _session_out(session, 0).model_dump(mode="json")},
            context=context,
        )
    )
    return session


def queue_turn(
    uow: UnitOfWork,
    session: AgentSession,
    content: str,
    context: EventContext,
    *,
    json_schema: dict[str, Any] | None = None,
) -> AgentMessage:
    """Add a prompt and the turn that answers it to the open transaction, with its event."""
    now = utcnow()
    prompt = uow.messages.add(
        _message(session, MessageRole.USER, MessageStatus.FINAL, content, context, now)
    )
    turn = uow.messages.add(
        _message(session, MessageRole.ASSISTANT, MessageStatus.QUEUED, "", context, now)
    )
    turn.prompt_message_id = prompt.id
    turn.json_schema = json_schema
    uow.record(
        build_event(
            event_type=EventType.AGENT_TURN_QUEUED,
            project_id=session.project_id,
            subject_id=turn.id,
            payload={
                "session_id": session.id,
                "task": session.task,
                "prompt_message_id": prompt.id,
                "prompt_excerpt": _excerpt(content, EXCERPT_MAX),
                "permission_mode": session.permission_mode,
            },
            context=context,
        )
    )
    return turn


def list_sessions(
    uow: UnitOfWork, project_id: str, task: AgentTask | None = AgentTask.CONVERSATION
) -> AgentSessionList:
    """The sessions of one task (the conversations, by default), or of all with ``None``."""
    with uow:
        project = require_project(uow, project_id)
        sessions = uow.agent_sessions.list_for_project(
            project.id, task.value if task is not None else None
        )
        counts = uow.messages.count_by_session([session.id for session in sessions])
        return AgentSessionList(
            sessions=[_session_out(session, counts.get(session.id, 0)) for session in sessions]
        )


def get_session(uow: UnitOfWork, session_id: str) -> AgentSessionOut:
    with uow:
        session = require_agent_session(uow, session_id)
        return _session_out(session, uow.messages.count_by_session([session.id]).get(session.id, 0))


def update_session(
    uow: UnitOfWork,
    session_id: str,
    patch: AgentSessionPatch,
    context: EventContext,
    *,
    settings: Settings,
) -> AgentSessionOut:
    if patch.model is not None or patch.effort is not None:
        _check_choice(require_available(settings), patch.model, patch.effort, ["body"])
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
    require_available(settings)
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
        turn = queue_turn(uow, session, data.content, context)
        if count == 0 and session.title == DEFAULT_TITLE:
            session.title = _excerpt(data.content, TITLE_MAX)
            session.version += 1
            session.updated_at = now
        out = MessageOut.model_validate(turn)
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
            project_id = message.project_id

            def make_event(
                event_type: EventType, subject: str, payload: dict[str, Any], severity: Severity
            ) -> Event:
                return build_event(
                    event_type=event_type,
                    project_id=project_id,
                    subject_id=subject,
                    payload=payload,
                    context=context,
                    severity=severity,
                )

            # No supervisor will end this turn: the documents it was to write and the comments
            # it was to answer are told here.
            agent_documents.complete(uow, message, cwd=Path("."), hashes={}, make_event=make_event)
            agent_comments.complete(uow, message, hashes={}, make_event=make_event)
        out = MessageOut.model_validate(message)
        uow.commit()
    return out


def get_workspace(uow: UnitOfWork, project_id: str, *, settings: Settings) -> WorkspaceOut:
    """Where everything NumericOS generates about a project is kept."""
    with uow:
        project = require_project(uow, project_id)
        root = require_trusted_root(project)
    folder = workspace.workspace_dir(settings, project.id, root)
    inside = workspace.inside(folder, root)
    return WorkspaceOut(
        path=str(folder),
        shown=workspace.shown(folder, root),
        inside_project=inside,
        exists=folder.is_dir(),
        # Outside the project Git never sees it; inside, its own .gitignore hides it.
        ignored_by_git=not inside or (folder / ".gitignore").is_file() or not folder.exists(),
    )


def move_created_files(
    uow: UnitOfWork,
    message_id: str,
    data: MoveCreatedFiles,
    context: EventContext,
    *,
    settings: Settings,
) -> MessageOut:
    """Move files a turn left in the repository to the NumericOS folder of the project. Only
    files the turn created, that are still there and that Git still does not track, are
    moved: a file that was committed since, or changed hands, is the project's own."""
    with uow:
        message = require_message(uow, message_id)
        project = require_project(uow, message.project_id)
        root = require_trusted_root(project)
        left = [path for path in message.files_created if path not in message.files_moved]
        wanted = data.paths if data.paths is not None else left
        unknown = sorted(set(wanted) - set(left))
        if unknown:
            raise InvalidRequestError(
                f"not files this turn left in the repository: {', '.join(unknown[:5])}",
                details={
                    "errors": [
                        {"loc": ["body", "paths"], "msg": "not created by this turn", "path": path}
                        for path in unknown[:50]
                    ]
                },
            )
    # Files are moved with no transaction open.
    folder = workspace.workspace_dir(settings, project.id, root)
    tracked = git.index_hashes(root)
    moved = workspace.move_out(
        root, folder, message.id, [path for path in wanted if path not in tracked]
    )
    with uow:
        message = require_message(uow, message_id)
        if not moved:
            return MessageOut.model_validate(message)
        message.files_moved = sorted({*message.files_moved, *moved})
        message.version += 1
        message.updated_at = utcnow()
        uow.record(
            build_event(
                event_type=EventType.AGENT_FILES_MOVED,
                project_id=message.project_id,
                subject_id=message.id,
                payload={
                    "paths": moved,
                    "destination": str(folder / workspace.MOVED / message.id),
                    "session_id": message.session_id,
                },
                context=context,
            )
        )
        out = MessageOut.model_validate(message)
        uow.commit()
    return out
