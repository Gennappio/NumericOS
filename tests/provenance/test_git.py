"""Read-only Git access, against real repositories."""

from __future__ import annotations

import subprocess
import time
from pathlib import Path

import pytest

from numericos.provenance import git
from tests.gitrepo import ENVIRONMENT, SOLVER, Repo

SOLVER_PATH = "examples/heat2d-python/heat2d.py"


def test_the_top_of_a_work_tree_is_recognised(repo: Repo, tmp_path: Path) -> None:
    inside = repo.root / "examples"
    outside = tmp_path / "plain"
    outside.mkdir()

    assert git.is_toplevel(repo.root)
    assert git.toplevel(inside) == repo.root.resolve()
    assert not git.is_toplevel(inside)
    assert git.toplevel(outside) is None
    assert not git.is_toplevel(tmp_path / "does-not-exist")


def test_a_ref_resolves_to_a_full_commit_sha(repo: Repo) -> None:
    first = repo.head
    repo.git("tag", "v1")
    repo.write(SOLVER_PATH, SOLVER + "# faster\n")
    second = repo.commit("candidate")

    assert git.resolve_commit(repo.root, "HEAD") == second
    assert git.resolve_commit(repo.root, "main") == second
    assert git.resolve_commit(repo.root, "v1") == first
    assert git.resolve_commit(repo.root, "HEAD~1") == first
    assert git.resolve_commit(repo.root, first[:10]) == first
    assert git.head(repo.root) == second


@pytest.mark.parametrize("ref", ["no-such-branch", "--help", "-n", "HEAD^{tree}x", "0" * 40])
def test_what_is_not_a_commit_is_refused(repo: Repo, ref: str) -> None:
    with pytest.raises(git.UnknownRefError):
        git.resolve_commit(repo.root, ref)


def test_a_repository_without_commits_has_no_head(tmp_path: Path) -> None:
    empty = Repo(tmp_path / "empty")
    empty.root.mkdir()
    empty.git("init", "-q", "-b", "main")

    assert git.head(empty.root) is None
    assert git.is_toplevel(empty.root)


def test_commit_info_names_author_time_and_subject(repo: Repo) -> None:
    info = git.commit_info(repo.root, repo.head)

    assert (info.subject, info.author) == ("baseline solver", "Ada Lovelace")
    assert info.authored_at.tzinfo is not None


def test_status_reports_changes_and_untracked_files_but_not_ignored_ones(repo: Repo) -> None:
    assert not git.status(repo.root).dirty

    repo.write(SOLVER_PATH, SOLVER + "# edited\n")
    repo.write("notes/new idea.md", "untracked, with a space in its name")
    repo.write("ignored/cache.bin", "ignored by .gitignore")
    repo.write("run.log", "ignored by pattern")

    state = git.status(repo.root)
    assert state.dirty
    assert state.changed == [SOLVER_PATH]
    assert state.untracked == ["notes/new idea.md"]


def test_a_staged_rename_is_one_change(repo: Repo) -> None:
    repo.git("mv", SOLVER_PATH, "examples/heat2d-python/solver.py")

    state = git.status(repo.root)

    assert state.changed == ["examples/heat2d-python/solver.py"]
    assert state.untracked == []


def test_reading_the_status_does_not_write_to_the_repository(repo: Repo) -> None:
    index = repo.root / ".git" / "index"
    solver = repo.root / SOLVER_PATH
    solver.write_text(solver.read_text())  # same content, new mtime: git would refresh the index
    before = (index.read_bytes(), index.stat().st_mtime_ns)

    git.status(repo.root)
    git.diff_against_head(repo.root)

    assert (index.read_bytes(), index.stat().st_mtime_ns) == before


