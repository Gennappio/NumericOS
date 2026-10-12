"""Read-only access to a project's Git repository.

No function here changes the repository: there is no checkout, reset, clean, stash, commit or
fetch, and ``GIT_OPTIONAL_LOCKS=0`` keeps ``git status`` from refreshing the index on disk.
Commands are argument vectors; a ref never reaches git as an option (``--end-of-options``).
"""

from __future__ import annotations

import os
import re
import shutil
import subprocess
import tarfile
import tempfile
import time
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

from numericos.core.provenance import CommitInfo

TIMEOUT_SECONDS = 120
_ENVIRONMENT = {
    "GIT_OPTIONAL_LOCKS": "0",
    "GIT_TERMINAL_PROMPT": "0",
    "GIT_PAGER": "cat",
    "LC_ALL": "C",
}


class GitError(Exception):
    """A git command failed; ``stderr`` holds what git said."""

    def __init__(self, message: str, stderr: str = "") -> None:
        super().__init__(f"{message}: {stderr.strip()}" if stderr.strip() else message)
        self.stderr = stderr


class UnknownRefError(GitError):
    def __init__(self, ref: str) -> None:
        super().__init__(f"{ref!r} does not name a commit of this repository")
        self.ref = ref


@dataclass(frozen=True)
class TreeStatus:
    """Uncommitted state of a working tree, as ``git status`` reports it."""

    changed: list[str] = field(default_factory=list)
    untracked: list[str] = field(default_factory=list)

    @property
    def dirty(self) -> bool:
        return bool(self.changed or self.untracked)


def _git(
    root: Path, *args: str, check: bool = True, stdin: bytes | None = None
) -> subprocess.CompletedProcess[bytes]:
    try:
        completed = subprocess.run(
            ["git", "-C", str(root), *args],
            capture_output=True,
            input=stdin,
            env={**os.environ, **_ENVIRONMENT},
            timeout=TIMEOUT_SECONDS,
            check=False,
        )
    except FileNotFoundError as error:
        raise GitError("git is not installed or not on PATH") from error
    except subprocess.TimeoutExpired as error:
        raise GitError(f"git {args[0]} did not finish in {TIMEOUT_SECONDS} s") from error
    if check and completed.returncode != 0:
        raise GitError(f"git {args[0]} failed", completed.stderr.decode(errors="replace"))
    return completed


def _text(completed: subprocess.CompletedProcess[bytes]) -> str:
    return completed.stdout.decode(errors="replace").strip()


def toplevel(path: Path) -> Path | None:
    """The top directory of the work tree that contains ``path``, or None outside a repository."""
    if not path.is_dir():
        return None
    completed = _git(path, "rev-parse", "--show-toplevel", check=False)
    return Path(_text(completed)) if completed.returncode == 0 else None


def is_toplevel(path: Path) -> bool:
    top = toplevel(path)
    return top is not None and top.resolve() == path.resolve()


def resolve_commit(root: Path, ref: str) -> str:
    """The full SHA of the commit ``ref`` names (a branch, tag, abbreviated or full SHA)."""
    completed = _git(
        root,
        "rev-parse",
        "--verify",
        "--quiet",
        "--end-of-options",
        f"{ref}^{{commit}}",
        check=False,
    )
    sha = _text(completed)
    if completed.returncode != 0 or not re.fullmatch(r"[0-9a-f]{40}", sha):
        raise UnknownRefError(ref)
    return sha


def head(root: Path) -> str | None:
    """SHA of HEAD, or None in a repository without commits."""
    try:
        return resolve_commit(root, "HEAD")
    except UnknownRefError:
        return None


def commit_info(root: Path, sha: str) -> CommitInfo:
    author, authored_at, subject = _text(
        _git(root, "show", "-s", "--format=%an%x00%aI%x00%s", sha)
    ).split("\x00", 2)
    return CommitInfo(
        subject=subject, author=author, authored_at=datetime.fromisoformat(authored_at)
    )


def status(root: Path) -> TreeStatus:
    """Changed tracked files and untracked (not ignored) files of the working tree."""
    output = _git(root, "status", "--porcelain=v1", "-z", "--untracked-files=all").stdout
    entries = output.decode(errors="surrogateescape").split("\x00")
    changed, untracked = [], []
    index = 0
    while index < len(entries):
        entry = entries[index]
        index += 1
        if len(entry) < 4:
            continue
        code, path = entry[:2], entry[3:]
        if code == "??":
            untracked.append(path)
            continue
        changed.append(path)
        if code[0] in "RC":  # a rename or copy is followed by its source path
            index += 1
    return TreeStatus(changed=sorted(changed), untracked=sorted(untracked))


def list_files(root: Path, patterns: list[str]) -> list[str]:
    """Paths of the files matching the patterns that are tracked, or new and not ignored."""
    output = _git(
        root, "ls-files", "-z", "--cached", "--others", "--exclude-standard", "--", *patterns
    ).stdout
    return sorted({path for path in output.decode(errors="surrogateescape").split("\x00") if path})


