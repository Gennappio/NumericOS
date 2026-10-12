"""The NumericOS folder of a project: the one place where anything NumericOS or its agent
generates about a project is kept, so that the project's repository stays as its author
left it.

By default it is ``.numericos`` at the top of the project directory. It ignores itself for
Git (its own ``.gitignore`` holds ``*``), so nothing in it ever shows in ``git status`` and
nothing of it can be committed by accident; no file of the project, and nothing under
``.git``, is changed to obtain that. With ``NUMERICOS_WORKSPACE_ROOT`` set, the folder of each
project is ``<that directory>/<project id>`` instead, outside the project altogether.

What it holds:

- ``scratch/``: what the agent creates that is not a change to the project (helper scripts,
  notes, logs, outputs of commands it ran, figures);
- ``docs/``: the documents NumericOS holds about the project, as Markdown files (the theory,
  the notes of the plan, the description of each file), rewritten whenever they change;
- ``moved/``: files a turn of the agent left in the repository and the researcher moved out;
- ``cache/``: caches of tools the agent ran (Python bytecode, mypy, ruff), which would
  otherwise be written next to the sources.
"""

from __future__ import annotations

import shutil
from pathlib import Path

from numericos.config import Settings
from numericos.core.enums import AgentTask, DocumentKind, PermissionMode
from numericos.persistence.models import Document

FOLDER = ".numericos"
SCRATCH = "scratch"
DOCS = "docs"
MOVED = "moved"
CACHE = "cache"

README = """# NumericOS folder

Everything NumericOS and its coding agent generate about this project is kept here, so that
the project's own files stay as you left them.

- `scratch/`: helper scripts, notes, logs and outputs the agent created while working. Safe
  to delete at any time.
- `docs/`: the theory, the notes of the plan and the description of each file, as Markdown.
  They are written by NumericOS and overwritten when they change: edit them in NumericOS.
- `moved/`: files a turn of the agent left in the repository and that you moved out of it.
- `cache/`: caches of tools the agent ran, kept out of the source tree. Safe to delete.

This folder ignores itself for Git (see its `.gitignore`): nothing in it shows in
`git status` or can be committed by accident. Delete the folder whenever you like; NumericOS
creates it again when it needs it.
"""

#: Tasks that write a document from the project: the folder is not part of the project and
#: must not be read as if it were (an old theory would be copied into the new one).
WRITING_TASKS = frozenset(
    {AgentTask.THEORY.value, AgentTask.FILE_DESCRIPTION.value, AgentTask.PLAN.value}
)


def workspace_dir(settings: Settings, project_id: str, root: Path) -> Path:
    """The NumericOS folder of a project whose directory is ``root``."""
    if settings.workspace_root is not None:
        return settings.workspace_root / project_id
    return root / FOLDER


def inside(workspace: Path, root: Path) -> bool:
    return workspace.resolve().is_relative_to(root.resolve())


def shown(workspace: Path, root: Path) -> str:
    """The folder as the agent and the researcher are told about it: relative to the project
    when it is inside it."""
    return (
        f"{workspace.relative_to(root).as_posix()}/" if inside(workspace, root) else f"{workspace}/"
    )


def ensure(workspace: Path) -> None:
    """Create the folder with what makes it ignore itself and explain itself."""
    (workspace / SCRATCH).mkdir(parents=True, exist_ok=True)
    ignore = workspace / ".gitignore"
    if not ignore.exists():
        ignore.write_text("*\n")
    readme = workspace / "README.md"
    if not readme.exists():
        readme.write_text(README)


def note(workspace: Path, root: Path, mode: PermissionMode, task: str) -> str:
    """What a turn is told about the folder, after what it is told about its permissions."""
    where = shown(workspace, root)
    if task in WRITING_TASKS:
        return (
            f"(NumericOS keeps its own files about this project in {where}: they are not part "
            "of the project. Do not read, describe or list that folder.)"
        )
    said = (
        f"(NumericOS keeps its own files about this project in {where}, outside what Git "
        f"tracks. The theory, the plan and the descriptions of the files it holds are in "
        f"{where}{DOCS}/ as Markdown, if they were written: read them when they help."
    )
    if mode is PermissionMode.READ_ONLY:
        return f"{said})"
    return (
        f"{said} Keep the repository clean: anything you create that is not itself a change "
        f"to the project that was asked for (helper or test scripts, notes, logs, outputs of "
        f"commands you run, figures) goes under {where}{SCRATCH}/, never elsewhere in the "
        "repository, and you say in your answer what you put there. Leave no caches in the "
        "repository either (for example __pycache__): remove what a command you ran left.)"
    )


def environment(workspace: Path) -> dict[str, str]:
    """What the agent's process is given so that it, and the tools it runs, find the folder
    and keep their caches there instead of next to the sources."""
    cache = workspace / CACHE
    return {
        "NUMERICOS_WORKSPACE": str(workspace),
        "NUMERICOS_SCRATCH_DIR": str(workspace / SCRATCH),
        "PYTHONPYCACHEPREFIX": str(cache / "pycache"),
        "MYPY_CACHE_DIR": str(cache / "mypy"),
        "RUFF_CACHE_DIR": str(cache / "ruff"),
    }


def mirror_path(kind: str, key: str) -> Path:
    """Where a document is kept as a file, relative to the folder."""
    if kind == DocumentKind.THEORY.value:
        return Path(DOCS) / "theory.md"
    if kind == DocumentKind.PLAN.value:
        return Path(DOCS) / "plan.md"
    return Path(DOCS) / "files" / f"{key}.md"


def mirror(workspace: Path, document: Document) -> Path | None:
    """Write a document as a Markdown file in the folder; nothing for one without content."""
    if document.version == 0 or not document.markdown.strip():
        return None
    ensure(workspace)
    path = workspace / mirror_path(document.kind, document.key)
    path.parent.mkdir(parents=True, exist_ok=True)
    written = document.generated_at.strftime("%Y-%m-%d %H:%M UTC") if document.generated_at else "?"
    header = (
        f"<!-- Written by NumericOS ({document.kind}, version {document.version}, {written}"
        f"{', ' + document.model if document.model else ''}). "
        "This file is overwritten when the document changes: edit it in NumericOS. -->\n\n"
    )
    path.write_text(f"{header}{document.markdown.rstrip()}\n")
    return path


def move_out(root: Path, workspace: Path, message_id: str, paths: list[str]) -> list[str]:
    """Move files a turn left in the repository into the folder, keeping their relative
    paths. Returns the ones that were there to move."""
    ensure(workspace)
    moved = []
    for relative in paths:
        source = (root / relative).resolve()
        if not source.is_relative_to(root.resolve()) or not source.is_file():
            continue
        destination = workspace / MOVED / message_id / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.move(str(source), destination)
        moved.append(relative)
    return moved
