"""The supervisor process.

A worker serves the queue. It prepares and starts a monitor for every queued run it has
capacity for, turns what the monitors write into run state and ledger events, and takes over
the runs of workers that are gone. It keeps nothing about a run only in memory: a worker can
stop at any moment without stopping a run, and any worker can continue from the files.

Two rules keep several workers and the API out of each other's way. Files and Git are read
between database transactions, never inside one, so that hashing the results of a run does not
keep anybody from writing. And every write is fenced: it is applied only if the run still
belongs to this worker and is still as this worker found it.
"""

from __future__ import annotations

import logging
import os
import socket
import subprocess
import threading
import time
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Literal, TypeGuard

from sqlalchemy.exc import OperationalError

from numericos import __version__
from numericos.config import Settings
from numericos.core.enums import EventType, FailureClass, RunStatus, Severity
from numericos.core.execution import ResourceSample, ResourceSummary, RunOutcome
from numericos.core.experiment import ExperimentProtocol, render_build
from numericos.core.ids import new_id
from numericos.core.provenance import CodeProvenance
from numericos.events.ledger import EventContext, build_event
from numericos.events.notifier import EventNotifier
from numericos.executor import artifacts, control, launch, layout
from numericos.executor.liveness import WORKER_STALE_SECONDS, process_alive, worker_alive
from numericos.executor.outcome import classify
from numericos.observability import files
from numericos.persistence.engine import (
    TIMESTAMP_FORMAT,
    make_engine,
    make_session_factory,
    utcnow,
)
from numericos.persistence.models import Artifact, Event, MetricSeries, Run
from numericos.persistence.models import Worker as WorkerRow
from numericos.persistence.unit_of_work import UnitOfWork
from numericos.provenance.code import working_tree_changed

ACTIVE = (RunStatus.STARTING.value, RunStatus.RUNNING.value)
PENDING = (RunStatus.QUEUED.value, *ACTIVE)
#: A claimed run whose monitor never appeared is given this long before it is queued again.
STARTUP_GRACE_SECONDS = 10.0
MONITOR_GONE = "the monitor process is gone: how the program ends will not be recorded"
#: A status reason is one line for people; the details stay in the run's files and events.
REASON_MAX = 300

log = logging.getLogger("numericos.worker")

#: What the monitor notes in its journal that belongs in the ledger, with its severity.
JOURNAL_EVENTS = {
    "limit_exceeded": (EventType.RUN_LIMIT_EXCEEDED, Severity.ERROR),
    "output_truncated": (EventType.RUN_OUTPUT_TRUNCATED, Severity.WARNING),
    "leftover_processes": (EventType.RUN_LEFTOVER_PROCESSES, Severity.WARNING),
    # A NaN or an infinity in a metric is a hard event whatever the contract does about it.
    "metric_non_finite": (EventType.RUN_METRIC_NON_FINITE, Severity.ERROR),
    "metrics_truncated": (EventType.RUN_METRICS_TRUNCATED, Severity.WARNING),
}


def journal_event(entry: dict[str, Any]) -> tuple[EventType, Severity] | None:
    """The ledger event a journal entry of the monitor becomes, if it becomes one."""
    kind = entry["type"]
    if kind == "guardrail_violated":
        stops = entry.get("action") == "halt"
        return EventType.RUN_GUARDRAIL_VIOLATED, Severity.ERROR if stops else Severity.WARNING
    if kind == "program_event":
        return EventType.RUN_PROGRAM_EVENT, Severity(entry.get("severity", "info"))
    return JOURNAL_EVENTS.get(kind)


def parse_stamp(value: str) -> datetime:
    return datetime.strptime(value, TIMESTAMP_FORMAT).replace(tzinfo=UTC)


def clip(reason: str | None) -> str | None:
    if reason is None:
        return None
    line = " ".join(reason.split())
    return line if len(line) <= REASON_MAX else line[: REASON_MAX - 1] + "…"


