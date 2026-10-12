"""Comments on what the agent wrote, and sending them to the agent.

A comment is attached to a passage of an answer or of a document. **Clarify** sends every
open clarification request on a text to the agent in one turn; each answer is kept on its
comment and shown next to its passage, and the text itself is not touched. **Resolve** sends
every open change request in one turn, in which the agent edits the files of the project
directly, decides what to do with requests that conflict, and may give a revised text.
Neither grows a conversation: each text has a session of its own for them.
"""

from __future__ import annotations

from numericos.agents import prompts, targets
from numericos.config import Settings
from numericos.core.anchors import Located, context, locate
from numericos.core.enums import (
    ACTIVE_MESSAGE_STATUSES,
    AgentTask,
    AnchorState,
    AnnotationKind,
    AnnotationStatus,
    EventType,
    PermissionMode,
    TargetType,
)
from numericos.core.errors import InvalidRequestError, NotFoundError, SessionBusyError
from numericos.core.ids import new_id
from numericos.core.schemas import (
    AnnotationCreate,
    AnnotationList,
    AnnotationOut,
    AnnotationPatch,
    AnnotationsSend,
    AnnotationsSent,
)
from numericos.events.ledger import EventContext, build_event
from numericos.persistence.engine import utcnow
from numericos.persistence.models import Annotation
from numericos.persistence.unit_of_work import UnitOfWork
from numericos.services import agents
from numericos.services.guards import check_version, require_project, require_trusted_root

ACTIVE = tuple(status.value for status in ACTIVE_MESSAGE_STATUSES)
KIND_OF_TASK = {
    AgentTask.CLARIFY: AnnotationKind.CLARIFICATION,
    AgentTask.RESOLVE: AnnotationKind.CHANGE,
}
PATCHABLE = ("body", "kind")


def _invalid(message: str, kind: str, **details: object) -> InvalidRequestError:
    return InvalidRequestError(
        message, details={"errors": [{"loc": ["body"], "msg": message, "type": kind}], **details}
    )


def _require_target(uow: UnitOfWork, target_type: TargetType, target_id: str) -> targets.Target:
    target = targets.load(uow, target_type, target_id)
    if target is None:
        raise NotFoundError(
            f"{target_type.value} {target_id} not found",
            details={"resource": target_type.value, "id": target_id},
        )
    return target


def _require_annotation(uow: UnitOfWork, annotation_id: str) -> Annotation:
    annotation = uow.annotations.get(annotation_id)
    if annotation is None:
        raise NotFoundError(
            f"comment {annotation_id} not found",
            details={"resource": "annotation", "id": annotation_id},
        )
    return annotation


def _event(
    uow: UnitOfWork,
    event_type: EventType,
    annotation: Annotation,
    context_: EventContext,
    **payload: object,
) -> None:
    out = AnnotationOut.model_validate(annotation)
    uow.record(
        build_event(
            event_type=event_type,
            project_id=annotation.project_id,
            subject_id=annotation.id,
            # The passage and the answer can be long: the ledger keeps what identifies them.
            payload={
                "annotation": out.model_dump(
                    mode="json", exclude={"prefix", "suffix", "response_markdown"}
                ),
                **payload,
            },
            context=context_,
        )
    )


def list_annotations(uow: UnitOfWork, target_type: TargetType, target_id: str) -> AnnotationList:
    with uow:
        target = _require_target(uow, target_type, target_id)
        found = uow.annotations.list_for_target(target_type.value, target.id)
        pending_id = next(
            (a.pending_message_id for a in found if a.pending_message_id is not None), None
        )
        turn = uow.messages.get(pending_id) if pending_id is not None else None
        return AnnotationList(
            annotations=[AnnotationOut.model_validate(annotation) for annotation in found],
            target_version=target.version,
            pending_message_id=turn.id if turn is not None else None,
            pending_session_id=turn.session_id if turn is not None else None,
        )


