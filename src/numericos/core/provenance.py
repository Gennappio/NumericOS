"""What a run records about the code, inputs and environment it was executed with."""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field


class CommitInfo(BaseModel):
    subject: str
    author: str
    authored_at: datetime


class FileDigest(BaseModel):
    path: str
    sha256: str
    size_bytes: int


class CodeProvenance(BaseModel):
    """The exact code of a run.

    ``ref`` mode: ``sha`` is fixed when the run is created and the run executes an export of
    that commit, so it is clean by construction. ``working_tree`` mode: the state is captured
    when the run starts; ``sha`` is then the commit under the working tree and ``diff_sha256``
    identifies the uncommitted changes that were executed with it.
    """

    mode: Literal["ref", "working_tree"]
    repository_root: str
    remote_url: str | None = None
    requested_ref: str | None = Field(default=None, description="As asked for, e.g. 'HEAD'.")
    sha: str | None = Field(default=None, description="Full commit SHA of the executed code.")
    commit: CommitInfo | None = None
    dirty: bool | None = Field(
        default=None, description="Executed with uncommitted changes. Null until the run starts."
    )
    diff_sha256: str | None = Field(
        default=None, description="SHA-256 of the executed uncommitted changes (a binary patch)."
    )
    diff_bytes: int | None = None
    untracked: list[FileDigest] = Field(
        default_factory=list, description="Untracked files that were part of the executed tree."
    )
    untracked_archived: bool | None = Field(
        default=None, description="Whether the untracked files were small enough to be stored."
    )
    submitted_with_dirty_working_tree: bool = Field(
        description="The project directory had uncommitted changes when the run was created. "
        "In ref mode they are not part of the run."
    )
    captured_at: datetime | None = Field(
        default=None, description="When the executed state was fixed."
    )
    changed_during_run: bool | None = Field(
        default=None,
        description=(
            "working_tree mode only: the tree was modified while the program ran, so the record "
            "describes what the program started with, not everything it may have read."
        ),
    )


class InputRecord(BaseModel):
    path: str
    base: Literal["code", "project"]
    sha256: str
    size_bytes: int


class ExecutableRecord(BaseModel):
    """The program file that ``argv[0]`` resolved to when the program was started, that is
    after any build command: for a compiled program it identifies the binary that ran."""

    argv0: str
    path: str | None = Field(
        description="Null until the program starts, and when it could not be resolved."
    )
    sha256: str | None = None
    size_bytes: int | None = None


class ProbeRecord(BaseModel):
    """Output of one environment probe command, kept as an artifact."""

    argv: list[str]
    exit_code: int | None = Field(description="Null when the command could not be run.")
    seconds: float
    output_sha256: str | None = None
    output_file: str | None = None
    error: str | None = None


class HostFacts(BaseModel):
    platform: str
    machine: str
    processor: str
    cpu_count_logical: int | None
    cpu_count_physical: int | None
    memory_total_bytes: int
    hostname: str
    python: str = Field(description="The interpreter of the NumericOS supervisor, not of the run.")
    numericos: str


class EnvironmentRecord(BaseModel):
    host: HostFacts
    executable: ExecutableRecord
    probes: list[ProbeRecord] = Field(default_factory=list)
    variables: dict[str, str] = Field(
        default_factory=dict,
        description="Environment of the run. Values of names that look like secrets are redacted.",
    )