def last_line(path: Path) -> str:
    """The last non-empty line of a text file; empty when there is none."""
    try:
        lines = path.read_text(errors="replace").splitlines()
    except FileNotFoundError:
        return ""
    return next((line.strip() for line in reversed(lines) if line.strip()), "")


@dataclass(frozen=True)
class Reading:
    """What the files of a run say at one moment, beyond what the database already holds."""

    identity: dict[str, Any] | None
    started: dict[str, Any] | None
    monitor_alive: bool
    program_alive: bool
    outcome: RunOutcome | None
    journal: list[dict[str, Any]]
    samples: list[dict[str, Any]]
    #: The monitor's summary of the metrics, when it has changed since the last reading.
    metrics: dict[str, Any] | None
    offsets: dict[str, int]


def read_run_files(run_dir: Path, offsets: dict[str, Any]) -> Reading:
    """Read what a monitor wrote since ``offsets``.

    The order matters. Liveness comes before the outcome: a monitor that ends between the two
    has written its outcome, and must not be taken for one that vanished. The outcome comes
    before the journal, the samples and the metric summary: once it exists the monitor has
    closed them, so they are read complete.
    """
    identity = layout.read_json(run_dir / layout.MONITOR)
    monitor_alive = identity is not None and process_alive(identity["pid"], identity["create_time"])
    started = layout.read_json(run_dir / layout.STARTED)
    program_alive = started is not None and process_alive(started["pid"], started["create_time"])
    document = layout.read_json(run_dir / layout.EXIT)
    journal, journal_cursor = files.read_to_end(
        run_dir / layout.JOURNAL, int(offsets.get("journal", 0))
    )
    samples, resources_cursor = files.read_to_end(
        run_dir / layout.RESOURCES, int(offsets.get("resources", 0))
    )
    summary = layout.read_json(run_dir / layout.METRICS_SUMMARY)
    seen_revision = int(offsets.get("metrics", -1))  # -1: no summary was read yet
    revision = int(summary["revision"]) if summary is not None else seen_revision
    return Reading(
        identity=identity,
        started=started,
        monitor_alive=monitor_alive,
        program_alive=program_alive,
        outcome=RunOutcome.model_validate(document) if document is not None else None,
        journal=journal,
        samples=samples,
        metrics=summary if revision != seen_revision else None,
        offsets={"journal": journal_cursor, "resources": resources_cursor, "metrics": revision},
    )


@dataclass(frozen=True)
class Verdict:
    """What follows from a reading for a run that is still open in the database."""

    kind: Literal["continue", "finished", "failed", "lost", "requeue", "monitor_lost"]
    reason: str = ""

    @property
    def ends(self) -> bool:
        return self.kind in ("finished", "failed", "lost")


@dataclass(frozen=True)
class Leftovers:
    """What a run leaves behind, examined before the transaction that records its end."""

    found: list[artifacts.Found]
    left_out: int
    source_changed: bool | None


