"""Which code a run executes, and the record that proves it."""

from __future__ import annotations

import hashlib
import tarfile
from pathlib import Path

from numericos.core.errors import InvalidRequestError, NotAGitRepositoryError
from numericos.core.experiment import CodeSpec
from numericos.core.provenance import CodeProvenance, FileDigest
from numericos.persistence.engine import utcnow
from numericos.provenance import git

#: Untracked files are stored with a working-tree run up to this total size.
MAX_UNTRACKED_ARCHIVE_BYTES = 64 * 1024 * 1024
DIFF_FILE = "code.diff"
UNTRACKED_ARCHIVE = "untracked.tar"


def file_digest(path: Path) -> tuple[str, int]:
    """SHA-256 and size of a file, read in chunks."""
    digest, size = hashlib.sha256(), 0
    with path.open("rb") as handle:
        while chunk := handle.read(1024 * 1024):
            digest.update(chunk)
            size += len(chunk)
    return digest.hexdigest(), size


def resolve_at_submission(root: Path, spec: CodeSpec, code_ref: str | None) -> CodeProvenance:
    """Fix what can be fixed when a run is created.

    In ``ref`` mode this is everything: the ref is resolved to a commit now, so the run executes
    that commit even if the branch moves before it starts. In ``working_tree`` mode the executed
    state is captured when the run starts (``capture_working_tree``).
    """
    if not git.is_toplevel(root):
        raise NotAGitRepositoryError(
            f"{root} is not the top directory of a Git work tree; runs need one to record "
            "exactly which code they execute",
            details={"root_path": str(root)},
        )
    base = CodeProvenance(
        mode=spec.mode,
        repository_root=str(root),
        remote_url=git.remote_url(root),
        submitted_with_dirty_working_tree=git.status(root).dirty,
    )
    if spec.mode == "working_tree":
        if code_ref is not None:
            raise InvalidRequestError(
                "this experiment runs the working tree; a code revision cannot be chosen",
                details={
                    "errors": [
                        {
                            "loc": ["body", "code_ref"],
                            "msg": "not allowed in working_tree mode",
                            "type": "not_allowed",
                        }
                    ]
                },
            )
        return base

    requested = code_ref or spec.ref
    try:
        sha = git.resolve_commit(root, requested)
    except git.UnknownRefError as error:
        raise InvalidRequestError(
            str(error),
            details={
                "errors": [{"loc": ["body", "code_ref"], "msg": str(error), "type": "unknown_ref"}]
            },
        ) from error
    return base.model_copy(
        update={
            "requested_ref": requested,
            "sha": sha,
            "commit": git.commit_info(root, sha),
            "dirty": False,
            "captured_at": utcnow(),
        }
    )


def capture_working_tree(root: Path, record: CodeProvenance, destination: Path) -> CodeProvenance:
    """Record the working tree a run is about to execute in place.

    The uncommitted changes to tracked files are stored as a binary patch against HEAD, the
    untracked files as digests and, up to a size limit, as an archive. Together with the commit
    they reproduce the executed tree; without the archive the record says so.
    """
    destination.mkdir(parents=True, exist_ok=True)
    sha = git.head(root)
    state = git.status(root)
    update: dict[str, object] = {
        "sha": sha,
        "commit": git.commit_info(root, sha) if sha else None,
        "dirty": state.dirty,
        "captured_at": utcnow(),
    }
    if sha and state.changed:
        patch = git.diff_against_head(root)
        (destination / DIFF_FILE).write_bytes(patch)
        update["diff_sha256"] = hashlib.sha256(patch).hexdigest()
        update["diff_bytes"] = len(patch)

    untracked = []
    for relative in state.untracked:
        path = root / relative
        if path.is_file() and not path.is_symlink():
            sha256, size = file_digest(path)
            untracked.append(FileDigest(path=relative, sha256=sha256, size_bytes=size))
    update["untracked"] = untracked
    if untracked:
        archived = sum(item.size_bytes for item in untracked) <= MAX_UNTRACKED_ARCHIVE_BYTES
        if archived:
            with tarfile.open(destination / UNTRACKED_ARCHIVE, "w") as archive:
                for item in untracked:
                    archive.add(root / item.path, arcname=item.path, recursive=False)
        update["untracked_archived"] = archived
    return record.model_copy(update=update)
