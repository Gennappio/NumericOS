"""Documents the agent writes about a project: its theory, the description of its files, its
plan. The API queues a turn of the agent for each request and marks the documents it will
write; the supervisor fills them when the turn ends (``numericos.agents.documents``).

Whether a document is still current is never stored. It is computed on every read from the
content hashes of the files it was written from: a file that changed, or is gone, makes it
stale, and says which file.
"""

from __future__ import annotations

from pathlib import Path

from numericos.agents import prompts
from numericos.config import Settings
from numericos.core.enums import (
    AgentTask,
    DocumentKind,
    DocumentStatus,
    EventType,
    FileCategory,
    PermissionMode,
)
from numericos.core.errors import (
    ExecutionNotTrustedError,
    GenerationPendingError,
    InvalidRequestError,
    NotFoundError,
)
from numericos.core.files import guess_category, is_viewable_image, media_type
from numericos.core.ids import new_id
from numericos.core.schemas import (
    CardOut,
    DescribeOut,
    DescribeRequest,
    DocumentOut,
    DocumentSlot,
    FileCounts,
    FileDescriptionState,
    FileEntry,
    FileList,
    GenerateRequest,
)
from numericos.events.ledger import EventContext, build_event
from numericos.persistence.engine import utcnow
from numericos.persistence.models import AgentMessage, AgentSession, Document, Project
from numericos.persistence.unit_of_work import UnitOfWork
from numericos.provenance import git
from numericos.services import agents
from numericos.services.guards import require_project, require_trusted_root

#: Files listed for one project, and files one request may ask the agent to describe.
MAX_LISTED = 5000
MAX_PER_REQUEST = 400
SINGLE_KEY = {DocumentKind.THEORY: "theory", DocumentKind.PLAN: "plan"}


def _trusted_root_or_none(project: Project) -> Path | None:
    try:
        return require_trusted_root(project)
    except ExecutionNotTrustedError:
        return None


def _with_staleness(out: DocumentOut, root: Path | None) -> DocumentOut:
    """Compare the files the document was written from with what they contain now."""
    if root is None or not out.sources or out.message_id is None:
        return out
    try:
        current = git.content_hashes(root, [source.path for source in out.sources])
    except git.GitError:
        return out
    changed = [source.path for source in out.sources if current.get(source.path) != source.sha]
    return out.model_copy(update={"stale": bool(changed), "changed_sources": changed})


def get_document(uow: UnitOfWork, document_id: str) -> DocumentOut:
    with uow:
        document = uow.documents.get(document_id)
        if document is None:
            raise NotFoundError(
                f"document {document_id} not found",
                details={"resource": "document", "id": document_id},
            )
        project = require_project(uow, document.project_id)
        out, root = DocumentOut.model_validate(document), _trusted_root_or_none(project)
    return _with_staleness(out, root)


def get_single(uow: UnitOfWork, project_id: str, kind: DocumentKind) -> DocumentSlot:
    """The theory or the plan notes of a project, if the agent was ever asked for them."""
    with uow:
        project = require_project(uow, project_id)
        document = uow.documents.by_key(project.id, kind.value, SINGLE_KEY[kind])
        if document is None:
            return DocumentSlot(document=None)
        out, root = DocumentOut.model_validate(document), _trusted_root_or_none(project)
    return DocumentSlot(document=_with_staleness(out, root))


def _pending(
    uow: UnitOfWork, project: Project, kind: DocumentKind, key: str, instructions: str | None
) -> Document:
    """The document of this key, created if needed, ready to be marked with a new turn."""
    document = uow.documents.by_key(project.id, kind.value, key)
    now = utcnow()
    if document is None:
        document = uow.documents.add(
            Document(
                id=new_id("doc"),
                project_id=project.id,
                kind=kind.value,
                key=key,
                title="",
                summary="",
                markdown="",
                status=DocumentStatus.GENERATING.value,
                instructions=instructions or "",
                sources=[],
                version=0,
                created_at=now,
                updated_at=now,
            )
        )
    elif document.pending_message_id is not None:
        raise GenerationPendingError(
            f"the agent is already writing {kind.value} {key!r}",
            details={"document_id": document.id, "message_id": document.pending_message_id},
        )
    if instructions is not None:
        document.instructions = instructions
    return document


def _mark(document: Document, session: AgentSession, turn: AgentMessage) -> None:
    document.pending_message_id = turn.id
    document.session_id = session.id
    document.status_reason = None
    if document.message_id is None:
        document.status = DocumentStatus.GENERATING.value
    document.updated_at = utcnow()


