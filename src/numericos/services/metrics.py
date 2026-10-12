"""The scientific metrics of a run: their summaries, their samples and how far they reach."""

from __future__ import annotations

import math
from pathlib import Path
from typing import Any

from numericos.core.enums import ACTIVE_RUN_STATUSES, RunStatus
from numericos.core.errors import NotFoundError
from numericos.core.experiment import ExperimentProtocol
from numericos.core.metrics import (
    DIAGNOSTIC_MESSAGES,
    Diagnostic,
    MetricBucket,
    MetricOverview,
    MetricPage,
    MetricSample,
    RunMetrics,
    SeriesSummary,
)
from numericos.executor import layout
from numericos.observability import files
from numericos.observability.coverage import build_coverage
from numericos.persistence.unit_of_work import UnitOfWork
from numericos.services.guards import require_experiment, require_run
from numericos.services.observations import cursor_start


def run_metrics(uow: UnitOfWork, run_id: str) -> RunMetrics:
    """Every series of a run with its summary, and the coverage of the run."""
    with uow:
        run = require_run(uow, run_id)
        experiment = require_experiment(uow, run.experiment_id)
        protocol = ExperimentProtocol.model_validate(experiment.protocol)
        series = [
            SeriesSummary.model_validate(row) for row in uow.metric_series.list_for_run(run.id)
        ]
        report = dict(run.metric_report or {})
        coverage = build_coverage(
            protocol,
            series,
            report,
            started=run.started_at is not None,
            active=RunStatus(run.status) in ACTIVE_RUN_STATUSES,
        )
    return RunMetrics(
        series=series,
        coverage=coverage,
        records=int(report.get("records", 0)),
        parsed_lines=int(report.get("parsed_lines", 0)),
        program_events=int(report.get("program_events", 0)),
        truncated=bool(report.get("truncated", False)),
        diagnostics=[
            Diagnostic(message=DIAGNOSTIC_MESSAGES.get(item["kind"], item["kind"]), **item)
            for item in report.get("diagnostics", [])
        ],
    )


def _series_file(uow: UnitOfWork, data_dir: Path, run_id: str, name: str) -> tuple[Path, bool]:
    """The file of a series and whether its run has ended. The series must exist: in the
    database, or already on disk while the supervisor has not recorded it yet."""
    with uow:
        run = require_run(uow, run_id)
        ended = RunStatus(run.status) not in ACTIVE_RUN_STATUSES
        known = uow.metric_series.get(run.id, name) is not None
    path = layout.run_dir(data_dir, run_id) / layout.METRICS / f"{name}.jsonl"
    if not known and not path.is_file():
        raise NotFoundError(
            f"run {run_id} has no metric {name!r}",
            details={"resource": "metric", "id": name, "run_id": run_id},
        )
    return path, ended


def _sample(record: dict[str, Any]) -> MetricSample:
    return MetricSample(
        t=record["t"],
        value=record["v"],
        non_finite=record.get("nf"),
        step=record.get("s"),
        time=record.get("x"),
        source_timestamp=record.get("ts"),
    )


def read_metric(
    uow: UnitOfWork,
    data_dir: Path,
    run_id: str,
    name: str,
    *,
    after: int | None,
    tail: int | None,
    limit: int,
) -> MetricPage:
    """Samples of one metric in the order they arrived, from a cursor or from the last ones."""
    path, ended = _series_file(uow, data_dir, run_id, name)
    records, cursor, at_end = files.read_after(path, cursor_start(path, after, tail), limit)
    return MetricPage(
        samples=[_sample(record) for record in records],
        next_cursor=cursor,
        has_more=not at_end,
        complete=ended and at_end,
    )


class _Bucket:
    """Accumulates consecutive samples."""

    def __init__(self, first: dict[str, Any]) -> None:
        self.first = self.last = first
        self.samples = self.non_finite = 0
        self.low: float | None = None
        self.high: float | None = None

    def add(self, record: dict[str, Any]) -> None:
        self.last = record
        self.samples += 1
        value = record["v"]
        if value is None:
            self.non_finite += 1
            return
        self.low = value if self.low is None else min(self.low, value)
        self.high = value if self.high is None else max(self.high, value)

    def done(self) -> MetricBucket:
        return MetricBucket(
            samples=self.samples,
            non_finite=self.non_finite,
            first_step=self.first.get("s"),
            last_step=self.last.get("s"),
            first_time=self.first.get("x"),
            last_time=self.last.get("x"),
            first_t=self.first["t"],
            last_t=self.last["t"],
            first_value=self.first["v"],
            last_value=self.last["v"],
            min_value=self.low,
            max_value=self.high,
        )


def metric_overview(
    uow: UnitOfWork, data_dir: Path, run_id: str, name: str, *, buckets: int
) -> MetricOverview:
    """The whole series in at most ``buckets`` stretches of consecutive samples.

    Each stretch keeps its first and last sample, its extremes and how many of its samples
    were not finite, so a chart of a million samples shows every spike and every NaN. The file
    is read as a stream, twice: once to count, once to reduce.
    """
    path, ended = _series_file(uow, data_dir, run_id, name)
    total, end = files.complete_extent(path)
    size = max(1, math.ceil(total / buckets))
    reduced: list[MetricBucket] = []
    current: _Bucket | None = None
    for record in files.iter_records(path, end):
        if current is None:
            current = _Bucket(record)
        current.add(record)
        if current.samples == size:
            reduced.append(current.done())
            current = None
    if current is not None:
        reduced.append(current.done())
    return MetricOverview(
        name=name,
        samples=total,
        buckets=reduced,
        next_cursor=end,
        complete=ended and end == files.file_size(path),
    )
