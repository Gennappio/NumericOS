"""Turning the answer of a turn into the documents it was asked to write.

A generation request marks its documents with the turn that writes them
(``pending_message_id``). When the turn ends, whoever ends it (the supervisor, or the API for
a turn cancelled before it started) calls ``complete`` in the same transaction: the documents
take the answer, or say why they could not. A plan is applied to the board here as well.
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import datetime
from pathlib import Path
from typing import Any

from numericos.agents import pipeline
from numericos.agents.anchoring import reanchor
from numericos.core.enums import (
    CardOrigin,
    CardType,
    DocumentKind,
    DocumentStatus,
    EventType,
    FileCategory,
    MessageStatus,
    Severity,
    TargetType,
    WorkflowStatus,
)
from numericos.core.formulas import repair_formulas
from numericos.core.ids import new_id
from numericos.core.schemas import CardOut
from numericos.persistence.engine import utcnow
from numericos.persistence.models import AgentMessage, BoardCard, Document, Event
from numericos.persistence.unit_of_work import UnitOfWork

#: Builds a ledger event of the turn's project: type, subject, payload, severity.
MakeEvent = Callable[[EventType, str, dict[str, Any], Severity], Event]

REASON_MAX = 300
SUMMARY_MAX = 400
TITLE_MAX = 300
NO_STRUCTURE = pipeline.NO_STRUCTURE


def _clip(text: str, limit: int) -> str:
    line = " ".join(text.split())
    return line if len(line) <= limit else line[: limit - 1] + "…"


def relative_path(raw: str, cwd: Path) -> str:
    """A path as the agent gave it, relative to the project directory where it lies inside."""
    path = Path(raw)
    if path.is_absolute():
        for base in (cwd, cwd.resolve()):
            try:
                return path.relative_to(base).as_posix()
            except ValueError:
                continue
        return raw
    return Path(raw).as_posix().removeprefix("./")


def first_heading(markdown: str) -> str | None:
    for line in markdown.splitlines():
        if line.startswith("# "):
            return _clip(line[2:], TITLE_MAX)
    return None


def _fail(document: Document, reason: str, now: datetime) -> None:
    """The turn wrote nothing for this document. Content from an earlier turn stays."""
    document.pending_message_id = None
    document.status_reason = _clip(reason, REASON_MAX)
    document.status = (
        DocumentStatus.READY if document.message_id is not None else DocumentStatus.FAILED
    ).value
    document.updated_at = now


def _fill(document: Document, message: AgentMessage, now: datetime) -> None:
    document.pending_message_id = None
    document.message_id = message.id
    document.session_id = message.session_id
    document.status = DocumentStatus.READY.value
    document.status_reason = None
    document.model = message.model
    document.generated_at = now
    document.version += 1
    document.updated_at = now


def complete(
    uow: UnitOfWork,
    message: AgentMessage,
    *,
    cwd: Path,
    hashes: dict[str, str | None],
    make_event: MakeEvent,
) -> None:
    """Give the documents this turn was writing what it wrote. ``hashes`` are the content
    hashes of the files the agent read, taken when the turn ended."""
    documents = uow.documents.pending_for_message(message.id)
    if not documents:
        return
    now = utcnow()
    kind = DocumentKind(documents[0].kind)
    failed: dict[str, str] = {}
    details: dict[str, Any] = {}

    if message.status != MessageStatus.FINAL.value:
        said = f": {message.status_reason}" if message.status_reason else ""
        failed = dict.fromkeys(
            (document.key for document in documents),
            f"the agent's turn ended {message.status}{said}",
        )
    elif kind is DocumentKind.THEORY:
        failed = _complete_theory(documents[0], message, hashes, now)
    elif kind is DocumentKind.FILE_DESCRIPTION:
        failed = _complete_files(documents, message, cwd, now)
    elif kind is DocumentKind.PIPELINE:
        failed, details = _complete_pipeline(documents[0], message, cwd, hashes, now)
    else:
        failed, details = _complete_plan(uow, documents[0], message, make_event, now)

    for document in documents:
        if document.key in failed:
            _fail(document, failed[document.key], now)
        elif kind is not DocumentKind.PLAN or document.markdown:
            # The text is new: the comments on the one before are looked for again in it.
            reanchor(uow, TargetType.DOCUMENT, document.id, document.markdown, document.version)
    written = [document.key for document in documents if document.key not in failed]
    uow.record(
        make_event(
            EventType.DOCUMENT_GENERATION_FINISHED,
            message.id,
            {
                "kind": kind.value,
                "written": written,
                "failed": failed,
                "message_id": message.id,
                "session_id": message.session_id,
                **details,
            },
            Severity.ERROR if failed and not written else Severity.INFO,
        )
    )


def _complete_theory(
    document: Document, message: AgentMessage, hashes: dict[str, str | None], now: datetime
) -> dict[str, str]:
    text = message.markdown.strip()
    if not text:
        return {document.key: "the agent returned an empty document"}
    document.markdown = text
    document.title = first_heading(text) or document.title
    document.sources = sources_of(message.files_read or [], hashes)
    _fill(document, message, now)
    return {}


def sources_of(paths: list[str], hashes: dict[str, str | None]) -> list[dict[str, Any]]:
    """The files a text was written from, with what they contained when it was written. A
    file that could not be hashed (it is gone, or outside the project) is no source."""
    return [
        {"path": path, "sha": hashes[path]}
        for path in dict.fromkeys(paths)
        if hashes.get(path) is not None
    ]


def build_pipeline(answer: Any, cwd: Path) -> pipeline.Built | str:
    """What a structured answer makes as a pipeline, or the reason why it makes none."""
    return pipeline.build(answer, lambda raw: relative_path(raw, cwd))


def put_pipeline(
    document: Document, built: pipeline.Built, read: list[str], hashes: dict[str, str | None]
) -> None:
    """Make a built pipeline the content of its document. Its sources are the files given as
    read and the files its boxes name."""
    document.markdown = built.markdown
    document.pipeline = built.structure
    document.title = built.title
    document.summary = built.summary
    named = [path for node in built.structure["nodes"] for path in node["files"]]
    document.sources = sources_of([*read, *named], hashes)


def _complete_pipeline(
    document: Document,
    message: AgentMessage,
    cwd: Path,
    hashes: dict[str, str | None],
    now: datetime,
) -> tuple[dict[str, str], dict[str, Any]]:
    built = build_pipeline(message.structured_output, cwd)
    if isinstance(built, str):
        return {document.key: built}, {}
    put_pipeline(document, built, message.files_read or [], hashes)
    _fill(document, message, now)
    return {}, {
        "boxes": len(built.structure["nodes"]),
        "arrows": len(built.structure["edges"]),
        "entries_skipped": built.skipped,
    }


def _complete_files(
    documents: list[Document], message: AgentMessage, cwd: Path, now: datetime
) -> dict[str, str]:
    answer = message.structured_output
    entries = answer.get("files") if isinstance(answer, dict) else None
    if not isinstance(entries, list):
        return dict.fromkeys((document.key for document in documents), NO_STRUCTURE)
    described = {
        relative_path(str(entry.get("path", "")), cwd): entry
        for entry in entries
        if isinstance(entry, dict)
    }
    categories = {category.value for category in FileCategory}
    failed: dict[str, str] = {}
    for document in documents:
        entry = described.get(document.key)
        text = str(entry.get("description", "")).strip() if entry else ""
        if not text:
            failed[document.key] = "the agent returned no description of this file"
            continue
        document.markdown = repair_formulas(text)
        document.summary = _clip(str(entry.get("summary", "")), SUMMARY_MAX)  # type: ignore[union-attr]
        category = entry.get("category")  # type: ignore[union-attr]
        if category in categories:
            document.category = category
        document.title = document.key
        document.sources = [{"path": document.key, "sha": document.subject_sha}]
        _fill(document, message, now)
    return failed


def _complete_plan(
    uow: UnitOfWork,
    document: Document,
    message: AgentMessage,
    make_event: MakeEvent,
    now: datetime,
) -> tuple[dict[str, str], dict[str, Any]]:
    answer = message.structured_output
    cards = answer.get("cards") if isinstance(answer, dict) else None
    if not isinstance(answer, dict) or not isinstance(cards, list):
        return {document.key: NO_STRUCTURE}, {}
    created, changed, skipped = apply_plan(uow, message.project_id, cards, make_event, now)
    document.markdown = repair_formulas(str(answer.get("rationale", "")).strip())
    document.title = "Plan"
    document.summary = f"{created} card(s) added, {changed} changed" + (
        f", {skipped} entry(ies) of the answer could not be used" if skipped else ""
    )
    document.sources = []
    _fill(document, message, now)
    return {}, {"cards_created": created, "cards_changed": changed, "entries_skipped": skipped}


def apply_plan(
    uow: UnitOfWork,
    project_id: str,
    entries: list[Any],
    make_event: MakeEvent,
    now: datetime,
) -> tuple[int, int, int]:
    """Put the agent's cards on the board: new ones at the end of their column, and the
    changes it made to cards that exist. Returns how many were created, changed and skipped."""
    types = {kind.value for kind in CardType}
    statuses = {status.value for status in WorkflowStatus}
    created = changed = skipped = 0
    for entry in entries:
        if not isinstance(entry, dict):
            skipped += 1
            continue
        title = _clip(str(entry.get("title", "")), TITLE_MAX)
        card_type, status = entry.get("type"), entry.get("status")
        if not title or card_type not in types or status not in statuses:
            skipped += 1
            continue
        description = repair_formulas(str(entry.get("description", "")).strip()[:20000])
        existing = uow.cards.get(entry["id"]) if isinstance(entry.get("id"), str) else None
        if existing is not None and existing.project_id != project_id:
            existing = None
        if existing is None:
            card = uow.cards.add(
                BoardCard(
                    id=new_id("card"),
                    project_id=project_id,
                    type=card_type,
                    title=title,
                    description=description,
                    workflow_status=status,
                    sort_order=uow.cards.next_sort_order(project_id, status),
                    entity_ref=None,
                    origin=CardOrigin.AGENT.value,
                    version=1,
                    created_at=now,
                    updated_at=now,
                )
            )
            out = CardOut.model_validate(card)
            uow.record(
                make_event(
                    EventType.CARD_CREATED,
                    card.id,
                    {"card": out.model_dump(mode="json")},
                    Severity.INFO,
                )
            )
            created += 1
            continue
        if _change_card(uow, existing, card_type, title, description, status, make_event, now):
            changed += 1
    return created, changed, skipped


def _change_card(
    uow: UnitOfWork,
    card: BoardCard,
    card_type: str,
    title: str,
    description: str,
    status: str,
    make_event: MakeEvent,
    now: datetime,
) -> bool:
    wanted = {"type": card_type, "title": title, "description": description}
    fields = [name for name, value in wanted.items() if getattr(card, name) != value]
    moved = card.workflow_status != status
    if not fields and not moved:
        return False
    origin = {"workflow_status": card.workflow_status, "sort_order": card.sort_order}
    for name in fields:
        setattr(card, name, wanted[name])
    if moved:
        card.sort_order = uow.cards.next_sort_order(card.project_id, status)
        card.workflow_status = status
    card.version += 1
    card.updated_at = now
    payload: dict[str, Any] = {
        "card": CardOut.model_validate(card).model_dump(mode="json"),
        "changed_fields": fields,
    }
    if moved:
        payload["from"] = origin
        payload["to"] = {"workflow_status": card.workflow_status, "sort_order": card.sort_order}
        payload["reindexed"] = []
    uow.record(
        make_event(
            EventType.CARD_MOVED if moved else EventType.CARD_UPDATED,
            card.id,
            payload,
            Severity.INFO,
        )
    )
    return True
