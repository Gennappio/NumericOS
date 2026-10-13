"""Turning the answer of a Clarify or Resolve turn into what the comments say.

A request marks its comments with the turn that answers them (``pending_message_id``). When
the turn ends, whoever ends it calls ``complete`` in the same transaction: a clarification
takes its answer, a change request takes the agent's decision and what it did, and a text the
agent rewrote becomes the new version of its document, with every comment looked for again in
it. A comment the turn did not answer is open again, and says why.
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import datetime
from pathlib import Path
from typing import Any

from numericos.agents.anchoring import reanchor
from numericos.agents.documents import build_pipeline, first_heading, put_pipeline, sources_of
from numericos.core.enums import (
    AgentTask,
    AnnotationStatus,
    DocumentKind,
    EventType,
    MessageStatus,
    Severity,
    TargetType,
)
from numericos.core.formulas import repair_formulas
from numericos.persistence.engine import utcnow
from numericos.persistence.models import AgentMessage, Annotation, Event
from numericos.persistence.unit_of_work import UnitOfWork

MakeEvent = Callable[[EventType, str, dict[str, Any], Severity], Event]

REASON_MAX = 300
NO_ANSWER = "the agent gave no answer to this request"
DECISIONS = {
    "applied": AnnotationStatus.RESOLVED,
    "declined": AnnotationStatus.DECLINED,
}


def _clip(text: str) -> str:
    line = " ".join(text.split())
    return line if len(line) <= REASON_MAX else line[: REASON_MAX - 1] + "…"


def source_paths(uow: UnitOfWork, message_id: str) -> list[str]:
    """The files the documents this turn may rewrite were written from: their hashes are
    needed when the turn ends, to say what the rewritten text is current with."""
    paths: list[str] = []
    for annotation in uow.annotations.pending_for_message(message_id):
        if annotation.target_type != TargetType.DOCUMENT.value:
            continue
        document = uow.documents.get(annotation.target_id)
        for source in document.sources if document is not None else []:
            if source["path"] not in paths:
                paths.append(source["path"])
    return paths


def _reopen(annotation: Annotation, reason: str, now: datetime) -> None:
    annotation.status = AnnotationStatus.OPEN.value
    annotation.status_reason = _clip(reason)
    annotation.pending_message_id = None
    annotation.version += 1
    annotation.updated_at = now


def _answer(
    annotation: Annotation,
    status: AnnotationStatus,
    markdown: str,
    message: AgentMessage,
    now: datetime,
) -> None:
    annotation.status = status.value
    annotation.status_reason = None
    # The answer came inside JSON: a formula escaped once too often is as it was meant.
    annotation.response_markdown = repair_formulas(markdown)
    annotation.message_id = message.id
    annotation.pending_message_id = None
    annotation.responded_at = now
    annotation.version += 1
    annotation.updated_at = now


def _entries(answer: Any, key: str) -> dict[str, dict[str, Any]] | None:
    items = answer.get(key) if isinstance(answer, dict) else None
    if not isinstance(items, list):
        return None
    return {str(item.get("id")): item for item in items if isinstance(item, dict)}


def complete(
    uow: UnitOfWork,
    message: AgentMessage,
    *,
    cwd: Path,
    hashes: dict[str, str | None],
    make_event: MakeEvent,
) -> None:
    """Give the comments this turn was answering what it answered. ``hashes`` are the content
    hashes, taken when the turn ended, of the files it read, wrote or named and of the files
    the text was written from."""
    pending = uow.annotations.pending_for_message(message.id)
    if not pending:
        return
    session = uow.agent_sessions.get(message.session_id)
    task = AgentTask(session.task) if session is not None else AgentTask.CLARIFY
    now = utcnow()
    reopened: dict[str, str] = {}
    details: dict[str, Any] = {}

    if message.status != MessageStatus.FINAL.value:
        said = f": {message.status_reason}" if message.status_reason else ""
        reopened = dict.fromkeys(
            (annotation.id for annotation in pending),
            f"the agent's turn ended {message.status}{said}",
        )
    elif task is AgentTask.CLARIFY:
        answers = _entries(message.structured_output, "answers") or {}
        for annotation in pending:
            text = str(answers.get(annotation.id, {}).get("markdown", "")).strip()
            if text:
                _answer(annotation, AnnotationStatus.ANSWERED, text, message, now)
            else:
                reopened[annotation.id] = NO_ANSWER
    else:
        results = _entries(message.structured_output, "results") or {}
        for annotation in pending:
            result = results.get(annotation.id, {})
            status = DECISIONS.get(str(result.get("decision")))
            if status is None:
                reopened[annotation.id] = NO_ANSWER
            else:
                summary = str(result.get("summary", "")).strip()
                _answer(annotation, status, summary, message, now)
        details = _rewrite(uow, pending[0], message, cwd, hashes, now)

    for annotation in pending:
        if annotation.id in reopened:
            _reopen(annotation, reopened[annotation.id], now)
    answered = [annotation.id for annotation in pending if annotation.id not in reopened]
    uow.record(
        make_event(
            EventType.ANNOTATIONS_ANSWERED,
            message.id,
            {
                "task": task.value,
                "target_type": pending[0].target_type,
                "target_id": pending[0].target_id,
                "answered": answered,
                "reopened": reopened,
                "applied": sum(a.status == AnnotationStatus.RESOLVED.value for a in pending),
                "declined": sum(a.status == AnnotationStatus.DECLINED.value for a in pending),
                "message_id": message.id,
                "session_id": message.session_id,
                **details,
            },
            Severity.ERROR if reopened and not answered else Severity.INFO,
        )
    )


def _rewrite(
    uow: UnitOfWork,
    annotation: Annotation,
    message: AgentMessage,
    cwd: Path,
    hashes: dict[str, str | None],
    now: datetime,
) -> dict[str, Any]:
    """If the agent gave a revised text for a document, make it the document's new version
    and look for every comment of the document again in it. A pipeline is revised as boxes
    and arrows, from which its text is put together again."""
    answer = message.structured_output if isinstance(message.structured_output, dict) else {}
    document = (
        uow.documents.get(annotation.target_id)
        if annotation.target_type == TargetType.DOCUMENT.value
        else None
    )
    if document is None:
        return {}
    # What the new text is current with: the files it was written from before, and the files
    # this turn read or changed, as they are now. A file that is gone is no source any more.
    paths = [
        *(source["path"] for source in document.sources),
        *(message.files_read or []),
        *(message.files_written or []),
    ]
    if document.kind == DocumentKind.PIPELINE.value:
        if not isinstance(answer.get("pipeline"), dict):
            return {}
        built = build_pipeline(answer["pipeline"], cwd)
        if isinstance(built, str):
            return {"revision_not_used": built}
        if built.markdown == document.markdown and built.structure == document.pipeline:
            return {}
        put_pipeline(document, built, paths, hashes)
    else:
        revised = answer.get("document")
        text = revised.strip() if isinstance(revised, str) else ""
        if not text or text == document.markdown.strip():
            return {}
        document.markdown = text
        document.title = first_heading(text) or document.title
        document.sources = sources_of(paths, hashes)
    document.message_id = message.id
    document.model = message.model
    document.generated_at = now
    document.version += 1
    document.updated_at = now
    attached, detached = reanchor(
        uow, TargetType.DOCUMENT, document.id, document.markdown, document.version
    )
    return {
        "document_id": document.id,
        "document_version": document.version,
        "comments_attached": attached,
        "comments_detached": detached,
    }
