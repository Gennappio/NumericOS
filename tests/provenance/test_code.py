"""Which code a run executes and how the record lets someone rebuild it."""

from __future__ import annotations

import subprocess
import tarfile
from pathlib import Path

import pytest

from numericos.core.errors import InvalidRequestError, NotAGitRepositoryError
from numericos.core.experiment import CodeSpec
from numericos.provenance import code
from tests.gitrepo import ENVIRONMENT, SOLVER, Repo

SOLVER_PATH = "examples/heat2d-python/heat2d.py"
REF = CodeSpec(mode="ref", ref="HEAD")
WORKING_TREE = CodeSpec(mode="working_tree")


def test_a_ref_is_fixed_to_a_commit_when_the_run_is_created(repo: Repo) -> None:
    baseline = repo.head

    record = code.resolve_at_submission(repo.root, REF, None)
    repo.write(SOLVER_PATH, SOLVER + "# later work\n")
    repo.commit("the branch moves on")

    assert record.mode == "ref"
    assert record.sha == baseline  # not the new HEAD
    assert record.requested_ref == "HEAD"
    assert record.commit is not None
    assert record.commit.subject == "baseline solver"
    assert record.dirty is False
    assert record.submitted_with_dirty_working_tree is False
    assert record.captured_at is not None
    assert record.repository_root == str(repo.root)


def test_uncommitted_changes_are_reported_but_are_not_what_a_ref_run_executes(repo: Repo) -> None:
    repo.write(SOLVER_PATH, SOLVER + "# not committed\n")

    record = code.resolve_at_submission(repo.root, REF, None)

    assert record.sha == repo.head
    assert record.dirty is False
    assert record.submitted_with_dirty_working_tree is True


def test_a_run_can_name_its_own_commit(repo: Repo) -> None:
    baseline = repo.head
    repo.write(SOLVER_PATH, SOLVER + "# candidate\n")
    candidate = repo.commit("candidate")

    assert code.resolve_at_submission(repo.root, REF, baseline[:12]).sha == baseline
    assert code.resolve_at_submission(repo.root, REF, "main").sha == candidate
    with pytest.raises(InvalidRequestError) as raised:
        code.resolve_at_submission(repo.root, REF, "no-such-ref")
    assert raised.value.details["errors"][0]["loc"] == ["body", "code_ref"]


def test_a_directory_that_is_not_a_work_tree_top_is_refused(repo: Repo, tmp_path: Path) -> None:
    plain = tmp_path / "plain"
    plain.mkdir()

    for root in (plain, repo.root / "examples"):
        with pytest.raises(NotAGitRepositoryError):
            code.resolve_at_submission(root, REF, None)


def test_a_working_tree_run_is_captured_when_it_starts_not_when_it_is_created(
    repo: Repo, tmp_path: Path
) -> None:
    record = code.resolve_at_submission(repo.root, WORKING_TREE, None)
    assert (record.mode, record.sha, record.dirty, record.captured_at) == (
        "working_tree",
        None,
        None,
        None,
    )
    with pytest.raises(InvalidRequestError, match="cannot be chosen"):
        code.resolve_at_submission(repo.root, WORKING_TREE, "main")

    captured = code.capture_working_tree(repo.root, record, tmp_path / "run")

    assert captured.sha == repo.head
    assert captured.dirty is False
    assert captured.diff_sha256 is None
    assert captured.untracked == []
    assert not (tmp_path / "run" / code.DIFF_FILE).exists()


def test_a_dirty_working_tree_can_be_rebuilt_from_its_record(repo: Repo, tmp_path: Path) -> None:
    repo.write(SOLVER_PATH, SOLVER + "print('uncommitted candidate')\n")
    repo.write("config/local.toml", "tolerance = 1e-9\n")  # untracked
    repo.write("ignored/cache.bin", "never part of the record")
    run_dir = tmp_path / "run"

    record = code.capture_working_tree(
        repo.root, code.resolve_at_submission(repo.root, WORKING_TREE, None), run_dir
    )

    assert record.sha == repo.head
    assert record.dirty is True
    assert record.diff_sha256 is not None
    assert record.diff_bytes == (run_dir / code.DIFF_FILE).stat().st_size
    assert [item.path for item in record.untracked] == ["config/local.toml"]
    assert record.untracked_archived is True

    # A third party: clone the commit, apply the patch, unpack the untracked files.
    rebuilt = tmp_path / "rebuilt"
    subprocess.run(
        ["git", "clone", "-q", str(repo.root), str(rebuilt)], env=ENVIRONMENT, check=True
    )
    subprocess.run(
        ["git", "-C", str(rebuilt), "checkout", "-q", record.sha], env=ENVIRONMENT, check=True
    )
    subprocess.run(
        ["git", "-C", str(rebuilt), "apply", "--binary", str(run_dir / code.DIFF_FILE)],
        env=ENVIRONMENT,
        check=True,
    )
    with tarfile.open(run_dir / code.UNTRACKED_ARCHIVE) as archive:
        archive.extractall(rebuilt, filter="data")
    for relative in (SOLVER_PATH, "config/local.toml"):
        assert (rebuilt / relative).read_text() == (repo.root / relative).read_text()
    assert not (rebuilt / "ignored").exists()


def test_untracked_files_beyond_the_size_limit_are_digested_but_not_stored(
    repo: Repo, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(code, "MAX_UNTRACKED_ARCHIVE_BYTES", 10)
    repo.write("big.dat", "x" * 100)

    record = code.capture_working_tree(
        repo.root, code.resolve_at_submission(repo.root, WORKING_TREE, None), tmp_path / "run"
    )

    assert record.untracked[0].size_bytes == 100
    assert len(record.untracked[0].sha256) == 64
    assert record.untracked_archived is False  # the record admits it is not self-sufficient
    assert not (tmp_path / "run" / code.UNTRACKED_ARCHIVE).exists()


def test_a_working_tree_is_changed_by_edits_to_tracked_files_not_by_new_files_beside_them(
    repo: Repo, tmp_path: Path
) -> None:
    repo.write(SOLVER_PATH, "edited before the run\n")
    submitted = code.resolve_at_submission(repo.root, CodeSpec(mode="working_tree"), None)
    started_with = code.capture_working_tree(repo.root, submitted, tmp_path / "run")
    unchanged = code.working_tree_changed(started_with)

    repo.write("output/field.dat", "written by the program\n")
    with_results = code.working_tree_changed(started_with)
    repo.write(SOLVER_PATH, "edited again while it ran\n")
    edited = code.working_tree_changed(started_with)

    assert (unchanged, with_results, edited) == (False, False, True)


def test_a_commit_made_during_a_working_tree_run_is_a_change(repo: Repo, tmp_path: Path) -> None:
    submitted = code.resolve_at_submission(repo.root, CodeSpec(mode="working_tree"), None)
    started_with = code.capture_working_tree(repo.root, submitted, tmp_path / "run")

    repo.write("README.md", "a new commit\n")
    repo.commit("meanwhile")

    assert code.working_tree_changed(started_with) is True


def test_nothing_is_said_about_a_run_of_an_exact_commit_or_an_unreadable_repository(
    repo: Repo, tmp_path: Path
) -> None:
    exact = code.resolve_at_submission(repo.root, CodeSpec(), None)
    submitted = code.resolve_at_submission(repo.root, CodeSpec(mode="working_tree"), None)
    started_with = code.capture_working_tree(repo.root, submitted, tmp_path / "run")
    moved_away = started_with.model_copy(update={"repository_root": str(tmp_path / "gone")})

    assert code.working_tree_changed(exact) is None
    assert code.working_tree_changed(moved_away) is None