def _queued_event(
    uow: UnitOfWork,
    project: Project,
    kind: DocumentKind,
    keys: list[str],
    session: AgentSession,
    turn: AgentMessage,
    context: EventContext,
) -> None:
    uow.record(
        build_event(
            event_type=EventType.DOCUMENT_GENERATION_QUEUED,
            project_id=project.id,
            subject_id=turn.id,
            payload={
                "kind": kind.value,
                "keys": keys,
                "message_id": turn.id,
                "session_id": session.id,
            },
            context=context,
        )
    )


def generate_theory(
    uow: UnitOfWork,
    project_id: str,
    data: GenerateRequest,
    context: EventContext,
    *,
    settings: Settings,
) -> DocumentOut:
    """Ask the agent to write, or write again, the theory of the project."""
    agents.require_available(settings)
    with uow:
        project = require_project(uow, project_id)
        root = require_trusted_root(project)
        document = _pending(uow, project, DocumentKind.THEORY, "theory", data.instructions)
        session = agents.open_session(
            uow,
            project,
            root,
            task=AgentTask.THEORY,
            mode=PermissionMode.READ_ONLY,
            title=f"Theory of {project.name}",
            context=context,
        )
        turn = agents.queue_turn(
            uow,
            session,
            prompts.theory(project.name, project.research_question, document.instructions),
            context,
        )
        _mark(document, session, turn)
        _queued_event(uow, project, DocumentKind.THEORY, ["theory"], session, turn, context)
        out = DocumentOut.model_validate(document)
        uow.commit()
    return out


def generate_plan(
    uow: UnitOfWork,
    project_id: str,
    data: GenerateRequest,
    context: EventContext,
    *,
    settings: Settings,
) -> DocumentOut:
    """Ask the agent for a plan. Its cards go to the board when its turn ends; the cards that
    are on the board now are shown to it, so that it adds to them or changes them."""
    agents.require_available(settings)
    with uow:
        project = require_project(uow, project_id)
        root = require_trusted_root(project)
        document = _pending(uow, project, DocumentKind.PLAN, "plan", data.instructions)
        cards = [
            CardOut.model_validate(card).model_dump(mode="json")
            for card in uow.cards.list_for_project(project.id)
        ]
        session = agents.open_session(
            uow,
            project,
            root,
            task=AgentTask.PLAN,
            mode=PermissionMode.READ_ONLY,
            title=f"Plan of {project.name}",
            context=context,
        )
        turn = agents.queue_turn(
            uow,
            session,
            prompts.plan(project.name, project.research_question, cards, document.instructions),
            context,
            json_schema=prompts.PLAN_SCHEMA,
        )
        _mark(document, session, turn)
        _queued_event(uow, project, DocumentKind.PLAN, ["plan"], session, turn, context)
        out = DocumentOut.model_validate(document)
        uow.commit()
    return out


# --------------------------------------------------------------------------- files


def _listing(root: Path) -> tuple[list[str], dict[str, str | None], bool]:
    """The files of the project and their content hashes, read with no transaction open."""
    try:
        paths = git.working_files(root)
        truncated = len(paths) > MAX_LISTED
        paths = paths[:MAX_LISTED]
        return paths, git.content_hashes(root, paths), truncated
    except git.GitError as error:
        raise InvalidRequestError(
            f"the project directory could not be read as a Git repository: {error}",
            details={"errors": [{"loc": ["root_path"], "msg": str(error), "type": "git_error"}]},
        ) from error


def _root_of(uow: UnitOfWork, project_id: str) -> tuple[str, Path]:
    with uow:
        project = require_project(uow, project_id)
        return project.id, require_trusted_root(project)


def _is_stale(document: Document, sha: str | None) -> bool:
    return document.message_id is not None and document.subject_sha != sha


def list_files(uow: UnitOfWork, project_id: str) -> FileList:
    """Every file of the project with what is known about it: size, kind, and its description
    if there is one, marked stale when the file changed since it was written."""
    project_id, root = _root_of(uow, project_id)
    paths, hashes, truncated = _listing(root)
    with uow:
        documents = {
            document.key: document
            for document in uow.documents.list_for_project(
                project_id, DocumentKind.FILE_DESCRIPTION.value
            )
        }
        entries: list[FileEntry] = []
        counts = dict.fromkeys(("described", "stale", "generating", "failed", "undescribed"), 0)
        for path in paths:
            document = documents.get(path)
            sha = hashes.get(path)
            state = None
            if document is None:
                counts["undescribed"] += 1
            else:
                stale = _is_stale(document, sha)
                pending = document.pending_message_id is not None
                state = FileDescriptionState(
                    document_id=document.id,
                    status=DocumentStatus(document.status),
                    summary=document.summary,
                    stale=stale,
                    pending=pending,
                    status_reason=document.status_reason,
                    updated_at=document.updated_at,
                )
                if pending:
                    counts["generating"] += 1
                elif document.message_id is None:
                    counts["failed"] += 1
                elif stale:
                    counts["stale"] += 1
                else:
                    counts["described"] += 1
            try:
                size = (root / path).stat().st_size
            except OSError:
                size = 0
            category = document.category if document is not None and document.category else None
            entries.append(
                FileEntry(
                    path=path,
                    size_bytes=size,
                    category=FileCategory(category) if category else guess_category(path),
                    sha=sha,
                    viewable_image=is_viewable_image(path),
                    description=state,
                )
            )
    return FileList(
        root=str(root),
        files=entries,
        counts=FileCounts(total=len(entries), **counts),
        truncated=truncated,
    )


