"""The NumericOS folder of a project: everything generated is kept there, the repository is
watched for what a turn leaves in it, and what it left can be moved out."""

from __future__ import annotations

import json
from pathlib import Path

from numericos.agents import layout, workspace
from numericos.config import Settings
from numericos.core.enums import PermissionMode
from numericos.executor.worker import Worker
from tests.lab import Json, Lab, drive

SOLVER = "examples/heat2d-python/heat2d.py"


def ended(lab: Lab, message_id: str) -> bool:
    return lab.turn_status(message_id) not in ("queued", "running")


def settled(document: Json | None) -> Json | None:
    return document if document and document["pending_message_id"] is None else None


def status(lab: Lab) -> str:
    return lab.repo.git("status", "--porcelain", "--untracked-files=all")


def test_what_the_agent_generates_goes_to_a_folder_git_does_not_see(
    lab: Lab, supervisor: Worker, settings: Settings
) -> None:
    before = status(lab)
    turn = lab.ask(lab.open_session(), "Check the scheme.\nSCRATCH check.py::print('ok')")
    drive(supervisor, lambda: ended(lab, turn["id"]))

    folder = lab.repo.root / ".numericos"
    answer = lab.message(turn["id"])
    info = lab.workspace()

    assert (folder / "scratch" / "check.py").read_text() == "print('ok')"
    assert (folder / ".gitignore").read_text() == "*\n"
    assert (
        "Everything NumericOS and its coding agent generate" in (folder / "README.md").read_text()
    )
    # The repository is exactly as it was: the folder ignores itself, nothing else changed.
    assert status(lab) == before == ""
    assert answer["files_created"] == [] and answer["files_moved"] == []
    assert info == {
        "path": str(folder),
        "shown": ".numericos/",
        "inside_project": True,
        "exists": True,
        "ignored_by_git": True,
    }
    # The turn was told where to put what it generates, and found the place in its environment.
    prompt = (layout.turn_dir(settings.data_dir, turn["id"]) / layout.PROMPT).read_text()
    assert "Keep the repository clean" in prompt
    assert "goes under .numericos/scratch/, never elsewhere in the repository" in prompt
    assert "are in .numericos/docs/ as Markdown" in prompt
    assert "Leave no caches in the repository either" in prompt
    # Tools the agent runs keep their caches in the folder, not next to the sources.
    caches = workspace.environment(folder)
    assert caches["PYTHONPYCACHEPREFIX"] == str(folder / "cache" / "pycache")
    assert caches["NUMERICOS_SCRATCH_DIR"] == str(folder / "scratch")
    assert {"MYPY_CACHE_DIR", "RUFF_CACHE_DIR"} <= set(caches)
    spec = json.loads((layout.turn_dir(settings.data_dir, turn["id"]) / layout.SPEC).read_text())
    assert "--add-dir" not in spec["argv"]  # inside the working directory already


def test_a_file_a_turn_leaves_in_the_repository_is_reported_and_can_be_moved_out(
    lab: Lab, supervisor: Worker
) -> None:
    lab.repo.write("mine.txt", "written by the researcher, not committed\n")
    turn = lab.ask(
        lab.open_session(),
        "WRITE notes_from_agent.md::scratch\nWRITE tmp/out.csv::1,2\n"
        f"WRITE {SOLVER}::print('edited')",
    )
    drive(supervisor, lambda: ended(lab, turn["id"]))
    answer = lab.message(turn["id"])

    # New files only: the edit of a tracked file is a change, and the researcher's own
    # untracked file was there before.
    assert answer["files_written"] == ["notes_from_agent.md", "tmp/out.csv", SOLVER]
    assert answer["files_created"] == ["notes_from_agent.md", "tmp/out.csv"]

    refused = lab.http.post(
        f"/v1/messages/{turn['id']}:move-created-files", json={"paths": ["mine.txt"]}
    )
    one = lab.move_created(turn["id"], paths=["tmp/out.csv"])
    rest = lab.move_created(turn["id"])
    again = lab.move_created(turn["id"])

    assert refused.status_code == 422
    assert one["files_moved"] == ["tmp/out.csv"]
    assert rest["files_moved"] == ["notes_from_agent.md", "tmp/out.csv"]
    assert again["version"] == rest["version"]  # nothing left to move
    moved = lab.repo.root / ".numericos" / "moved" / turn["id"]
    assert (moved / "tmp" / "out.csv").read_text() == "1,2"
    assert (moved / "notes_from_agent.md").read_text() == "scratch"
    assert not (lab.repo.root / "notes_from_agent.md").exists()
    assert (lab.repo.root / "mine.txt").exists()
    # What is left for Git to show: the change that was asked for, and the researcher's file.
    assert [line.strip() for line in status(lab).splitlines()] == [f"M {SOLVER}", "?? mine.txt"]
    events = [e for e in lab.turn_events(turn["id"]) if e["type"] == "AGENT_FILES_MOVED"]
    assert [e["payload"]["paths"] for e in events] == [["tmp/out.csv"], ["notes_from_agent.md"]]


