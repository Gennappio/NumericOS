"""Per-run monitor.

One monitor process per run. It starts the program in its own process group, records its output
line by line with arrival times, samples the resources of its process tree, enforces the limits
of the run, obeys a cancellation request, and finally writes how the program ended. Everything
goes to files in the run directory. The monitor needs no database and no supervisor: a run stays
observed and bounded even when the worker that started it is gone.

Usage: ``python -m numericos.executor.monitor RUN_DIR``
"""

from __future__ import annotations

import contextlib
import json
import os
import resource
import selectors
import signal
import subprocess
import sys
import time
import traceback
from dataclasses import dataclass
from pathlib import Path
from typing import Any, BinaryIO

import psutil

from numericos.executor import layout
from numericos.executor.collector import PARSED, RECORD, LineObserver, MetricCollector
from numericos.executor.spec import RunSpec
from numericos.provenance.executable import resolve_executable

MAX_LINE_BYTES = 1024 * 1024
#: After the program exits, how long to keep reading output still held open by descendants.
DRAIN_SECONDS = 2.0
TICK_SECONDS = 0.1
STREAMS = {"o": "stdout", "e": "stderr", "b": "build"}
#: ``ru_maxrss`` is in bytes on macOS and in kibibytes on Linux.
MAXRSS_UNIT = 1 if sys.platform == "darwin" else 1024


def utc_stamp(epoch: float | None = None) -> str:
    moment = time.gmtime(time.time() if epoch is None else epoch)
    fraction = int(((time.time() if epoch is None else epoch) % 1) * 1_000_000)
    return time.strftime("%Y-%m-%dT%H:%M:%S", moment) + f".{fraction:06d}Z"