def create_annotation(
    uow: UnitOfWork, data: AnnotationCreate, context_: EventContext
) -> AnnotationOut:
    """Attach a comment to a passage. The passage must be exactly where the request says it
    is, or occur exactly once: a comment is never attached to a place by guessing."""
    now = utcnow()
    with uow:
        target = _require_target(uow, data.target_type, data.target_id)
        if not target.ready:
            raise _invalid(
                "the text is still being written: it can be commented when it is final",
                "target_not_ready",
            )
        if data.start_offset is not None and data.end_offset is not None:
            start, end = data.start_offset, data.end_offset
            if end > len(target.markdown) or target.markdown[start:end] != data.quote:
                raise _invalid(
                    "the passage is not at these offsets in the current text: "
                    "read the text again and select the passage anew",
                    "anchor_mismatch",
                    target_version=target.version,
                )
        else:
            found = locate(target.markdown, data.quote)
            if not isinstance(found, Located):
                raise _invalid(
                    "the passage is not in the text"
                    if found.reason == "missing"
                    else "the passage occurs more than once: give its offsets",
                    f"quote_{found.reason}",
                    target_version=target.version,
                )
            start, end = found.start, found.end
        prefix, suffix = context(target.markdown, start, end)
        annotation = uow.annotations.add(
            Annotation(
                id=new_id("ann"),
                project_id=target.project_id,
                target_type=target.type.value,
                target_id=target.id,
                target_version=target.version,
                kind=data.kind.value,
                status=AnnotationStatus.OPEN.value,
                body=data.body.strip(),
                start_offset=start,
                end_offset=end,
                quote=data.quote,
                prefix=prefix,
                suffix=suffix,
                anchor_state=AnchorState.ATTACHED.value,
                version=1,
                created_at=now,
                updated_at=now,
            )
        )
        _event(uow, EventType.ANNOTATION_CREATED, annotation, context_)
        out = AnnotationOut.model_validate(annotation)
        uow.commit()
    return out


def _require_open(annotation: Annotation) -> None:
    if annotation.status != AnnotationStatus.OPEN.value:
        raise _invalid(
            f"the comment is {annotation.status}: only an open comment can be changed",
            "annotation_not_open",
        )


def update_annotation(
    uow: UnitOfWork, annotation_id: str, patch: AnnotationPatch, context_: EventContext
) -> AnnotationOut:
    """Reword an open comment or change what it asks for."""
    with uow:
        annotation = _require_annotation(uow, annotation_id)
        check_version(
            "annotation", annotation.id, current=annotation.version, provided=patch.version
        )
        _require_open(annotation)
        wanted = {
            "body": patch.body.strip() if patch.body is not None else None,
            "kind": patch.kind.value if patch.kind is not None else None,
        }
        changed = [
            name
            for name in PATCHABLE
            if wanted[name] is not None and getattr(annotation, name) != wanted[name]
        ]
        if not changed:
            return AnnotationOut.model_validate(annotation)
        for name in changed:
            setattr(annotation, name, wanted[name])
        if annotation.kind != AnnotationKind.NOTE.value and not annotation.body:
            raise _invalid("say what you ask about the passage", "empty_request")
        annotation.version += 1
        annotation.updated_at = utcnow()
        _event(uow, EventType.ANNOTATION_UPDATED, annotation, context_, changed_fields=changed)
        out = AnnotationOut.model_validate(annotation)
        uow.commit()
    return out


def dismiss_annotation(
    uow: UnitOfWork, annotation_id: str, context_: EventContext
) -> AnnotationOut:
    """Withdraw a comment. It is kept, dismissed; one that the agent is answering cannot be
    withdrawn until its turn ends."""
    with uow:
        annotation = _require_annotation(uow, annotation_id)
        if annotation.status == AnnotationStatus.DISMISSED.value:
            return AnnotationOut.model_validate(annotation)
        if annotation.status == AnnotationStatus.PENDING.value:
            raise _invalid(
                "the agent is answering this comment: stop its turn first", "annotation_pending"
            )
        annotation.status = AnnotationStatus.DISMISSED.value
        annotation.version += 1
        annotation.updated_at = utcnow()
        _event(uow, EventType.ANNOTATION_UPDATED, annotation, context_, changed_fields=["status"])
        out = AnnotationOut.model_validate(annotation)
        uow.commit()
    return out