def working_files(root: Path) -> list[str]:
    """The files of the working tree that are tracked, or new and not ignored, and exist now
    as regular files (a tracked file that was deleted, or a submodule, is not listed)."""
    return [path for path in list_files(root, []) if (root / path).is_file()]


def index_hashes(root: Path) -> dict[str, str]:
    """The blob hash the index holds for every tracked file."""
    output = _git(root, "ls-files", "-s", "-z").stdout.decode(errors="surrogateescape")
    hashes: dict[str, str] = {}
    for entry in output.split("\x00"):
        meta, _, path = entry.partition("\t")
        fields = meta.split()
        if path and len(fields) == 3 and fields[2] == "0":
            hashes[path] = fields[1]
    return hashes


def hash_objects(root: Path, paths: list[str]) -> dict[str, str]:
    """The blob hash of the content each file has now. A path with a line break is left out:
    git reads the paths one per line."""
    usable = [path for path in paths if "\n" not in path]
    if not usable:
        return {}
    stdin = "".join(f"{path}\n" for path in usable).encode(errors="surrogateescape")
    output = _git(root, "hash-object", "--stdin-paths", stdin=stdin).stdout.decode()
    return dict(zip(usable, output.split(), strict=True))


#: Hashes of files that differ from the index, by what the file system says about them, so
#: that a large result file is read once and not on every listing.
_hash_cache: dict[tuple[str, str], tuple[int, int, str]] = {}


def content_hashes(root: Path, paths: list[str]) -> dict[str, str | None]:
    """The content hash of each path as it is now in the working tree; None if it is not a
    file. Tracked files that ``git status`` reports unchanged take their hash from the index;
    the others are hashed, once per size and modification time."""
    tracked = index_hashes(root)
    tree = status(root)
    different = set(tree.changed) | set(tree.untracked)
    result: dict[str, str | None] = {}
    to_hash: list[str] = []
    stats: dict[str, tuple[int, int]] = {}
    for path in paths:
        file = root / path
        try:
            stat = file.stat() if file.is_file() else None
        except OSError:
            stat = None
        if stat is None:
            result[path] = None
        elif path in tracked and path not in different:
            result[path] = tracked[path]
        else:
            cached = _hash_cache.get((str(root), path))
            stats[path] = (stat.st_size, stat.st_mtime_ns)
            if cached is not None and cached[:2] == stats[path]:
                result[path] = cached[2]
            else:
                to_hash.append(path)
    for path, sha in hash_objects(root, to_hash).items():
        result[path] = sha
        _hash_cache[(str(root), path)] = (*stats[path], sha)
    for path in to_hash:
        result.setdefault(path, None)
    return result


def diff_against_head(root: Path) -> bytes:
    """The uncommitted changes to tracked files as a binary patch (applies with ``git apply``)."""
    return _git(
        root, "diff", "HEAD", "--binary", "--no-color", "--no-ext-diff", "--no-textconv"
    ).stdout


def diff_between(root: Path, base: str, sha: str, max_bytes: int = 1_000_000) -> tuple[str, bool]:
    """Unified diff from ``base`` to ``sha`` and whether it was cut at ``max_bytes``."""
    output = _git(root, "diff", "--no-color", "--no-ext-diff", "--no-textconv", base, sha).stdout
    return output[:max_bytes].decode(errors="replace"), len(output) > max_bytes


def remote_url(root: Path) -> str | None:
    """URL of ``origin`` without any embedded credentials, or None."""
    completed = _git(root, "config", "--get", "remote.origin.url", check=False)
    url = _text(completed)
    if completed.returncode != 0 or not url:
        return None
    return re.sub(r"^([a-z][a-z0-9+.-]*://)[^/@]+@", r"\1", url)


def export(root: Path, sha: str, destination: Path) -> None:
    """Write the tree of commit ``sha`` to ``destination``, which must not exist yet.

    The files come from ``git archive``: exactly what the commit contains, nothing from the
    working tree. Submodules and Git LFS content are therefore not included. The export is
    assembled next to the destination and renamed, so a half-written tree is never visible.
    Every file gets the time of the export as its modification time, so whatever is written
    or changed later can be told apart from the commit's own files.
    """
    if destination.exists():
        raise GitError(f"{destination} already exists")
    destination.parent.mkdir(parents=True, exist_ok=True)
    staging = Path(tempfile.mkdtemp(prefix=".export-", dir=destination.parent))
    try:
        process = subprocess.Popen(
            ["git", "-C", str(root), "archive", "--format=tar", sha],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            env={**os.environ, **_ENVIRONMENT},
        )
        assert process.stdout is not None and process.stderr is not None
        try:
            exported_at = time.time()
            with tarfile.open(fileobj=process.stdout, mode="r|") as archive:
                for member in archive:
                    member.mtime = exported_at
                    archive.extract(member, staging, filter="data")
        except tarfile.TarError as error:
            process.kill()
            raise GitError(f"could not unpack the archive of {sha}: {error}") from error
        finally:
            stderr = process.stderr.read().decode(errors="replace")
            process.wait()
        if process.returncode != 0:
            raise GitError(f"git archive of {sha} failed", stderr)
        staging.rename(destination)
    finally:
        shutil.rmtree(staging, ignore_errors=True)