class Worker:
    def __init__(
        self,
        settings: Settings,
        *,
        max_parallel: int = 1,
        poll_interval: float = 0.5,
        heartbeat_interval: float = 2.0,
        stale_after: float = WORKER_STALE_SECONDS,
    ) -> None:
        self.settings = settings
        self.id = new_id("wrk")
        self.max_parallel = max_parallel
        self.poll_interval = poll_interval
        self.heartbeat_interval = heartbeat_interval
        self.stale_after = stale_after
        self.engine = make_engine(settings.db_path)
        self._sessions = make_session_factory(self.engine)
        self._notifier = EventNotifier()  # nobody subscribes here; the API finds the events
        self._monitors: dict[str, subprocess.Popen[bytes]] = {}
        self._leaving = threading.Event()
        self._heart: threading.Thread | None = None

    def _uow(self) -> UnitOfWork:
        return UnitOfWork(self._sessions, self._notifier)

    def _run_dir(self, run_id: str) -> Path:
        return layout.run_dir(self.settings.data_dir, run_id)

    def _mine(self, run: Run | None) -> TypeGuard[Run]:
        """The run is open and this worker is the one responsible for it."""
        return run is not None and run.status in ACTIVE and run.worker_id == self.id

    def _event(
        self,
        run: Run,
        event_type: EventType,
        payload: dict[str, Any],
        severity: Severity = Severity.INFO,
    ) -> Event:
        context = EventContext(
            actor=f"worker:{self.id}",
            correlation_id=run.correlation_id or new_id("cor"),
            producer="worker",
        )
        return build_event(
            event_type=event_type,
            project_id=run.project_id,
            subject_id=run.id,
            run_id=run.id,
            payload=payload,
            context=context,
            severity=severity,
        )

    # ------------------------------------------------------------------ lifecycle

    def start(self) -> None:
        """Register this worker, so that others and the API can tell it is alive."""
        now = utcnow()
        with self._uow() as uow:
            uow.workers.add(
                WorkerRow(
                    id=self.id,
                    pid=os.getpid(),
                    hostname=socket.gethostname(),
                    version=__version__,
                    max_parallel_runs=self.max_parallel,
                    started_at=now,
                    heartbeat_at=now,
                )
            )
            uow.commit()
        self._heart = threading.Thread(
            target=self._beat, name="numericos-worker-heartbeat", daemon=True
        )
        self._heart.start()

    def _beat(self) -> None:
        """Say "alive" at a steady pace, on a thread of its own.

        Preparing a run or hashing its results can take longer than the patience other workers
        have with a silent one. A busy worker must not be taken for a dead one.
        """
        while not self._leaving.wait(self.heartbeat_interval):
            try:
                with self._uow() as uow:
                    row = uow.workers.get(self.id)
                    if row is not None:
                        row.heartbeat_at = utcnow()
                        uow.commit()
            except OperationalError as error:
                log.warning("heartbeat not written, the next one follows: %s", error.orig)

    def stop(self) -> None:
        """Leave. Runs keep going under their monitors; another worker will take them over."""
        self._leaving.set()
        if self._heart is not None:
            self._heart.join(timeout=10)
            self._heart = None
        with self._uow() as uow:
            row = uow.workers.get(self.id)
            if row is not None and row.stopped_at is None:
                row.stopped_at = utcnow()
                uow.commit()
        self.engine.dispose()

    def run_forever(self, should_stop: Callable[[], bool]) -> None:
        """Serve until told to stop.

        A database that stays busy longer than the busy timeout does not end the supervisor:
        every step of a round is its own transaction, so the next round simply repeats it.
        """
        while not should_stop():
            try:
                self.tick()
            except OperationalError as error:
                if "database is locked" not in str(error):
                    raise
                log.warning("the database is busy; trying again")
            time.sleep(self.poll_interval)

    def run_until_idle(self, timeout: float = 300.0) -> None:
        """Serve until no run is queued or active any more."""
        deadline = time.monotonic() + timeout
        while True:
            self.tick()
            with self._uow() as uow:
                remaining = uow.runs.with_status(PENDING, limit=1)
            if not remaining:
                return
            if time.monotonic() > deadline:
                raise TimeoutError(f"runs were still pending after {timeout} s")
            time.sleep(self.poll_interval)

    def tick(self) -> None:
        """One round: take over orphans, read the monitors, start queued runs."""
        for run_id in [
            name for name, process in self._monitors.items() if process.poll() is not None
        ]:
            if not (self._run_dir(run_id) / layout.MONITOR).exists():
                continue  # it ended before naming itself: _ingest reports that, with this handle
            del self._monitors[run_id]
        self._adopt_orphans()
        for run_id in self._owned(ACTIVE):
            self._ingest(run_id)
        capacity = self.max_parallel - len(self._owned(ACTIVE))
        for _ in range(max(0, capacity)):
            claimed = self._claim_next()
            if claimed is None:
                break
            self._launch(claimed)

    def _owned(self, statuses: tuple[str, ...]) -> list[str]:
        with self._uow() as uow:
            return [run.id for run in uow.runs.with_status(statuses) if run.worker_id == self.id]

    # ------------------------------------------------------------------ orphans

    def _adopt_orphans(self) -> None:
        """Take over active runs whose worker stopped or went silent."""
        with self._uow() as uow:
            now = utcnow()
            adopted = False
            for run in uow.runs.with_status(ACTIVE):
                if run.worker_id == self.id:
                    continue
                owner = uow.workers.get(run.worker_id) if run.worker_id else None
                if worker_alive(owner, now, self.stale_after):
                    continue
                uow.record(
                    self._event(
                        run,
                        EventType.RUN_ADOPTED,
                        {"previous_worker_id": run.worker_id, "worker_id": self.id},
                    )
                )
                log.warning("run %s: taken over from worker %s", run.id, run.worker_id)
                run.worker_id = self.id
                adopted = True
            if adopted:
                uow.commit()

    # ------------------------------------------------------------------ launching

    def _claim_next(self) -> str | None:
        """Take the oldest queued run. Claims are serialised by the database."""
        with self._uow() as uow:
            queued = uow.runs.with_status((RunStatus.QUEUED.value,), limit=1)
            if not queued:
                return None
            run = queued[0]
            run.status = RunStatus.STARTING.value
            run.worker_id = self.id
            run.version += 1
            run.updated_at = utcnow()
            uow.commit()
            return run.id

    def _launch(self, run_id: str) -> None:
        with self._uow() as uow:
            run = uow.runs.get(run_id)
            if not self._mine(run):
                return
            experiment = uow.experiments.get(run.experiment_id)
            project = uow.projects.get(run.project_id)
            assert experiment is not None and project is not None
            protocol = ExperimentProtocol.model_validate(experiment.protocol)
            argv = list(run.argv)
            build = render_build(protocol, run.parameters, run.seed)
            record = CodeProvenance.model_validate(run.code)
            cancelled = run.cancel_requested_at is not None
            root = project.root_path if project.execution_trusted_at is not None else None

        if cancelled:
            self._end_unstarted(run_id, RunStatus.CANCELLED, None, "cancelled before it started")
            return
        try:
            if root is None:
                raise launch.LaunchError(
                    FailureClass.INFRASTRUCTURE,
                    "trust to execute in the project directory was withdrawn before the start",
                )
            prepared = launch.prepare(
                run_dir=self._run_dir(run_id),
                run_id=run_id,
                root=Path(root),
                protocol=protocol,
                argv=argv,
                build=build,
                record=record,
            )
        except launch.LaunchError as error:
            self._end_unstarted(run_id, RunStatus.FAILED, error.failure_class, error.reason)
            return
        except OSError as error:
            # The boundary of one run: a full disk or an unreadable directory fails this run,
            # with the reason on record, and leaves the supervisor serving the others.
            self._end_unstarted(
                run_id,
                RunStatus.FAILED,
                FailureClass.INFRASTRUCTURE,
                f"the run could not be prepared: {error}",
            )
            return

        # The record is durable before anything runs: a crash right here leaves a claimed run
        # without a monitor, which is queued again, never a program nobody knows about.
        with self._uow() as uow:
            run = uow.runs.get(run_id)
            if not self._mine(run):
                log.warning("run %s: taken over while it was prepared; not started here", run_id)
                return
            run.code = prepared.code.model_dump(mode="json")
            run.code_sha = prepared.code.sha
            run.inputs = [item.model_dump(mode="json") for item in prepared.inputs]
            run.environment = prepared.environment.model_dump(mode="json")
            run.updated_at = utcnow()  # the monitor gets its full grace period to appear
            uow.commit()
        try:
            handle = launch.spawn_monitor(self._run_dir(run_id))
        except OSError as error:
            self._end_unstarted(
                run_id,
                RunStatus.FAILED,
                FailureClass.INFRASTRUCTURE,
                f"the monitor could not be started: {error}",
            )
            return
        self._monitors[run_id] = handle
        log.info("run %s: monitor started (pid %s)", run_id, handle.pid)

    def _end_unstarted(
        self, run_id: str, status: RunStatus, failure_class: FailureClass | None, reason: str
    ) -> None:
        """Close a run whose program never ran."""
        with self._uow() as uow:
            run = uow.runs.get(run_id)
            if not self._mine(run):
                return
            now = utcnow()
            run.status = status.value
            run.failure_class = failure_class.value if failure_class else None
            run.status_reason = clip(reason)
            run.finished_at = now
            run.updated_at = now
            run.version += 1
            log.info("run %s: %s without starting its program: %s", run.id, run.status, reason)
            uow.record(
                self._event(
                    run,
                    EventType.RUN_FINISHED,
                    self._finished_payload(run),
                    Severity.ERROR if status is RunStatus.FAILED else Severity.INFO,
                )
            )
            uow.commit()

    # ------------------------------------------------------------------ ingesting

    def _ingest(self, run_id: str) -> None:
        """Bring one active run up to date with what its monitor has written.

        Three steps: note how the database sees the run, read the files with no transaction
        open, then apply the reading in a second transaction, provided the run is still as
        the first one found it. Otherwise the reading is dropped and the next round starts
        from whatever is there by then, so nothing is ever applied twice.
        """
        run_dir = self._run_dir(run_id)
        with self._uow() as uow:
            run = uow.runs.get(run_id)
            if not self._mine(run):
                return
            status, offsets = run.status, dict(run.ingest or {})
            unchanged_for = (utcnow() - run.updated_at).total_seconds()
            reported_gone = run.status_reason == MONITOR_GONE
            record = CodeProvenance.model_validate(run.code)
            cancel_reason = run.cancel_reason if run.cancel_requested_at is not None else None

        if cancel_reason is not None:
            # The API writes this file itself; repeating it here covers a request that was
            # recorded but whose file could not be written.
            control.request_cancel(run_dir, reason=cancel_reason, actor=f"worker:{self.id}")
        reading = read_run_files(run_dir, offsets)
        verdict = self._verdict(run_id, run_dir, reading, unchanged_for, reported_gone)
        leftovers = None
        if verdict.ends:
            found, left_out = artifacts.collect(run_dir)
            leftovers = Leftovers(found, left_out, working_tree_changed(record))

        with self._uow() as uow:
            run = uow.runs.get(run_id)
            if not self._mine(run) or run.status != status or dict(run.ingest or {}) != offsets:
                return
            progressed = bool(reading.journal or reading.samples or reading.metrics)
            if reading.identity is not None and run.monitor_pid is None:
                run.monitor_pid = reading.identity["pid"]
                run.monitor_started_at = reading.identity["create_time"]
                progressed = True
            if run.status == RunStatus.STARTING.value and reading.started is not None:
                self._mark_started(uow, run, reading.started)
                progressed = True
            for entry in reading.journal:
                self._record_journal_entry(uow, run, entry)
            if reading.samples:
                run.resources = self._fold_samples(run.resources, reading.samples)
            if reading.metrics is not None:
                self._record_metrics(uow, run, reading.metrics)

            if verdict.kind == "finished":
                assert reading.outcome is not None and leftovers is not None
                self._finalize(uow, run, reading.outcome, leftovers)
            elif verdict.kind in ("failed", "lost"):
                assert leftovers is not None
                self._monitors.pop(run.id, None)
                failed = verdict.kind == "failed"
                self._close(
                    uow,
                    run,
                    RunStatus.FAILED if failed else RunStatus.LOST,
                    FailureClass.INFRASTRUCTURE if failed else FailureClass.UNKNOWN,
                    verdict.reason,
                    leftovers,
                )
            elif verdict.kind == "requeue":
                run.status = RunStatus.QUEUED.value
                run.worker_id = None
                run.version += 1
                log.warning("run %s: queued again, its worker stopped before starting it", run.id)
                uow.record(
                    self._event(
                        run, EventType.RUN_REQUEUED, {"reason": verdict.reason}, Severity.WARNING
                    )
                )
            elif verdict.kind == "monitor_lost":
                assert reading.started is not None
                run.status_reason = MONITOR_GONE
                log.warning("run %s: its monitor is gone while the program still runs", run.id)
                uow.record(
                    self._event(
                        run,
                        EventType.RUN_MONITOR_LOST,
                        {"pid": reading.started["pid"]},
                        Severity.WARNING,
                    )
                )

            if progressed or verdict.kind != "continue":
                run.ingest = reading.offsets
                run.heartbeat_at = utcnow()
                run.updated_at = run.heartbeat_at
                uow.commit()

    def _verdict(
        self,
        run_id: str,
        run_dir: Path,
        reading: Reading,
        unchanged_for: float,
        reported_gone: bool,
    ) -> Verdict:
        """Decide only what is certain about a run from what its files say."""
        if reading.outcome is not None:
            return Verdict("finished")
        if reading.monitor_alive:
            return Verdict("continue")
        if reading.identity is None:
            handle = self._monitors.get(run_id)
            if handle is None:
                # Claimed by a worker that died before any monitor ran: nothing was executed.
                if unchanged_for < STARTUP_GRACE_SECONDS:
                    return Verdict("continue")
                return Verdict("requeue", "its worker stopped before the program was started")
            if handle.poll() is None:
                return Verdict("continue")  # just started; it has not named itself yet
            said = last_line(run_dir / layout.MONITOR_LOG) or "it left no message"
            return Verdict(
                "failed", f"the monitor could not start (exit code {handle.returncode}): {said}"
            )
        if reading.program_alive:
            return Verdict("continue" if reported_gone else "monitor_lost")
        return Verdict(
            "lost", "the monitor process disappeared without recording how the program ended"
        )

    def _mark_started(self, uow: UnitOfWork, run: Run, started: dict[str, Any]) -> None:
        run.status = RunStatus.RUNNING.value
        run.pid = started["pid"]
        run.process_started_at = started["create_time"]
        run.started_at = parse_stamp(started["started_at"])
        if run.environment is not None and "executable" in started:
            # The file the program actually runs as, resolved after any build.
            run.environment = {**run.environment, "executable": started["executable"]}
        run.version += 1
        uow.record(
            self._event(
                run,
                EventType.RUN_STARTED,
                {
                    "pid": run.pid,
                    "argv": run.argv,
                    "code_sha": run.code_sha,
                    "started_at": started["started_at"],  # the ledger time is when it was read
                },
            )
        )
        log.info("run %s: program running (pid %s)", run.id, run.pid)

    def _record_metrics(self, uow: UnitOfWork, run: Run, report: dict[str, Any]) -> None:
        """Bring the series of the run to what the monitor's summary says."""
        now = utcnow()
        known = {series.name: series for series in uow.metric_series.list_for_run(run.id)}
        for summary in report["series"]:
            series = known.get(summary["name"])
            if series is None:
                series = uow.metric_series.add(
                    MetricSeries(
                        id=new_id("ser"),
                        project_id=run.project_id,
                        experiment_id=run.experiment_id,
                        run_id=run.id,
                        **summary,
                        updated_at=now,
                    )
                )
                continue
            for column, value in summary.items():
                setattr(series, column, value)
            series.updated_at = now
        run.metric_report = {key: value for key, value in report.items() if key != "series"}

    def _record_journal_entry(self, uow: UnitOfWork, run: Run, entry: dict[str, Any]) -> None:
        mapped = journal_event(entry)
        if mapped is None:
            return
        event_type, severity = mapped
        details = {key: value for key, value in entry.items() if key not in ("t", "type")}
        uow.record(self._event(run, event_type, {**details, "observed_at": entry["t"]}, severity))

    @staticmethod
    def _fold_samples(
        current: dict[str, Any] | None, samples: list[dict[str, Any]]
    ) -> dict[str, Any]:
        summary = ResourceSummary.model_validate(current or {})
        of_the_program = [sample["rss_bytes"] for sample in samples if sample["phase"] == "program"]
        return ResourceSummary(
            samples=summary.samples + len(of_the_program),
            max_rss_bytes=max([summary.max_rss_bytes, *of_the_program]),
            last=ResourceSample.model_validate(samples[-1]),
        ).model_dump(mode="json")

    def _close(
        self,
        uow: UnitOfWork,
        run: Run,
        status: RunStatus,
        failure_class: FailureClass,
        reason: str,
        leftovers: Leftovers,
    ) -> None:
        """End a run whose outcome was not recorded by a monitor."""
        run.status = status.value
        run.failure_class = failure_class.value
        run.status_reason = clip(reason)
        run.finished_at = utcnow()
        run.version += 1
        self._register_artifacts(uow, run, leftovers)
        log.info("run %s: %s (%s)", run.id, run.status, run.status_reason)
        uow.record(
            self._event(run, EventType.RUN_FINISHED, self._finished_payload(run), Severity.ERROR)
        )

    def _finalize(
        self, uow: UnitOfWork, run: Run, outcome: RunOutcome, leftovers: Leftovers
    ) -> None:
        status, failure_class, reason = classify(outcome)
        run.status = status.value
        run.failure_class = failure_class.value if failure_class else None
        run.status_reason = clip(reason)
        run.exit_code = outcome.exit_code
        run.exit_signal = outcome.signal
        run.wall_seconds = outcome.wall_seconds
        run.finished_at = parse_stamp(outcome.finished_at)
        run.outcome = outcome.model_dump(mode="json")
        run.version += 1
        if leftovers.source_changed is not None:
            run.code = {**(run.code or {}), "changed_during_run": leftovers.source_changed}
        if leftovers.source_changed:
            uow.record(
                self._event(
                    run,
                    EventType.RUN_SOURCE_CHANGED,
                    {
                        "detail": (
                            "HEAD or the uncommitted changes to tracked files are no longer "
                            "what the program started with"
                        )
                    },
                    Severity.WARNING,
                )
            )
        self._register_artifacts(uow, run, leftovers)
        severity = {
            RunStatus.SUCCEEDED: Severity.INFO,
            RunStatus.CANCELLED: Severity.WARNING,
        }.get(status, Severity.ERROR)
        payload = self._finished_payload(run)
        if leftovers.left_out:
            payload["results_not_listed"] = leftovers.left_out
        log.info(
            "run %s: %s after %.1f s%s",
            run.id,
            run.status,
            outcome.wall_seconds,
            f" ({run.status_reason})" if run.status_reason else "",
        )
        uow.record(self._event(run, EventType.RUN_FINISHED, payload, severity))

    def _finished_payload(self, run: Run) -> dict[str, Any]:
        return {
            "status": run.status,
            "failure_class": run.failure_class,
            "status_reason": run.status_reason,
            "exit_code": run.exit_code,
            "signal": run.exit_signal,
            "wall_seconds": run.wall_seconds,
            "program_seconds": (run.outcome or {}).get("program_seconds"),
            "finished_at": run.finished_at.strftime(TIMESTAMP_FORMAT) if run.finished_at else None,
            "code_sha": run.code_sha,
            "program_started": run.started_at is not None,
        }

    def _register_artifacts(self, uow: UnitOfWork, run: Run, leftovers: Leftovers) -> None:
        now = utcnow()
        for item in leftovers.found:
            uow.artifacts.add(
                Artifact(
                    id=new_id("art"),
                    project_id=run.project_id,
                    run_id=run.id,
                    kind=item.kind,
                    name=item.name,
                    media_type=item.media_type,
                    size_bytes=item.size_bytes,
                    sha256=item.sha256,
                    created_at=now,
                )
            )