def test_a_created_file_that_was_committed_since_is_the_projects_own(
    lab: Lab, supervisor: Worker
) -> None:
    turn = lab.ask(lab.open_session(), "WRITE src/new_module.py::x = 1")
    drive(supervisor, lambda: ended(lab, turn["id"]))
    lab.repo.commit("keep the new module")

    after = lab.move_created(turn["id"])

    assert after["files_created"] == ["src/new_module.py"] and after["files_moved"] == []
    assert (lab.repo.root / "src" / "new_module.py").exists()


def test_documents_are_kept_as_markdown_files_in_the_folder(lab: Lab, supervisor: Worker) -> None:
    lab.generate("theory", f"READ {SOLVER}")
    drive(supervisor, lambda: settled(lab.single("theory")))
    lab.describe(paths=[SOLVER])
    drive(supervisor, lambda: lab.files()["counts"]["generating"] == 0)
    lab.generate("plan")
    drive(supervisor, lambda: settled(lab.single("plan")))

    docs = lab.repo.root / ".numericos" / "docs"
    theory = (docs / "theory.md").read_text()

    assert theory.startswith("<!-- Written by NumericOS (theory, version 1, ")
    assert "This file is overwritten when the document changes" in theory
    assert "\n\n# Explicit scheme for the 2D heat equation\n" in theory
    assert f"`{SOLVER}` holds" in (docs / "files" / f"{SOLVER}.md").read_text()
    assert "Check stability **first**" in (docs / "plan.md").read_text()
    assert status(lab) == ""  # none of it is seen by Git
    # The folder is not a file of the project: it is neither listed nor described.
    assert all(not entry["path"].startswith(".numericos") for entry in lab.files()["files"])

    comment = lab.comment(lab.single("theory") or {}, "change", "Forward Euler", "Go implicit.")
    lab.send_comments(
        "resolve", lab.single("theory") or {}, instructions="REPLACE Forward Euler=>Backward Euler"
    )
    drive(
        supervisor, lambda: lab.comments(lab.single("theory") or {})["pending_message_id"] is None
    )
    rewritten = (docs / "theory.md").read_text()
    assert comment["status"] == "open"
    assert "version 2" in rewritten and "Backward Euler in time" in rewritten


def test_a_task_that_writes_a_document_is_told_to_leave_the_folder_alone(
    lab: Lab, supervisor: Worker, settings: Settings
) -> None:
    document = lab.generate("theory")
    drive(supervisor, lambda: settled(lab.single("theory")))

    turn_dir = layout.turn_dir(settings.data_dir, document["pending_message_id"])
    prompt = (turn_dir / layout.PROMPT).read_text()

    assert "Do not read, describe or list that folder" in prompt
    assert "Keep the repository clean" not in prompt  # read-only: it cannot create anything
    assert not (turn_dir / layout.UNTRACKED).exists()


def test_the_folder_can_be_kept_outside_the_project(
    lab: Lab, supervisor: Worker, settings: Settings, tmp_path: Path
) -> None:
    settings.workspace_root = tmp_path / "numericos-workspaces"
    turn = lab.ask(lab.open_session(), "SCRATCH check.py::print('ok')")
    drive(supervisor, lambda: ended(lab, turn["id"]))

    folder = settings.workspace_root / lab.project["id"]
    info = lab.workspace()
    spec = json.loads((layout.turn_dir(settings.data_dir, turn["id"]) / layout.SPEC).read_text())

    assert (folder / "scratch" / "check.py").read_text() == "print('ok')"
    assert not (lab.repo.root / ".numericos").exists()  # nothing at all in the project
    assert (info["inside_project"], info["shown"], info["ignored_by_git"]) == (
        False,
        f"{folder}/",
        True,
    )
    # The agent is given the folder explicitly: it is outside its working directory.
    assert spec["argv"][-2:] == ["--add-dir", str(folder)]


def test_what_a_turn_is_told_depends_on_what_it_may_do(tmp_path: Path) -> None:
    root, folder = tmp_path, tmp_path / ".numericos"

    read_only = workspace.note(folder, root, PermissionMode.READ_ONLY, "conversation")
    editing = workspace.note(folder, root, PermissionMode.EDIT, "resolve")
    writing = workspace.note(folder, root, PermissionMode.READ_ONLY, "file_description")
    outside = workspace.note(
        tmp_path.parent / "elsewhere", root, PermissionMode.FULL, "conversation"
    )

    assert "read them when they help" in read_only and "Keep the repository clean" not in read_only
    assert ".numericos/scratch/" in editing and "say in your answer what you put there" in editing
    assert "Do not read, describe or list that folder" in writing and "docs/" not in writing
    assert f"{tmp_path.parent / 'elsewhere'}/scratch/" in outside
    assert workspace.mirror_path("file_description", "src/a.py") == Path("docs/files/src/a.py.md")