def describe_files(
    uow: UnitOfWork,
    project_id: str,
    data: DescribeRequest,
    context: EventContext,
    *,
    settings: Settings,
) -> DescribeOut:
    """Ask the agent to describe files: the ones named, or every file in a state. The files
    are grouped a few per turn; files that are being described already are left out."""
    agents.require_available(settings)
    project_id, root = _root_of(uow, project_id)
    paths, hashes, _truncated = _listing(root)
    known = set(paths)
    if data.paths is not None:
        unknown = sorted(set(data.paths) - known)
        if unknown:
            raise InvalidRequestError(
                f"not files of the project: {', '.join(unknown[:5])}",
                details={
                    "errors": [
                        {"loc": ["body", "paths"], "msg": "not a file of the project", "path": path}
                        for path in unknown[:50]
                    ]
                },
            )
    with uow:
        project = require_project(uow, project_id)
        documents = {
            document.key: document
            for document in uow.documents.list_for_project(
                project.id, DocumentKind.FILE_DESCRIPTION.value
            )
        }

        def wanted(path: str) -> bool:
            document = documents.get(path)
            if data.scope == "undescribed":
                return document is None or document.message_id is None
            if data.scope == "stale":
                return document is not None and _is_stale(document, hashes.get(path))
            return True

        chosen = (
            sorted(set(data.paths)) if data.paths is not None else [p for p in paths if wanted(p)]
        )
        busy = {
            path
            for path in chosen
            if path in documents and documents[path].pending_message_id is not None
        }
        targets = [path for path in chosen if path not in busy]
        left = max(0, len(targets) - MAX_PER_REQUEST)
        targets = targets[:MAX_PER_REQUEST]

        size = settings.agent_files_per_turn
        message_ids: list[str] = []
        for start in range(0, len(targets), size):
            batch = targets[start : start + size]
            more = f" and {len(batch) - 1} more" if len(batch) > 1 else ""
            session = agents.open_session(
                uow,
                project,
                root,
                task=AgentTask.FILE_DESCRIPTION,
                mode=PermissionMode.READ_ONLY,
                title=f"Describe {batch[0]}{more}",
                context=context,
            )
            turn = agents.queue_turn(
                uow,
                session,
                prompts.files(batch, data.instructions or ""),
                context,
                json_schema=prompts.FILES_SCHEMA,
            )
            for path in batch:
                document = _pending(
                    uow, project, DocumentKind.FILE_DESCRIPTION, path, data.instructions
                )
                document.subject_sha = hashes.get(path)
                document.category = document.category or guess_category(path).value
                _mark(document, session, turn)
            _queued_event(
                uow, project, DocumentKind.FILE_DESCRIPTION, batch, session, turn, context
            )
            message_ids.append(turn.id)
        if message_ids:
            uow.commit()
    return DescribeOut(
        queued=len(targets),
        turns=len(message_ids),
        skipped=len(busy),
        left=left,
        message_ids=message_ids,
    )


def file_description(uow: UnitOfWork, project_id: str, path: str) -> DocumentOut:
    """The description of one file, with whether the file changed since."""
    with uow:
        project = require_project(uow, project_id)
        document = uow.documents.by_key(project.id, DocumentKind.FILE_DESCRIPTION.value, path)
        if document is None:
            raise NotFoundError(
                f"{path} has no description", details={"resource": "document", "id": path}
            )
        out, root = DocumentOut.model_validate(document), _trusted_root_or_none(project)
    return _with_staleness(out, root)


def file_content(uow: UnitOfWork, project_id: str, path: str) -> tuple[Path, str]:
    """A file of the trusted project directory, to show it (an image of the theory, a figure
    of the results). Only regular files inside the directory are served."""
    _project_id, root = _root_of(uow, project_id)
    resolved = (root / path).resolve()
    if not resolved.is_relative_to(root.resolve()) or not resolved.is_file():
        raise NotFoundError(
            f"{path} is not a file of the project", details={"resource": "file", "id": path}
        )
    return resolved, media_type(path)