def send(
    uow: UnitOfWork,
    task: AgentTask,
    data: AnnotationsSend,
    context_: EventContext,
    *,
    settings: Settings,
) -> AnnotationsSent:
    """Clarify or Resolve: one turn of the agent for every open request of that kind on the
    text whose passage is still in it."""
    agents.require_available(settings)
    kind = KIND_OF_TASK[task]
    mode = PermissionMode.READ_ONLY if task is AgentTask.CLARIFY else data.permission_mode
    if task is AgentTask.RESOLVE and mode is PermissionMode.READ_ONLY:
        raise _invalid("a change cannot be made in read-only mode", "read_only_resolve")
    with uow:
        target = _require_target(uow, data.target_type, data.target_id)
        project = require_project(uow, target.project_id)
        root = require_trusted_root(project)
        chosen = [
            annotation
            for annotation in uow.annotations.list_for_target(target.type.value, target.id)
            if annotation.kind == kind.value
            and annotation.status == AnnotationStatus.OPEN.value
            and annotation.anchor_state == AnchorState.ATTACHED.value
        ]
        if not chosen:
            raise _invalid(
                f"there is no open {kind.value} request attached to this text", "nothing_to_send"
            )
        session = uow.agent_sessions.latest_for_target(
            task.value, target.type.value, target.id, target.version
        )
        first = session is None
        if session is None:
            session = agents.open_session(
                uow,
                project,
                root,
                task=task,
                mode=mode,
                title=f"{'Clarify' if task is AgentTask.CLARIFY else 'Resolve'}: {target.title}",
                context=context_,
                target=(target.type.value, target.id, target.version),
            )
        else:
            busy = uow.messages.active_in_session(session.id, ACTIVE)
            if busy is not None:
                raise SessionBusyError(
                    "the agent is still answering the previous requests on this text",
                    details={"session_id": session.id, "message_id": busy.id},
                )
            session.permission_mode = mode.value
        items = [
            {
                "id": annotation.id,
                "quote": annotation.quote,
                "prefix": annotation.prefix,
                "suffix": annotation.suffix,
                "body": annotation.body,
            }
            for annotation in chosen
        ]
        shared = {
            "what": target.what,
            "title": target.title,
            "markdown": target.markdown,
            "question": target.question,
            "items": items,
            "first": first,
            "instructions": data.instructions or "",
        }
        if task is AgentTask.CLARIFY:
            prompt, schema = prompts.clarify(**shared), prompts.CLARIFY_SCHEMA  # type: ignore[arg-type]
        else:
            prompt = prompts.resolve(**shared, rewritable=target.rewritable)  # type: ignore[arg-type]
            schema = prompts.RESOLVE_SCHEMA
        turn = agents.queue_turn(uow, session, prompt, context_, json_schema=schema)
        now = utcnow()
        for annotation in chosen:
            annotation.status = AnnotationStatus.PENDING.value
            annotation.status_reason = None
            annotation.pending_message_id = turn.id
            annotation.version += 1
            annotation.updated_at = now
        uow.record(
            build_event(
                event_type=EventType.ANNOTATIONS_SENT,
                project_id=project.id,
                subject_id=turn.id,
                payload={
                    "task": task.value,
                    "target_type": target.type.value,
                    "target_id": target.id,
                    "annotation_ids": [annotation.id for annotation in chosen],
                    "permission_mode": mode.value,
                    "message_id": turn.id,
                    "session_id": session.id,
                },
                context=context_,
            )
        )
        sent = AnnotationsSent(queued=len(chosen), message_id=turn.id, session_id=session.id)
        uow.commit()
    return sent