def test_the_patch_of_uncommitted_changes_reproduces_them(repo: Repo, tmp_path: Path) -> None:
    repo.write(SOLVER_PATH, SOLVER + "print('candidate')\n")
    repo.write("data/table.bin", "")
    (repo.root / "data/table.bin").write_bytes(bytes(range(256)))
    repo.git("add", "data/table.bin")  # a new tracked binary file is part of the patch

    patch = git.diff_against_head(repo.root)

    clone = tmp_path / "clone"
    subprocess.run(["git", "clone", "-q", str(repo.root), str(clone)], env=ENVIRONMENT, check=True)
    subprocess.run(
        ["git", "-C", str(clone), "apply", "--binary"], input=patch, env=ENVIRONMENT, check=True
    )
    assert (clone / SOLVER_PATH).read_text() == (repo.root / SOLVER_PATH).read_text()
    assert (clone / "data/table.bin").read_bytes() == bytes(range(256))


def test_export_writes_exactly_the_commit(repo: Repo, tmp_path: Path) -> None:
    repo.write("bin/run.sh", "#!/bin/sh\necho ok\n", executable=True)
    committed = repo.commit("add launcher")
    repo.write(SOLVER_PATH, "uncommitted edit\n")
    repo.write("scratch.txt", "untracked\n")
    destination = tmp_path / "export"

    git.export(repo.root, committed, destination)

    assert (destination / SOLVER_PATH).read_text() == SOLVER
    assert (destination / "bin/run.sh").stat().st_mode & 0o111  # still executable
    assert not (destination / "scratch.txt").exists()
    assert not (destination / ".git").exists()
    assert sorted(path.name for path in destination.iterdir()) == [".gitignore", "bin", "examples"]


def test_exported_files_carry_the_time_of_the_export_not_of_the_commit(
    repo: Repo, tmp_path: Path
) -> None:
    repo.git("commit", "-q", "--amend", "--no-edit", "--date", "2001-01-01T00:00:00Z")
    before = time.time()

    git.export(repo.root, repo.head, tmp_path / "export")

    stamps = [path.stat().st_mtime for path in (tmp_path / "export").rglob("*") if path.is_file()]
    assert stamps
    assert all(before - 2 <= stamp <= time.time() + 2 for stamp in stamps)
    assert len({round(stamp, 3) for stamp in stamps}) == 1  # one moment for the whole tree


def test_export_of_an_older_commit_ignores_what_came_later(repo: Repo, tmp_path: Path) -> None:
    baseline = repo.head
    repo.write(SOLVER_PATH, SOLVER + "# candidate\n")
    repo.commit("candidate")

    git.export(repo.root, baseline, tmp_path / "baseline")

    assert (tmp_path / "baseline" / SOLVER_PATH).read_text() == SOLVER


def test_a_failed_export_leaves_nothing_behind(repo: Repo, tmp_path: Path) -> None:
    target = tmp_path / "out" / "export"

    with pytest.raises(git.GitError):
        git.export(repo.root, "f" * 40, target)

    assert not target.exists()
    assert list((tmp_path / "out").iterdir()) == []

    target.mkdir()
    with pytest.raises(git.GitError, match="already exists"):
        git.export(repo.root, repo.head, target)


def test_the_diff_between_two_commits_is_cut_at_the_limit(repo: Repo) -> None:
    baseline = repo.head
    repo.write(SOLVER_PATH, SOLVER + "print('candidate')\n")
    candidate = repo.commit("candidate")

    text, truncated = git.diff_between(repo.root, baseline, candidate)
    cut, was_cut = git.diff_between(repo.root, baseline, candidate, max_bytes=40)

    assert "+print('candidate')" in text
    assert not truncated
    assert (len(cut), was_cut) == (40, True)


def test_the_remote_url_is_recorded_without_credentials(repo: Repo) -> None:
    assert git.remote_url(repo.root) is None

    repo.git("remote", "add", "origin", "https://ada:s3cret-token@example.org/lab/solver.git")
    assert git.remote_url(repo.root) == "https://example.org/lab/solver.git"

    repo.git("remote", "set-url", "origin", "git@example.org:lab/solver.git")
    assert git.remote_url(repo.root) == "git@example.org:lab/solver.git"
