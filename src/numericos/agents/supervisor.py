"""Turns of the coding agent under the supervisor.

The worker that serves runs also serves turns, with the same rules: a turn is claimed in the
database, its agent process is started detached with its output going to a file, the file is
read between transactions, and every write is fenced so that two workers, or a worker and the
API, never apply the same reading twice. A supervisor that stops leaves the agent running; the
next one continues from the files.

An agent process is not a monitor: nothing writes how it ended but itself (the ``result``
record). A process that is gone without a result left an interrupted turn, and says so.
"""

from __future__ import annotations

import contextlib
import logging
import os
import signal
import subprocess
import time
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal, TypeGuard

import psutil

from numericos.agents import claude_code, layout
from numericos.agents.records import choice_for, finished_payload
from numericos.config import Settings
from numericos.core.agents import ActivityItem, TurnResult
from numericos.core.enums import EventType, MessageStatus, PermissionMode, Severity
from numericos.core.ids import new_id
from numericos.events.ledger import EventContext, build_event
from numericos.executor.layout import read_json, write_json_atomic
from numericos.executor.liveness import process_alive, worker_alive
from numericos.observability import files
from numericos.persistence.engine import TIMESTAMP_FORMAT, utcnow
from numericos.persistence.models import AgentMessage, Event
from numericos.persistence.unit_of_work import UnitOfWork

ACTIVE = (MessageStatus.QUEUED.value, MessageStatus.RUNNING.value)
#: A claimed turn whose process never appeared is given this long before it is queued again.
STARTUP_GRACE_SECONDS = 10.0
#: After SIGTERM, how long the agent gets to leave before SIGKILL.
STOP_GRACE_SECONDS = 5.0
REASON_MAX = 300
ENDED_WITHOUT_ANSWER = "the agent process ended without a final answer"

log = logging.getLogger("numericos.agents")


def clip(reason: str) -> str:
    line = " ".join(reason.split())
    return line if len(line) <= REASON_MAX else line[: REASON_MAX - 1] + "…"


def last_line(path: Path) -> str:
    try:
        lines = path.read_text(errors="replace").splitlines()
    except FileNotFoundError:
        return ""
    return next((line.strip() for line in reversed(lines) if line.strip()), "")


@dataclass(frozen=True)
class TurnReading:
    """What the files of a turn say at one moment, beyond what the database already holds."""

    identity: dict[str, Any] | None
    alive: bool
    records: list[dict[str, Any]]
    cursor: int


def read_turn_files(turn_dir: Path, offsets: dict[str, Any]) -> TurnReading:
    """Liveness first, then the stream: a process that ends between the two has written its
    result, and must not be taken for one that vanished."""
    identity = read_json(turn_dir / layout.PROCESS)
    alive = identity is not None and process_alive(identity["pid"], identity["create_time"])
    records, cursor = files.read_to_end(turn_dir / layout.STREAM, int(offsets.get("stream", 0)))
    return TurnReading(identity=identity, alive=alive, records=records, cursor=cursor)


@dataclass(frozen=True)
class Verdict:
    kind: Literal["continue", "finished", "ended", "requeue"]
    reason: str = ""


@dataclass(frozen=True)
class Launch:
    """Everything a turn needs to start, read in one transaction."""

    message_id: str
    project_id: str
    session_id: str
    native_session_id: str
    cwd: str
    mode: PermissionMode
    model: str | None
    effort: str | None
    system: str
    prompt: str
    resume: bool
    cancelled: bool


