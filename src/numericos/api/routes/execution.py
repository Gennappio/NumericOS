"""Observing and controlling runs: output, resources, events, files, cancellation, supervisors."""

from __future__ import annotations

from typing import Annotated, Any, Literal

from fastapi import APIRouter, Path, Query, Request
from fastapi.responses import FileResponse

from numericos.api.deps import Context, Uow
from numericos.core.experiment import METRIC_NAME
from numericos.core.metrics import MetricOverview, MetricPage, RunMetrics
from numericos.core.schemas import (
    ArtifactList,
    ErrorEnvelope,
    EventPage,
    LogPage,
    ResourcePage,
    RunCancel,
    RunList,
    RunOut,
    WorkerList,
)
from numericos.services import events, metrics, observations, runs, workers
from numericos.services.guards import require_run

router = APIRouter()

After = Annotated[
    int | None, Query(ge=0, description="Cursor returned by the previous page (a byte offset).")
]
Tail = Annotated[
    int | None,
    Query(ge=1, le=10000, description="Start from the last N records instead of a cursor."),
]
CURSOR_RESPONSES: dict[int | str, dict[str, Any]] = {
    409: {"model": ErrorEnvelope, "description": "The cursor is beyond what is recorded"},
}
MetricNameInPath = Annotated[str, Path(pattern=METRIC_NAME, description="Name of the metric.")]


@router.get(
    "/projects/{project_id}/runs",
    tags=["runs"],
    summary="The newest runs of a project across its experiments",
)
def list_project_runs(
    project_id: str, uow: Uow, limit: Annotated[int, Query(ge=1, le=500)] = 50
) -> RunList:
    return runs.list_project_runs(uow, project_id, limit)


@router.post(
    "/runs/{run_id}:cancel",
    tags=["runs"],
    summary="Ask for a run to be stopped; returns at once",
)
def cancel_run(
    run_id: str, uow: Uow, context: Context, request: Request, body: RunCancel | None = None
) -> RunOut:
    return runs.cancel_run(
        uow, run_id, body or RunCancel(), context, data_dir=request.app.state.settings.data_dir
    )


@router.get(
    "/runs/{run_id}/logs",
    tags=["observability"],
    summary="Output lines of a run with arrival time and stream, by cursor",
    responses=CURSOR_RESPONSES,
)
def read_logs(
    run_id: str,
    uow: Uow,
    request: Request,
    after: After = None,
    tail: Tail = None,
    limit: Annotated[int, Query(ge=1, le=5000)] = 1000,
    stream: Annotated[
        list[Literal["stdout", "stderr", "build"]] | None,
        Query(description="Only these streams. Repeat the parameter for several."),
    ] = None,
) -> LogPage:
    return observations.read_logs(
        uow,
        request.app.state.settings.data_dir,
        run_id,
        after=after,
        tail=tail,
        limit=limit,
        streams=set(stream) if stream else None,
    )


@router.get(
    "/runs/{run_id}/resources",
    tags=["observability"],
    summary="Samples of the run's process tree (CPU, memory, processes), by cursor",
    responses=CURSOR_RESPONSES,
)
def read_resources(
    run_id: str,
    uow: Uow,
    request: Request,
    after: After = None,
    tail: Tail = None,
    limit: Annotated[int, Query(ge=1, le=5000)] = 1000,
) -> ResourcePage:
    return observations.read_resources(
        uow, request.app.state.settings.data_dir, run_id, after=after, tail=tail, limit=limit
    )


@router.get(
    "/runs/{run_id}/metrics",
    tags=["observability"],
    summary="The metrics of a run in short, and how far its observation reaches",
)
def get_run_metrics(run_id: str, uow: Uow) -> RunMetrics:
    return metrics.run_metrics(uow, run_id)


@router.get(
    "/runs/{run_id}/metrics/{name}",
    tags=["observability"],
    summary="Samples of one metric in arrival order, by cursor",
    responses=CURSOR_RESPONSES,
)
def read_metric(
    run_id: str,
    name: MetricNameInPath,
    uow: Uow,
    request: Request,
    after: After = None,
    tail: Tail = None,
    limit: Annotated[int, Query(ge=1, le=5000)] = 1000,
) -> MetricPage:
    return metrics.read_metric(
        uow, request.app.state.settings.data_dir, run_id, name, after=after, tail=tail, limit=limit
    )


@router.get(
    "/runs/{run_id}/metrics/{name}/overview",
    tags=["observability"],
    summary="A whole series reduced to a bounded number of buckets, for charts",
)
def get_metric_overview(
    run_id: str,
    name: MetricNameInPath,
    uow: Uow,
    request: Request,
    buckets: Annotated[int, Query(ge=10, le=2000)] = 400,
) -> MetricOverview:
    return metrics.metric_overview(
        uow, request.app.state.settings.data_dir, run_id, name, buckets=buckets
    )


@router.get(
    "/runs/{run_id}/events",
    tags=["observability"],
    summary="Ledger events of one run, in sequence order",
)
def list_run_events(
    run_id: str,
    uow: Uow,
    after: Annotated[int | None, Query(ge=0)] = None,
    limit: Annotated[int, Query(ge=1, le=1000)] = 200,
    order: Annotated[Literal["asc", "desc"], Query()] = "asc",
) -> EventPage:
    with uow:
        project_id = require_run(uow, run_id).project_id
    return events.list_events(
        uow, project_id, after=after, limit=limit, descending=order == "desc", run_id=run_id
    )


@router.get(
    "/runs/{run_id}/artifacts",
    tags=["observability"],
    summary="Files of a finished run with size and checksum",
)
def list_artifacts(run_id: str, uow: Uow) -> ArtifactList:
    return observations.list_artifacts(uow, run_id)


@router.get(
    "/artifacts/{artifact_id}/content",
    tags=["observability"],
    summary="Download one artifact",
    response_class=FileResponse,
    responses={
        200: {
            "description": "The file, served with its own media type",
            "content": {
                "application/octet-stream": {"schema": {"type": "string", "format": "binary"}}
            },
        },
        409: {"model": ErrorEnvelope, "description": "The file is no longer in its run directory"},
    },
)
def download_artifact(artifact_id: str, uow: Uow, request: Request) -> FileResponse:
    path, media_type = observations.artifact_file(
        uow, request.app.state.settings.data_dir, artifact_id
    )
    return FileResponse(path, media_type=media_type, filename=path.name)


@router.get(
    "/workers",
    tags=["observability"],
    summary="Supervisor processes and whether any is alive to start queued runs",
)
def list_workers(uow: Uow) -> WorkerList:
    return workers.list_workers(uow)
