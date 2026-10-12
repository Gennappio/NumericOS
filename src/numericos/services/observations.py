"""What was observed of a run: its output, its resource samples and its files."""

from __future__ import annotations

from pathlib import Path

from numericos.core.enums import ACTIVE_RUN_STATUSES, RunStatus
from numericos.core.errors import ArtifactMissingError, InvalidRequestError, NotFoundError
from numericos.core.execution import LogLine, ResourceSample
from numericos.core.schemas import ArtifactList, ArtifactOut, LogPage, ResourcePage
from numericos.executor import layout
from numericos.observability import files
from numericos.persistence.unit_of_work import UnitOfWork
from numericos.services.guards import require_run

STREAM_NAMES = {"o": "stdout", "e": "stderr", "b": "build"}


def _ended(uow: UnitOfWork, run_id: str) -> bool:
    with uow:
        return RunStatus(require_run(uow, run_id).status) not in ACTIVE_RUN_STATUSES


def _start(path: Path, after: int | None, tail: int | None) -> int:
    if after is not None and tail is not None:
        raise InvalidRequestError(
            "give either a cursor or a tail, not both",
            details={
                "errors": [
                    {
                        "loc": ["query", "tail"],
                        "msg": "cannot be combined with after",
                        "type": "conflict",
                    }
                ]
            },
        )
    return files.tail_start(path, tail) if tail is not None else (after or 0)


def read_logs(
    uow: UnitOfWork,
    data_dir: Path,
    run_id: str,
    *,
    after: int | None,
    tail: int | None,
    limit: int,
    streams: set[str] | None,
) -> LogPage:
    """Output lines of a run in arrival order, from a cursor or from the last ``tail`` lines."""
    ended = _ended(uow, run_id)
    path = layout.run_dir(data_dir, run_id) / layout.OUTPUT
    records, cursor, at_end = files.read_after(path, _start(path, after, tail), limit)
    lines = [
        LogLine(
            t=record["t"],
            stream=STREAM_NAMES[record["s"]],
            text=record["l"],
            metric=bool(record.get("m")),
            cut=bool(record.get("x")),
        )
        for record in records
        if streams is None or STREAM_NAMES[record["s"]] in streams
    ]
    return LogPage(lines=lines, next_cursor=cursor, has_more=not at_end, complete=ended and at_end)


def read_resources(
    uow: UnitOfWork, data_dir: Path, run_id: str, *, after: int | None, tail: int | None, limit: int
) -> ResourcePage:
    """Samples of the run's process tree, from a cursor or from the last ``tail`` samples."""
    ended = _ended(uow, run_id)
    path = layout.run_dir(data_dir, run_id) / layout.RESOURCES
    records, cursor, at_end = files.read_after(path, _start(path, after, tail), limit)
    return ResourcePage(
        samples=[ResourceSample.model_validate(record) for record in records],
        next_cursor=cursor,
        has_more=not at_end,
        complete=ended and at_end,
    )


def list_artifacts(uow: UnitOfWork, run_id: str) -> ArtifactList:
    with uow:
        run = require_run(uow, run_id)
        return ArtifactList(
            artifacts=[
                ArtifactOut.model_validate(item) for item in uow.artifacts.list_for_run(run.id)
            ]
        )


def artifact_file(uow: UnitOfWork, data_dir: Path, artifact_id: str) -> tuple[Path, str]:
    """The file of an artifact and its media type. The file must be inside its run directory."""
    with uow:
        artifact = uow.artifacts.get(artifact_id)
        if artifact is None:
            raise NotFoundError(
                f"artifact {artifact_id} not found",
                details={"resource": "artifact", "id": artifact_id},
            )
        run_dir = layout.run_dir(data_dir, artifact.run_id)
        name, media_type = artifact.name, artifact.media_type
    path = (run_dir / name).resolve()
    if not path.is_relative_to(run_dir.resolve()) or not path.is_file():
        raise ArtifactMissingError(
            f"the file of artifact {artifact_id} is no longer in its run directory",
            details={"artifact_id": artifact_id, "name": name},
        )
    return path, media_type