class TurnSupervisor:
    def __init__(
        self,
        *,
        worker_id: str,
        uow: Callable[[], UnitOfWork],
        settings: Settings,
        max_parallel: int,
        stale_after: float,
    ) -> None:
        self.worker_id = worker_id
        self._uow = uow
        self.settings = settings
        self.max_parallel = max_parallel
        self.stale_after = stale_after
        self._processes: dict[str, subprocess.Popen[bytes]] = {}

    def _turn_dir(self, message_id: str) -> Path:
        return layout.turn_dir(self.settings.data_dir, message_id)

    def _mine(self, message: AgentMessage | None) -> TypeGuard[AgentMessage]:
        return (
            message is not None and message.status in ACTIVE and message.worker_id == self.worker_id
        )

    def _event(
        self,
        message: AgentMessage,
        event_type: EventType,
        payload: dict[str, Any],
        severity: Severity = Severity.INFO,
    ) -> Event:
        context = EventContext(
            actor=f"worker:{self.worker_id}",
            correlation_id=message.correlation_id or new_id("cor"),
            producer="worker",
        )
        return build_event(
            event_type=event_type,
            project_id=message.project_id,
            subject_id=message.id,
            payload=payload,
            context=context,
            severity=severity,
        )

    # ------------------------------------------------------------------ one round

    def tick(self) -> None:
        self._adopt_orphans()
        for message_id in self._owned():
            self._ingest(message_id)
        capacity = self.max_parallel - len(self._owned())
        for _ in range(max(0, capacity)):
            claimed = self._claim_next()
            if claimed is None:
                break
            self._launch(claimed)

    def pending(self) -> int:
        with self._uow() as uow:
            return len(uow.messages.with_status(ACTIVE))

    def _owned(self) -> list[str]:
        with self._uow() as uow:
            return [
                message.id
                for message in uow.messages.with_status(ACTIVE)
                if message.worker_id == self.worker_id
            ]

    def _adopt_orphans(self) -> None:
        """Take over claimed turns whose worker stopped or went silent."""
        with self._uow() as uow:
            now = utcnow()
            adopted = False
            for message in uow.messages.with_status(ACTIVE):
                if message.worker_id is None or message.worker_id == self.worker_id:
                    continue
                owner = uow.workers.get(message.worker_id)
                if worker_alive(owner, now, self.stale_after):
                    continue
                uow.record(
                    self._event(
                        message,
                        EventType.AGENT_TURN_ADOPTED,
                        {"previous_worker_id": message.worker_id, "worker_id": self.worker_id},
                    )
                )
                log.warning("turn %s: taken over from worker %s", message.id, message.worker_id)
                message.worker_id = self.worker_id
                adopted = True
            if adopted:
                uow.commit()

    # ------------------------------------------------------------------ starting

    def _claim_next(self) -> str | None:
        """The oldest queued turn of a session that is not already being answered."""
        with self._uow() as uow:
            active = uow.messages.with_status(ACTIVE)
            busy = {message.session_id for message in active if message.worker_id is not None}
            for message in active:
                if message.worker_id is not None or message.session_id in busy:
                    continue
                message.worker_id = self.worker_id
                message.version += 1
                message.updated_at = utcnow()
                uow.commit()
                return message.id
        return None

    def _launch(self, message_id: str) -> None:
        with self._uow() as uow:
            message = uow.messages.get(message_id)
            if not self._mine(message) or message.status != MessageStatus.QUEUED.value:
                return
            session = uow.agent_sessions.get(message.session_id)
            assert session is not None
            prompt = (
                uow.messages.get(message.prompt_message_id)
                if message.prompt_message_id is not None
                else None
            )
            # The provider knows the session only once a turn reached it: the first turn
            # creates it, the next ones resume it.
            earlier = [
                item
                for item in uow.messages.list_for_session(session.id)
                if item.id != message.id and item.model is not None
            ]
            mode = PermissionMode(session.permission_mode)
            policy = uow.agent_policies.get(message.project_id)
            model, effort = choice_for(session, policy.tasks if policy is not None else None)
            launch = Launch(
                message_id=message.id,
                project_id=message.project_id,
                session_id=session.id,
                native_session_id=session.native_session_id,
                cwd=session.cwd,
                mode=mode,
                model=model,
                effort=effort,
                system=session.system_prompt,
                prompt=(
                    f"{(prompt.markdown if prompt else '').rstrip()}\n\n"
                    f"{claude_code.mode_note(mode)}\n"
                ),
                resume=bool(earlier),
                cancelled=message.cancel_requested_at is not None,
            )

        if launch.cancelled:
            self._end_unstarted(message_id, MessageStatus.CANCELLED, "cancelled before it started")
            return
        if not Path(launch.cwd).is_dir():
            self._end_unstarted(
                message_id,
                MessageStatus.FAILED,
                f"the project directory {launch.cwd} does not exist",
            )
            return
        try:
            handle = self._spawn(launch)
        except OSError as error:
            self._end_unstarted(
                message_id, MessageStatus.FAILED, f"the agent could not be started: {error}"
            )
            return

        with self._uow() as uow:
            message = uow.messages.get(message_id)
            if not self._mine(message):
                # Taken over while it was started: nobody would read this process.
                log.warning("turn %s: taken over while starting; stopping the process", message_id)
                self._kill(handle.pid)
                return
            self._mark_started(uow, message, handle.pid, launch)
            uow.commit()
        self._processes[message_id] = handle
        log.info("turn %s: agent started (pid %s)", message_id, handle.pid)

    def _spawn(self, launch: Launch) -> subprocess.Popen[bytes]:
        turn_dir = self._turn_dir(launch.message_id)
        turn_dir.mkdir(parents=True, exist_ok=True)
        (turn_dir / layout.PROMPT).write_text(launch.prompt)
        argv = claude_code.command(
            self.settings.claude_command,
            session_id=launch.native_session_id,
            resume=launch.resume,
            mode=launch.mode,
            system=launch.system,
            max_budget_usd=self.settings.agent_max_budget_usd,
            model=launch.model,
            effort=launch.effort,
        )
        write_json_atomic(
            turn_dir / layout.SPEC,
            {
                "argv": argv,
                "cwd": launch.cwd,
                "resume": launch.resume,
                "mode": launch.mode.value,
                "model": launch.model,
                "effort": launch.effort,
            },
        )
        env = claude_code.environment(
            {
                "NUMERICOS_PROJECT_ID": launch.project_id,
                "NUMERICOS_AGENT_SESSION_ID": launch.session_id,
                "NUMERICOS_MESSAGE_ID": launch.message_id,
                "NUMERICOS_API_URL": self.settings.api_url,
            }
        )
        with (
            (turn_dir / layout.PROMPT).open("rb") as stdin,
            (turn_dir / layout.STREAM).open("ab") as stdout,
            (turn_dir / layout.STDERR).open("ab") as stderr,
        ):
            handle = subprocess.Popen(
                argv,
                stdin=stdin,
                stdout=stdout,
                stderr=stderr,
                cwd=launch.cwd,
                env=env,
                start_new_session=True,
            )
        try:
            create_time = psutil.Process(handle.pid).create_time()
        except psutil.Error:
            create_time = time.time()  # it ended at once; the reading will say so
        write_json_atomic(
            turn_dir / layout.PROCESS,
            {
                "pid": handle.pid,
                "pgid": handle.pid,
                "create_time": create_time,
                "started_at": utcnow().strftime(TIMESTAMP_FORMAT),
            },
        )
        return handle

    def _mark_started(
        self, uow: UnitOfWork, message: AgentMessage, pid: int, launch: Launch | None
    ) -> None:
        identity = read_json(self._turn_dir(message.id) / layout.PROCESS) or {}
        now = utcnow()
        message.status = MessageStatus.RUNNING.value
        message.pid = pid
        message.process_started_at = identity.get("create_time")
        message.started_at = now
        message.heartbeat_at = now
        message.updated_at = now
        message.version += 1
        payload: dict[str, Any] = {"pid": pid, "session_id": message.session_id}
        if launch is not None:
            message.model_requested = launch.model
            message.effort = launch.effort
            payload.update(
                {
                    "resume": launch.resume,
                    "permission_mode": launch.mode.value,
                    "model": launch.model,
                    "effort": launch.effort,
                }
            )
        uow.record(self._event(message, EventType.AGENT_TURN_STARTED, payload))

    def _end_unstarted(self, message_id: str, status: MessageStatus, reason: str) -> None:
        with self._uow() as uow:
            message = uow.messages.get(message_id)
            if not self._mine(message):
                return
            now = utcnow()
            message.status = status.value
            message.status_reason = clip(reason)
            message.finished_at = now
            message.updated_at = now
            message.version += 1
            log.info("turn %s: %s without starting the agent: %s", message.id, status.value, reason)
            uow.record(
                self._event(
                    message,
                    EventType.AGENT_TURN_FINISHED,
                    finished_payload(message),
                    Severity.ERROR if status is MessageStatus.FAILED else Severity.WARNING,
                )
            )
            uow.commit()

    # ------------------------------------------------------------------ following

    def _ingest(self, message_id: str) -> None:
        """Bring one turn up to date with what its process wrote, in a fenced transaction."""
        turn_dir = self._turn_dir(message_id)
        with self._uow() as uow:
            message = uow.messages.get(message_id)
            if not self._mine(message):
                return
            status, offsets = message.status, dict(message.ingest or {})
            unchanged_for = (utcnow() - message.updated_at).total_seconds()
            cancel_reason = (
                message.cancel_reason if message.cancel_requested_at is not None else None
            )
            session = uow.agent_sessions.get(message.session_id)
            assert session is not None
            cwd = Path(session.cwd)

        reading = read_turn_files(turn_dir, offsets)
        signalled = dict(offsets)
        if cancel_reason is not None and reading.alive and reading.identity is not None:
            self._stop(reading.identity, signalled)
        verdict = self._verdict(message_id, reading, unchanged_for)
        handle = self._processes.get(message_id)
        exit_code = handle.poll() if handle is not None else None

        with self._uow() as uow:
            message = uow.messages.get(message_id)
            if (
                not self._mine(message)
                or message.status != status
                or dict(message.ingest or {}) != offsets
            ):
                return
            progressed = bool(reading.records) or signalled != offsets
            if message.status == MessageStatus.QUEUED.value and reading.identity is not None:
                # Started by a worker that stopped before recording it.
                self._mark_started(uow, message, reading.identity["pid"], None)
                progressed = True
            progress = self._fold(message, reading.records, cwd)

            if verdict.kind == "finished":
                assert progress.result is not None
                self._processes.pop(message_id, None)
                self._finalize(uow, message, progress.result, exit_code)
            elif verdict.kind == "ended":
                self._processes.pop(message_id, None)
                self._close(uow, message, cancel_reason, verdict.reason, exit_code)
            elif verdict.kind == "requeue":
                message.status = MessageStatus.QUEUED.value
                message.worker_id = None
                message.version += 1
                log.warning(
                    "turn %s: queued again, its worker stopped before starting it", message.id
                )
                uow.record(
                    self._event(
                        message,
                        EventType.AGENT_TURN_REQUEUED,
                        {"reason": verdict.reason},
                        Severity.WARNING,
                    )
                )

            if progressed or verdict.kind != "continue":
                message.ingest = {**signalled, "stream": reading.cursor}
                message.heartbeat_at = utcnow()
                message.updated_at = message.heartbeat_at
                uow.commit()

    def _verdict(self, message_id: str, reading: TurnReading, unchanged_for: float) -> Verdict:
        if any(record.get("type") == "result" for record in reading.records):
            return Verdict("finished")
        if reading.alive:
            return Verdict("continue")
        if reading.identity is None:
            handle = self._processes.get(message_id)
            if handle is not None and handle.poll() is None:
                return Verdict("continue")  # just started; its identity is being written
            if unchanged_for < STARTUP_GRACE_SECONDS:
                return Verdict("continue")
            return Verdict("requeue", "its worker stopped before the agent was started")
        said = last_line(self._turn_dir(message_id) / layout.STDERR)
        return Verdict("ended", f"{ENDED_WITHOUT_ANSWER}: {said or 'it left no message'}")

    def _fold(
        self, message: AgentMessage, records: list[dict[str, Any]], cwd: Path
    ) -> claude_code.Progress:
        progress = claude_code.Progress(
            model=message.model,
            activity=[ActivityItem.model_validate(item) for item in message.activity or []],
            dropped=message.activity_dropped or 0,
            files_read=list(message.files_read or []),
            files_written=list(message.files_written or []),
        )
        if not records:
            return progress
        now = time.time()
        for record in records:
            progress.fold(record, cwd, now)
        message.model = progress.model
        message.activity = [item.model_dump(mode="json") for item in progress.activity]
        message.activity_dropped = progress.dropped
        message.files_read = progress.files_read
        message.files_written = progress.files_written
        if progress.plan_usage is not None:
            message.plan_usage = progress.plan_usage.model_dump(mode="json")
        return progress

    def _finalize(
        self,
        uow: UnitOfWork,
        message: AgentMessage,
        result: TurnResult,
        exit_code: int | None,
    ) -> None:
        now = utcnow()
        failed = result.is_error
        message.status = (MessageStatus.FAILED if failed else MessageStatus.FINAL).value
        message.status_reason = clip(f"{result.subtype}: {result.text}") if failed else None
        message.markdown = result.text
        message.structured_output = result.structured_output
        message.cost_usd = result.cost_usd
        message.usage = result.usage.model_dump(mode="json") if result.usage else None
        message.num_turns = result.num_turns
        message.permission_denials = [
            denial.model_dump(mode="json") for denial in result.permission_denials
        ]
        message.exit_code = exit_code
        message.finished_at = now
        message.version += 1
        payload = {**finished_payload(message), "subtype": result.subtype}
        if result.duration_ms is not None:
            payload["duration_ms"] = result.duration_ms
        log.info(
            "turn %s: %s (%s, %s USD)", message.id, message.status, result.subtype, result.cost_usd
        )
        uow.record(
            self._event(
                message,
                EventType.AGENT_TURN_FINISHED,
                payload,
                Severity.ERROR if failed else Severity.INFO,
            )
        )

    def _close(
        self,
        uow: UnitOfWork,
        message: AgentMessage,
        cancel_reason: str | None,
        reason: str,
        exit_code: int | None,
    ) -> None:
        """End a turn whose process is gone without a result."""
        cancelled = cancel_reason is not None
        message.status = (MessageStatus.CANCELLED if cancelled else MessageStatus.INTERRUPTED).value
        message.status_reason = clip(reason if cancel_reason is None else cancel_reason)
        message.exit_code = exit_code
        message.finished_at = utcnow()
        message.version += 1
        log.info("turn %s: %s (%s)", message.id, message.status, message.status_reason)
        uow.record(
            self._event(
                message,
                EventType.AGENT_TURN_FINISHED,
                finished_payload(message),
                Severity.WARNING if cancelled else Severity.ERROR,
            )
        )

    # ------------------------------------------------------------------ stopping

    def _stop(self, identity: dict[str, Any], state: dict[str, Any]) -> None:
        """SIGTERM the agent's process group once; SIGKILL it when it outstays the grace."""
        signalled_at = state.get("signalled_at")
        now = time.time()
        if signalled_at is None:
            self._signal(identity["pgid"], signal.SIGTERM)
            state["signalled_at"] = now
        elif now - float(signalled_at) > STOP_GRACE_SECONDS and not state.get("killed"):
            self._signal(identity["pgid"], signal.SIGKILL)
            state["killed"] = True

    @staticmethod
    def _signal(pgid: int, signum: signal.Signals) -> None:
        with contextlib.suppress(ProcessLookupError, PermissionError):
            os.killpg(pgid, signum)

    def _kill(self, pid: int) -> None:
        self._signal(pid, signal.SIGKILL)
