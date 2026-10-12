"""Content hashes of the working tree: what a description is compared with to tell whether
the file it describes has changed."""

from __future__ import annotations

from numericos.provenance import git
from tests.gitrepo import Repo

SOLVER = "examples/heat2d-python/heat2d.py"


def test_working_files_are_tracked_or_new_and_exist(repo: Repo) -> None:
    repo.write("notes.md", "new\n")
    repo.write("ignored/cache.bin", "x")
    repo.write("run.log", "x")
    (repo.root / ".gitignore").unlink()  # tracked, deleted in the working tree

    listed = git.working_files(repo.root)

    assert SOLVER in listed and "notes.md" in listed
    assert ".gitignore" not in listed  # gone: nothing to describe
    # Without the .gitignore the formerly ignored files are simply new files.
    assert "run.log" in listed


def test_ignored_files_are_not_listed(repo: Repo) -> None:
    repo.write("ignored/cache.bin", "x")
    repo.write("run.log", "x")

    assert git.working_files(repo.root) == [".gitignore", SOLVER]


def test_hashes_follow_the_content_not_the_commit(repo: Repo) -> None:
    committed = git.content_hashes(repo.root, [SOLVER])[SOLVER]
    assert committed == repo.git("rev-parse", f"HEAD:{SOLVER}")  # unchanged: from the index

    repo.write(SOLVER, "print('edited')\n")
    repo.write("new.py", "print('new')\n")
    hashes = git.content_hashes(repo.root, [SOLVER, "new.py", "missing.py", "examples"])

    assert hashes[SOLVER] != committed
    assert hashes[SOLVER] == repo.git("hash-object", SOLVER)
    assert hashes["new.py"] == repo.git("hash-object", "new.py")
    assert hashes["missing.py"] is None
    assert hashes["examples"] is None  # a directory is not a file

    repo.git("checkout", "--", SOLVER)
    assert git.content_hashes(repo.root, [SOLVER])[SOLVER] == committed


def test_a_changed_file_is_hashed_again_only_when_it_changes(
    repo: Repo, monkeypatch: object
) -> None:
    repo.write("big.dat", "1 2 3\n")
    first = git.content_hashes(repo.root, ["big.dat"])
    calls: list[list[str]] = []
    real = git.hash_objects

    def counting(root: object, paths: list[str]) -> dict[str, str]:
        calls.append(paths)
        return real(root, paths)  # type: ignore[arg-type]

    monkeypatch.setattr(git, "hash_objects", counting)  # type: ignore[attr-defined]
    again = git.content_hashes(repo.root, ["big.dat"])
    repo.write("big.dat", "1 2 3 4 5 6\n")
    changed = git.content_hashes(repo.root, ["big.dat"])

    assert again == first
    assert calls == [[], ["big.dat"]]  # nothing to hash the second time; once after the edit
    assert changed["big.dat"] != first["big.dat"]