def group_alive(pgid: int) -> bool:
    try:
        os.killpg(pgid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return True


@dataclass
class Ended:
    """How one command ended, with what the operating system measured for it."""

    returncode: int | None = None
    launch_error: str | None = None
    #: From just before the command was started until its exit was noticed.
    seconds: float | None = None
    cpu_user_seconds: float | None = None
    cpu_system_seconds: float | None = None
    max_rss_bytes: int | None = None

    @property
    def ok(self) -> bool:
        return self.launch_error is None and self.returncode == 0


class Child:
    """A started command. It is reaped with ``wait4``, which reports the resources that this
    command and the descendants it waited for have used: exact totals for the program alone,
    apart from the build commands that ran before it."""

    def __init__(self, process: subprocess.Popen[bytes]) -> None:
        self._process = process
        self.pid = process.pid
        self.returncode: int | None = None
        self.usage: resource.struct_rusage | None = None

    def poll(self) -> int | None:
        if self.returncode is None:
            pid, status, usage = os.wait4(self.pid, os.WNOHANG)
            if pid == self.pid:
                self.returncode = os.waitstatus_to_exitcode(status)
                self.usage = usage
                self._process.returncode = self.returncode  # the Popen object must not wait again
        return self.returncode


class AlreadyMonitoredError(Exception):
    """The run directory already has a monitor: this one must not start anything."""


class Monitor:
    def __init__(self, run_dir: Path, observer: LineObserver | None = None) -> None:
        self.dir = run_dir
        self.spec = RunSpec.model_validate_json((run_dir / layout.SPEC).read_bytes())
        self._claim()
        self._output = self._append(layout.OUTPUT)
        self._resources = self._append(layout.RESOURCES)
        self._journal = self._append(layout.JOURNAL)
        #: Learns the metrics of the run from its output lines, and may ask for a stop.
        self.observer = observer or MetricCollector(run_dir, self.spec, self._note)
        self._began = time.monotonic()
        self._stop: tuple[str, str] | None = None
        self._sigterm_at: float | None = None
        self._sigkill_at: float | None = None
        #: Stop signals that actually reached the run, as opposed to being attempted.
        self._delivered: set[str] = set()
        self._received_signal: int | None = None
        self._wakeup: int | None = None
        self._output_bytes = 0
        self._output_truncated = False
        self._lines = dict.fromkeys(STREAMS, 0)
        self._records = 0
        # Sampling state of the command in progress; the totals describe the program only.
        self._cpu_seen: dict[int, float] = {}
        self._cpu_seconds = 0.0
        self._last_sample = self._began
        self._samples = 0
        self._max_rss = 0

    def _claim(self) -> None:
        """Name this process as the one monitor of the run, or refuse to go on.

        A run directory is executed at most once. The name is given by creating
        ``monitor.json`` exclusively: of two monitors started for the same run by mistake,
        exactly one gets it, and the other leaves without having started anything.
        """
        identity = {
            "pid": os.getpid(),
            "create_time": psutil.Process().create_time(),
            "started_at": utc_stamp(),
        }
        draft = self.dir / f".{layout.MONITOR}.{os.getpid()}"
        draft.write_text(json.dumps(identity, sort_keys=True))
        try:
            os.link(draft, self.dir / layout.MONITOR)  # fails if the name is taken
        except FileExistsError:
            raise AlreadyMonitoredError(
                f"{self.dir} already has a monitor ({layout.MONITOR} exists)"
            ) from None
        finally:
            draft.unlink()

    def _append(self, name: str) -> BinaryIO:
        return (self.dir / name).open("ab", buffering=0)

    # ------------------------------------------------------------------ records

    def _write(self, handle: BinaryIO, record: dict[str, Any]) -> None:
        handle.write(json.dumps(record, separators=(",", ":")).encode() + b"\n")

    def _note(self, kind: str, **fields: Any) -> None:
        self._write(self._journal, {"t": utc_stamp(), "type": kind, **fields})

    def _line(self, stream: str, raw: bytes, *, cut: bool = False) -> None:
        arrived = time.time()
        text = raw.rstrip(b"\r").decode("utf-8", errors="replace")
        self._lines[stream] += 1
        became = self.observer.observe(STREAMS[stream], text, arrived)
        if became == RECORD:
            self._records += 1  # kept as a sample or an event, not as a line of output
            return
        if self._output_truncated:
            return
        record: dict[str, Any] = {"t": round(arrived, 6), "s": stream, "l": text}
        if became == PARSED:
            record["m"] = 1
        if cut:
            record["x"] = 1
        encoded = json.dumps(record, separators=(",", ":"), ensure_ascii=False).encode() + b"\n"
        if self._output_bytes + len(encoded) > self.spec.max_output_bytes:
            self._output_truncated = True
            self._note("output_truncated", limit_bytes=self.spec.max_output_bytes)
            return
        self._output_bytes += len(encoded)
        self._output.write(encoded)

    # ------------------------------------------------------------------ stopping

    def _request_stop(self, reason: str, detail: str) -> None:
        if self._stop is None:
            self._stop = (reason, detail)
            self._note("stop_requested", reason=reason, detail=detail)

    def _on_signal(self, signum: int, _frame: object) -> None:
        self._received_signal = signum

    def _drive_stop(self, pgid: int) -> None:
        """SIGTERM the whole process group once, SIGKILL it after the grace period."""
        now = time.monotonic()
        if self._sigterm_at is None:
            self._sigterm_at = now
            if self._signal_group(pgid, signal.SIGTERM):
                self._delivered.add("SIGTERM")
        elif self._sigkill_at is None and now - self._sigterm_at >= self.spec.grace_seconds:
            self._sigkill_at = now
            if self._signal_group(pgid, signal.SIGKILL):
                self._delivered.add("SIGKILL")

    def _signal_group(self, pgid: int, signum: signal.Signals) -> bool:
        """Signal the group. False when nothing was left to receive the signal."""
        try:
            os.killpg(pgid, signum)
        except ProcessLookupError:
            return False
        self._note("signal_sent", signal=signum.name)
        return True

    # ------------------------------------------------------------------ observation

    def _sample(self, root: psutil.Process, phase: str) -> None:
        """One sample of the process tree. CPU use is what the tree consumed since the previous
        sample (or since the command started), so every sample covers a real interval."""
        now = time.monotonic()
        interval = now - self._last_sample
        try:
            processes = [root, *root.children(recursive=True)]
        except psutil.Error:
            return  # the command ended between the liveness check and the sample
        rss = threads = alive = 0
        cpu_delta = 0.0
        read_bytes: int | None = None
        write_bytes: int | None = None
        seen: dict[int, float] = {}
        for process in processes:
            try:
                with process.oneshot():
                    times = process.cpu_times()
                    rss += process.memory_info().rss
                    threads += process.num_threads()
                    if hasattr(process, "io_counters"):
                        counters = process.io_counters()
                        read_bytes = (read_bytes or 0) + counters.read_bytes
                        write_bytes = (write_bytes or 0) + counters.write_bytes
            except psutil.Error:
                continue
            alive += 1
            used = times.user + times.system
            seen[process.pid] = used
            # A process seen for the first time started within this interval: all the CPU
            # time it has used so far was used in it.
            cpu_delta += max(0.0, used - self._cpu_seen.get(process.pid, 0.0))
        if alive == 0:
            return
        self._last_sample = now
        self._cpu_seen = seen
        self._cpu_seconds += cpu_delta
        if phase == "program":
            self._samples += 1
            self._max_rss = max(self._max_rss, rss)
        self._write(
            self._resources,
            {
                "t": round(time.time(), 3),
                "elapsed": round(now - self._began, 3),
                "phase": phase,
                "cpu_percent": round(100 * cpu_delta / interval, 1) if interval > 0 else 0.0,
                "cpu_seconds": round(self._cpu_seconds, 3),
                "rss_bytes": rss,
                "processes": alive,
                "threads": threads,
                "io_read_bytes": read_bytes,
                "io_write_bytes": write_bytes,
            },
        )
        limit = self.spec.max_rss_bytes
        if limit is not None and rss > limit:
            self._note("limit_exceeded", limit="max_rss", value=rss, threshold=limit)
            self._request_stop("limit_rss", f"resident memory {rss} bytes exceeded {limit} bytes")

    def _check(self) -> None:
        """Everything that can require stopping the program, checked once per tick."""
        elapsed = time.monotonic() - self._began
        if elapsed > self.spec.wall_seconds:
            if self._stop is None:
                self._note(
                    "limit_exceeded",
                    limit="wall_seconds",
                    value=round(elapsed, 3),
                    threshold=self.spec.wall_seconds,
                )
            self._request_stop(
                "limit_wall", f"wall-clock limit of {self.spec.wall_seconds} s exceeded"
            )
        if self._received_signal is not None:
            name = signal.Signals(self._received_signal).name
            self._request_stop("monitor_terminated", f"the monitor received {name}")
        cancel = layout.read_json(self.dir / layout.CANCEL)
        if cancel is not None:
            self._request_stop("cancelled", str(cancel.get("reason", "cancellation requested")))
        observed = self.observer.stop_request()
        if observed is not None:
            self._request_stop(*observed)

    # ------------------------------------------------------------------ execution

    def _execute(self, argv: list[str], *, stream_out: str, stream_err: str, main: bool) -> Ended:
        phase = "program" if main else "build"
        if main:
            # After the build, so that a compiled program is identified by the binary that
            # runs. The stamp marks the moment: files modified from here on are the program's.
            executable = resolve_executable(argv[0], self.spec.env, Path(self.spec.cwd))
            (self.dir / layout.LAUNCH).touch()
        began = time.monotonic()
        try:
            process = subprocess.Popen(
                argv,
                cwd=self.spec.cwd,
                env=self.spec.env,
                stdin=subprocess.DEVNULL,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                start_new_session=True,  # its own process group: signals reach the whole tree
                bufsize=0,
            )
        except OSError as error:
            return Ended(launch_error=f"{argv[0]!r} could not be started: {error.strerror}")
        assert process.stdout is not None and process.stderr is not None
        child = Child(process)
        pgid = process.pid
        try:
            root: psutil.Process | None = psutil.Process(process.pid)
            created = root.create_time() if root else None
        except psutil.Error:
            root, created = None, None
        if main:
            layout.write_json_atomic(
                self.dir / layout.STARTED,
                {
                    "pid": process.pid,
                    "pgid": pgid,
                    "create_time": created,
                    "started_at": utc_stamp(),
                    "monitor_pid": os.getpid(),
                    "executable": executable.model_dump(mode="json"),
                },
            )
            self._note("started", pid=process.pid)

        selector = selectors.DefaultSelector()
        selector.register(process.stdout, selectors.EVENT_READ, stream_out)
        selector.register(process.stderr, selectors.EVENT_READ, stream_err)
        assert self._wakeup is not None, "run() installs the wake-up pipe before anything starts"
        selector.register(self._wakeup, selectors.EVENT_READ, None)
        pending = {stream_out: b"", stream_err: b""}
        skipping = {stream_out: False, stream_err: False}
        open_streams = 2
        exited_at: float | None = None
        self._cpu_seen = {}
        self._cpu_seconds = 0.0
        self._last_sample = began
        next_sample = began + self.spec.resource_interval_seconds

        while True:
            timeout = max(0.0, min(next_sample - time.monotonic(), TICK_SECONDS))
            for key, _events in selector.select(timeout):
                if key.data is None:
                    with contextlib.suppress(BlockingIOError):
                        os.read(key.fd, 4096)  # a signal arrived: look at everything now
                    continue
                stream = key.data
                chunk = os.read(key.fd, 65536)
                if not chunk:
                    selector.unregister(key.fileobj)
                    open_streams -= 1
                    if pending[stream] and not skipping[stream]:
                        self._line(stream, pending[stream])
                    pending[stream] = b""
                    continue
                self._consume(stream, chunk, pending, skipping)

            if exited_at is None and child.poll() is not None:
                exited_at = time.monotonic()
            if exited_at is None:
                if root is not None and time.monotonic() >= next_sample:
                    next_sample = time.monotonic() + self.spec.resource_interval_seconds
                    self._sample(root, phase)
                # A limit or a request can only stop a program that is still running. One
                # that arrives after the program ended by itself changes nothing about how
                # it ended.
                self._check()
                if self._stop is not None:
                    self._drive_stop(pgid)
            elif open_streams == 0 or time.monotonic() - exited_at > DRAIN_SECONDS:
                break
            self.observer.tick()
        selector.close()
        process.stdout.close()
        process.stderr.close()
        self._reap_group(pgid)
        usage = child.usage
        assert usage is not None and exited_at is not None
        return Ended(
            returncode=child.returncode,
            seconds=round(exited_at - began, 6),
            cpu_user_seconds=round(usage.ru_utime, 6),
            cpu_system_seconds=round(usage.ru_stime, 6),
            max_rss_bytes=usage.ru_maxrss * MAXRSS_UNIT,
        )

    def _consume(
        self, stream: str, chunk: bytes, pending: dict[str, bytes], skipping: dict[str, bool]
    ) -> None:
        """Split a chunk into lines; a line longer than the limit is recorded once, cut."""
        data = pending[stream] + chunk
        *lines, rest = data.split(b"\n")
        for line in lines:
            if skipping[stream]:
                skipping[stream] = False  # the end of an over-long line
            elif len(line) > MAX_LINE_BYTES:
                self._line(stream, line[:MAX_LINE_BYTES], cut=True)
            else:
                self._line(stream, line)
        if skipping[stream]:
            rest = b""
        elif len(rest) > MAX_LINE_BYTES:
            self._line(stream, rest[:MAX_LINE_BYTES], cut=True)
            skipping[stream] = True
            rest = b""
        pending[stream] = rest

    def _reap_group(self, pgid: int) -> None:
        """No process of the run may outlive it: stop whatever is left in its group."""
        if not group_alive(pgid):
            return
        self._note("leftover_processes")
        self._signal_group(pgid, signal.SIGTERM)
        deadline = time.monotonic() + self.spec.grace_seconds
        while group_alive(pgid) and time.monotonic() < deadline:
            time.sleep(0.05)
        if group_alive(pgid):
            self._signal_group(pgid, signal.SIGKILL)

    # ------------------------------------------------------------------ lifecycle

    def _listen_for_signals(self) -> None:
        """Requests to stop the monitor are noted and obeyed in the loop. The end of a child
        wakes the loop at once, so that the time a command took is measured to the moment it
        ended and not to the next tick."""
        for signum in (signal.SIGTERM, signal.SIGINT, signal.SIGHUP):
            signal.signal(signum, self._on_signal)
        self._wakeup, write_end = os.pipe()
        os.set_blocking(self._wakeup, False)
        os.set_blocking(write_end, False)
        signal.set_wakeup_fd(write_end, warn_on_full_buffer=False)
        signal.signal(signal.SIGCHLD, lambda _signum, _frame: None)

    def run(self) -> None:
        self._listen_for_signals()
        reason, detail = "exited", ""
        program = Ended()  # how the program itself ended; stays empty if it never ran
        attempted = False
        try:
            build_failure = self._build()
            if build_failure is not None:
                reason, detail = "build_failed", build_failure
            elif self._stop is None:
                attempted = True
                program = self._execute(self.spec.argv, stream_out="o", stream_err="e", main=True)
                if program.launch_error:
                    reason, detail = "launch_failed", program.launch_error
            # A stop is the reason only if it had an effect: a signal reached the run, or the
            # program was not started because of it.
            if self._stop is not None and (self._delivered or not attempted):
                reason, detail = self._stop
        except Exception:
            # The boundary of the run: whatever goes wrong here must still be recorded.
            reason, detail = "monitor_error", traceback.format_exc(limit=5)
            traceback.print_exc()
        self._finish(program, reason, detail)

    def _build(self) -> str | None:
        """Run the build commands in order; return what went wrong with the first that failed.

        Nothing further is started once a stop has been requested.
        """
        for index, command in enumerate(self.spec.build):
            if self._stop is not None:
                return None
            self._note("build_started", index=index, argv=command)
            built = self._execute(command, stream_out="b", stream_err="b", main=False)
            self._note(
                "build_finished",
                index=index,
                returncode=built.returncode,
                seconds=built.seconds,
                cpu_seconds=(
                    None
                    if built.cpu_user_seconds is None or built.cpu_system_seconds is None
                    else round(built.cpu_user_seconds + built.cpu_system_seconds, 6)
                ),
            )
            if not built.ok:
                return built.launch_error or (
                    f"build command {index} ({command[0]}) ended with {built.returncode}"
                )
        return None

    def _finish(self, program: Ended, reason: str, detail: str) -> None:
        code = program.returncode
        measured = program.cpu_user_seconds is not None
        cpu = (
            program.cpu_user_seconds + program.cpu_system_seconds
            if program.cpu_user_seconds is not None and program.cpu_system_seconds is not None
            else None
        )
        self.observer.measured(
            {
                "wall_time": program.seconds,
                "cpu_time": round(cpu, 6) if cpu is not None else None,
                "max_rss": program.max_rss_bytes,
            },
            time.time(),
        )
        document = {
            "exit_code": code if code is not None and code >= 0 else None,
            "signal": signal.Signals(-code).name if code is not None and code < 0 else None,
            "finished_at": utc_stamp(),
            "wall_seconds": round(time.monotonic() - self._began, 3),
            "program_seconds": program.seconds,
            "termination": {
                "reason": reason,
                "detail": detail,
                "sigterm_sent": "SIGTERM" in self._delivered,
                "sigkill_sent": "SIGKILL" in self._delivered,
            },
            "rusage": (
                {
                    "cpu_user_seconds": program.cpu_user_seconds,
                    "cpu_system_seconds": program.cpu_system_seconds,
                    "max_rss_bytes": program.max_rss_bytes,
                }
                if measured
                else None
            ),
            "sampled": {
                "samples": self._samples,
                "max_rss_bytes": self._max_rss,
            },
            "output": {
                "stdout_lines": self._lines["o"],
                "stderr_lines": self._lines["e"],
                "build_lines": self._lines["b"],
                "records": self._records,
                "bytes": self._output_bytes,
                "truncated": self._output_truncated,
            },
            "observed": self.observer.close(),
        }
        self._note("finished", reason=reason)
        for handle in (self._output, self._resources, self._journal):
            os.fsync(handle.fileno())
            handle.close()
        layout.write_json_atomic(self.dir / layout.EXIT, document)


def main(arguments: list[str] | None = None) -> int:
    arguments = sys.argv[1:] if arguments is None else arguments
    if len(arguments) != 1:
        print("usage: python -m numericos.executor.monitor RUN_DIR", file=sys.stderr)
        return 2
    try:
        monitor = Monitor(Path(arguments[0]))
    except AlreadyMonitoredError as error:
        print(f"refusing to start: {error}", file=sys.stderr)
        return 3
    monitor.run()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
