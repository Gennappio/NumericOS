"""The per-run monitor, with real processes."""

from __future__ import annotations

import hashlib
import json
import os
import signal
import subprocess
import sys
import time
from pathlib import Path

import psutil

from numericos.executor import control, layout
from tests.executor.helpers import (
    exit_of,
    journal,
    output,
    python,
    read_jsonl,
    run_monitor,
    start_monitor,
    wait_for,
    write_spec,
)

MB = 1024 * 1024
SLEEP_FOREVER = "import time; time.sleep(120)"


def gone(pid: int) -> bool:
    """The process no longer runs (a zombie counts as gone)."""
    try:
        return psutil.Process(pid).status() == psutil.STATUS_ZOMBIE
    except psutil.NoSuchProcess:
        return True


def test_output_is_recorded_line_by_line_with_stream_and_arrival_time(tmp_path: Path) -> None:
    write_spec(
        tmp_path,
        python(
            """
            import sys, time
            print("first")
            print("warning", file=sys.stderr)
            time.sleep(0.4)
            print("last")
            """
        ),
    )

    result = run_monitor(tmp_path)

    records = read_jsonl(tmp_path / layout.OUTPUT)
    assert output(tmp_path, "o") == ["first", "last"]
    assert output(tmp_path, "e") == ["warning"]
    arrival = {record["l"]: record["t"] for record in records}
    assert arrival["last"] - arrival["first"] >= 0.3  # arrival times, not one batch at the end
    assert result["exit_code"] == 0
    assert result["signal"] is None
    assert result["termination"] == {
        "reason": "exited",
        "detail": "",
        "sigterm_sent": False,
        "sigkill_sent": False,
    }
    assert result["output"] == {
        "stdout_lines": 2,
        "stderr_lines": 1,
        "build_lines": 0,
        "records": 0,
        "bytes": (tmp_path / layout.OUTPUT).stat().st_size,
        "truncated": False,
    }
    assert result["wall_seconds"] >= 0.4
    started = layout.read_json(tmp_path / layout.STARTED)
    assert started is not None
    assert started["pid"] > 0 and started["create_time"] > 0
    assert journal(tmp_path) == ["started", "finished"]


def test_a_failing_exit_code_and_a_fatal_signal_are_told_apart(tmp_path: Path) -> None:
    write_spec(tmp_path / "exit", python("import sys; print('no convergence'); sys.exit(3)"))
    write_spec(
        tmp_path / "crash",
        python("import os, signal; os.kill(os.getpid(), signal.SIGSEGV)"),
    )

    by_code = run_monitor(tmp_path / "exit")
    by_signal = run_monitor(tmp_path / "crash")

    assert (by_code["exit_code"], by_code["signal"]) == (3, None)
    assert (by_signal["exit_code"], by_signal["signal"]) == (None, "SIGSEGV")
    for result in (by_code, by_signal):
        assert result["termination"]["reason"] == "exited"  # nobody asked it to stop
        assert result["termination"]["sigterm_sent"] is False


def test_the_wall_clock_limit_stops_the_program(tmp_path: Path) -> None:
    write_spec(tmp_path, python(SLEEP_FOREVER), wall_seconds=0.6)
    began = time.monotonic()

    result = run_monitor(tmp_path)

    assert time.monotonic() - began < 10
    assert result["termination"]["reason"] == "limit_wall"
    assert result["termination"]["sigterm_sent"] is True
    assert result["termination"]["sigkill_sent"] is False
    assert result["signal"] == "SIGTERM"
    events = read_jsonl(tmp_path / layout.JOURNAL)
    limit = next(event for event in events if event["type"] == "limit_exceeded")
    assert (limit["limit"], limit["threshold"]) == ("wall_seconds", 0.6)
    assert limit["value"] > 0.6


def test_a_program_that_ignores_sigterm_is_killed_after_the_grace_period(tmp_path: Path) -> None:
    write_spec(
        tmp_path,
        python(
            """
            import signal, time
            signal.signal(signal.SIGTERM, signal.SIG_IGN)
            print("ignoring SIGTERM")
            time.sleep(120)
            """
        ),
        wall_seconds=0.5,
        grace_seconds=0.6,
    )

    result = run_monitor(tmp_path)

    assert result["termination"]["reason"] == "limit_wall"
    assert result["termination"]["sigkill_sent"] is True
    assert result["signal"] == "SIGKILL"
    assert [e["signal"] for e in read_jsonl(tmp_path / layout.JOURNAL) if "signal" in e] == [
        "SIGTERM",
        "SIGKILL",
    ]


def test_the_memory_limit_stops_the_program(tmp_path: Path) -> None:
    write_spec(
        tmp_path,
        python(
            """
            import time
            block = b"x" * (300 * 1024 * 1024)
            print("allocated", len(block))
            time.sleep(120)
            """
        ),
        max_rss_bytes=120 * MB,
    )

    result = run_monitor(tmp_path)

    assert result["termination"]["reason"] == "limit_rss"
    limit = next(e for e in read_jsonl(tmp_path / layout.JOURNAL) if e["type"] == "limit_exceeded")
    assert limit["limit"] == "max_rss"
    assert limit["value"] > limit["threshold"] == 120 * MB
    assert result["sampled"]["max_rss_bytes"] > 120 * MB


def test_a_cancel_request_stops_the_whole_process_tree(tmp_path: Path) -> None:
    write_spec(
        tmp_path,
        python(
            f"""
            import os, subprocess, sys, time
            child = subprocess.Popen([sys.executable, "-c", {SLEEP_FOREVER!r}])
            print("pids", os.getpid(), child.pid)
            time.sleep(120)
            """
        ),
    )
    monitor = start_monitor(tmp_path)
    line = wait_for(lambda: next(iter(output(tmp_path, "o")), None), what="the program's pids")
    parent, child = (int(pid) for pid in line.split()[1:])

    control.request_cancel(tmp_path, reason="requested by the user", actor="web:local")
    monitor.wait(timeout=15)

    result = exit_of(tmp_path)
    assert result["termination"]["reason"] == "cancelled"
    assert result["termination"]["detail"] == "requested by the user"
    assert result["signal"] == "SIGTERM"
    assert gone(parent)
    wait_for(lambda: gone(child), timeout=5, what="the child process to stop")


def test_processes_the_program_leaves_behind_are_stopped(tmp_path: Path) -> None:
    write_spec(
        tmp_path,
        python(
            f"""
            import subprocess, sys
            orphan = subprocess.Popen(
                [sys.executable, "-c", {SLEEP_FOREVER!r}],
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
            )
            print("left behind", orphan.pid)
            """
        ),
    )

    result = run_monitor(tmp_path)

    orphan = int(output(tmp_path, "o")[0].split()[-1])
    assert result["exit_code"] == 0
    assert result["termination"]["reason"] == "exited"
    assert "leftover_processes" in journal(tmp_path)
    wait_for(lambda: gone(orphan), timeout=5, what="the leftover process to stop")


def test_a_program_that_cannot_be_started_is_reported_not_guessed(tmp_path: Path) -> None:
    write_spec(tmp_path / "missing", ["no-such-solver-binary", "--dt", "0.01"])
    write_spec(tmp_path / "nowhere", python("print('x')"), cwd=str(tmp_path / "does-not-exist"))

    missing = run_monitor(tmp_path / "missing")
    nowhere = run_monitor(tmp_path / "nowhere")

    for result in (missing, nowhere):
        assert result["termination"]["reason"] == "launch_failed"
        assert (result["exit_code"], result["signal"]) == (None, None)
        assert (result["program_seconds"], result["rusage"]) == (None, None)  # nothing ran
    assert "no-such-solver-binary" in missing["termination"]["detail"]
    assert not (tmp_path / "missing" / layout.STARTED).exists()


def test_unusual_output_is_recorded_without_losing_what_follows(tmp_path: Path) -> None:
    write_spec(
        tmp_path,
        python(
            """
            import sys
            out = sys.stdout.buffer
            out.write(b"windows line\\r\\n")
            out.write(b"not utf-8: \\xff\\xfe\\n")
            out.write(b"x" * (1024 * 1024 + 500) + b"\\n")
            out.write(b"after the long line\\n")
            out.write(b"no newline at the end")
            """
        ),
    )

    result = run_monitor(tmp_path)

    records = [record for record in read_jsonl(tmp_path / layout.OUTPUT) if record["s"] == "o"]
    texts = [record["l"] for record in records]
    assert texts[0] == "windows line"
    assert texts[1] == "not utf-8: ��"
    assert len(texts[2]) == 1024 * 1024 and records[2]["x"] == 1  # cut, and flagged as cut
    assert texts[3:] == ["after the long line", "no newline at the end"]
    assert result["output"]["stdout_lines"] == 5


def test_output_beyond_the_cap_is_counted_but_not_stored(tmp_path: Path) -> None:
    write_spec(
        tmp_path,
        python("for i in range(500): print('line', i)"),
        max_output_bytes=2000,
    )

    result = run_monitor(tmp_path)

    assert (tmp_path / layout.OUTPUT).stat().st_size <= 2000
    assert result["output"]["truncated"] is True
    assert result["output"]["stdout_lines"] == 500  # every line was seen
    assert 0 < len(output(tmp_path)) < 500
    assert journal(tmp_path).count("output_truncated") == 1
    assert result["exit_code"] == 0


def test_build_commands_run_first_and_a_failed_build_prevents_the_run(tmp_path: Path) -> None:
    write_spec(
        tmp_path / "ok",
        python("print('running')"),
        build=[python("print('compiling')")],
    )
    write_spec(
        tmp_path / "broken",
        python("print('must not run')"),
        build=[python("import sys; print('error: syntax', file=sys.stderr); sys.exit(2)")],
    )

    built = run_monitor(tmp_path / "ok")
    failed = run_monitor(tmp_path / "broken")

    records = read_jsonl(tmp_path / "ok" / layout.OUTPUT)
    assert [(record["s"], record["l"]) for record in records] == [
        ("b", "compiling"),
        ("o", "running"),
    ]
    assert built["exit_code"] == 0
    assert failed["termination"]["reason"] == "build_failed"
    assert "ended with 2" in failed["termination"]["detail"]
    assert (failed["exit_code"], failed["signal"]) == (None, None)  # the program never ran
    assert (failed["program_seconds"], failed["rusage"]) == (None, None)
    assert output(tmp_path / "broken") == ["error: syntax"]
    assert not (tmp_path / "broken" / layout.STARTED).exists()


def test_a_stop_that_comes_after_the_program_ended_does_not_rewrite_how_it_ended(
    tmp_path: Path,
) -> None:
    # The program ends by itself, but a child keeps its output open: the monitor is still
    # collecting when the wall limit passes and when the cancellation arrives.
    write_spec(
        tmp_path,
        python(
            f"""
            import subprocess, sys
            subprocess.Popen([sys.executable, "-c", {SLEEP_FOREVER!r}])
            print("result ready", flush=True)
            """
        ),
        wall_seconds=0.8,
    )
    monitor = start_monitor(tmp_path)
    wait_for(lambda: output(tmp_path, "o") == ["result ready"], what="the program's result")
    control.request_cancel(tmp_path, reason="too late", actor="test")
    monitor.wait(timeout=15)

    result = exit_of(tmp_path)
    assert result["termination"]["reason"] == "exited"
    assert (result["exit_code"], result["signal"]) == (0, None)
    assert result["termination"]["sigterm_sent"] is False  # tidying up leftovers is not a stop
    assert "limit_exceeded" not in journal(tmp_path)
    assert "leftover_processes" in journal(tmp_path)


def test_a_cancellation_during_the_build_means_the_program_is_never_started(
    tmp_path: Path,
) -> None:
    write_spec(
        tmp_path,
        python("print('must not run')"),
        build=[python("import time; print('compiling', flush=True); time.sleep(60)")],
    )
    monitor = start_monitor(tmp_path)
    wait_for(lambda: output(tmp_path, "b") == ["compiling"], what="the build to start")

    control.request_cancel(tmp_path, reason="wrong flags", actor="test")
    monitor.wait(timeout=15)

    result = exit_of(tmp_path)
    assert result["termination"]["reason"] == "cancelled"
    assert result["termination"]["detail"] == "wrong flags"
    assert (result["exit_code"], result["signal"]) == (None, None)
    assert output(tmp_path, "o") == []
    assert not (tmp_path / layout.STARTED).exists()


def test_a_monitor_that_is_told_to_stop_takes_its_program_with_it(tmp_path: Path) -> None:
    write_spec(tmp_path, python("import os, time; print(os.getpid()); time.sleep(120)"))
    monitor = start_monitor(tmp_path)
    pid = int(wait_for(lambda: next(iter(output(tmp_path, "o")), None), what="the program"))

    monitor.send_signal(signal.SIGTERM)
    monitor.wait(timeout=15)

    result = exit_of(tmp_path)
    assert result["termination"]["reason"] == "monitor_terminated"
    assert "SIGTERM" in result["termination"]["detail"]
    assert gone(pid)


def test_a_run_outlives_the_process_that_started_its_monitor(tmp_path: Path) -> None:
    write_spec(tmp_path, python("import time; time.sleep(1.0); print('finished on my own')"))
    launcher = python(
        """
        import subprocess, sys
        subprocess.Popen(
            [sys.executable, "-m", "numericos.executor.monitor", sys.argv[1]],
            stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
            start_new_session=True,
        )
        """,
        str(tmp_path),
    )

    subprocess.run(launcher, check=True, timeout=10)  # the "worker" starts a monitor and dies
    assert not (tmp_path / layout.EXIT).exists()

    wait_for(lambda: (tmp_path / layout.EXIT).exists(), what="the run to finish by itself")
    assert exit_of(tmp_path)["exit_code"] == 0
    assert output(tmp_path, "o") == ["finished on my own"]


def test_resources_of_the_process_tree_are_sampled_while_it_runs(tmp_path: Path) -> None:
    write_spec(
        tmp_path,
        python(
            """
            import time
            data = [float(i) for i in range(200_000)]
            end = time.monotonic() + 1.2
            while time.monotonic() < end:
                sum(x * x for x in data)
            """
        ),
    )

    result = run_monitor(tmp_path)

    samples = read_jsonl(tmp_path / layout.RESOURCES)
    assert len(samples) >= 4
    assert result["sampled"]["samples"] == len(samples)
    assert {sample["phase"] for sample in samples} == {"program"}
    assert {sample["processes"] for sample in samples} == {1}
    # Every sample covers a real interval: the first comes one interval after the start, and
    # one busy thread never shows up as several cores.
    assert samples[0]["elapsed"] >= 0.15
    assert max(sample["cpu_percent"] for sample in samples) > 50
    assert max(sample["cpu_percent"] for sample in samples) < 150
    assert max(sample["rss_bytes"] for sample in samples) > 5 * MB
    assert result["sampled"]["max_rss_bytes"] == max(sample["rss_bytes"] for sample in samples)
    assert [sample["elapsed"] for sample in samples] == sorted(s["elapsed"] for s in samples)
    assert samples[-1]["cpu_seconds"] > 0.5
    assert result["rusage"]["cpu_user_seconds"] > 0.5  # exact totals from the operating system
    assert result["rusage"]["max_rss_bytes"] > 5 * MB
    assert 1.2 <= result["program_seconds"] <= result["wall_seconds"]
    if sys.platform == "darwin":
        assert samples[0]["io_read_bytes"] is None  # not offered by this platform: said, not faked
    started = layout.read_json(tmp_path / layout.STARTED)
    assert started is not None and started["pid"] != os.getpid()


def test_a_run_directory_has_one_monitor_and_a_second_one_starts_nothing(tmp_path: Path) -> None:
    write_spec(
        tmp_path,
        python("import os, time; print('pid', os.getpid(), flush=True); time.sleep(120)"),
    )
    first = start_monitor(tmp_path)
    wait_for(lambda: output(tmp_path, "o"), what="the program to start")
    named = (tmp_path / layout.MONITOR).read_text()

    second = start_monitor(tmp_path)
    _out, said = second.communicate(timeout=15)
    still_named = (tmp_path / layout.MONITOR).read_text()
    control.request_cancel(tmp_path, reason="end of the test", actor="test")
    first.wait(timeout=15)

    assert second.returncode == 3
    assert "already has a monitor" in said.decode()
    assert still_named == named
    assert len(output(tmp_path, "o")) == 1  # the program was started once
    assert exit_of(tmp_path)["termination"]["reason"] == "cancelled"
    assert sorted(path.name for path in tmp_path.glob(".monitor*")) == []  # no draft left


def test_the_program_file_is_identified_when_the_program_starts(tmp_path: Path) -> None:
    script = "#!/bin/sh\necho from-the-built-program\n"
    build = python(
        "import os, sys; open('solver', 'w').write(sys.argv[1]); os.chmod('solver', 0o755)",
        script,
    )
    write_spec(tmp_path, ["./solver"], build=[build])

    result = run_monitor(tmp_path)

    started = json.loads((tmp_path / layout.STARTED).read_text())
    assert result["exit_code"] == 0
    assert output(tmp_path, "o") == ["from-the-built-program"]
    assert started["executable"]["path"] == str((tmp_path / "solver").resolve())
    assert started["executable"]["sha256"] == hashlib.sha256(script.encode()).hexdigest()
    stamp = (tmp_path / layout.LAUNCH).stat().st_mtime_ns
    assert (tmp_path / "solver").stat().st_mtime_ns <= stamp  # built before the launch


def test_the_program_is_timed_and_measured_apart_from_its_build(tmp_path: Path) -> None:
    burn = """
        import time
        end = time.monotonic() + 0.8
        while time.monotonic() < end:
            sum(range(2000))
        """
    write_spec(tmp_path, python("import time; time.sleep(0.4)"), build=[python(burn)])

    result = run_monitor(tmp_path)

    built = next(e for e in read_jsonl(tmp_path / layout.JOURNAL) if e["type"] == "build_finished")
    samples = read_jsonl(tmp_path / layout.RESOURCES)
    in_build = [sample for sample in samples if sample["phase"] == "build"]
    in_program = [sample for sample in samples if sample["phase"] == "program"]
    assert built["seconds"] >= 0.8 and built["cpu_seconds"] >= 0.5
    assert 0.4 <= result["program_seconds"] < 0.8  # the sleep, not the build before it
    assert result["wall_seconds"] >= 1.2  # both
    total_cpu = result["rusage"]["cpu_user_seconds"] + result["rusage"]["cpu_system_seconds"]
    assert total_cpu < 0.3  # the program slept: the CPU of the build is not counted as its own
    assert in_build and in_program
    assert max(sample["cpu_percent"] for sample in in_build) > 50
    assert max(sample["cpu_percent"] for sample in in_program) < 50
    assert in_program[0]["cpu_seconds"] < in_build[-1]["cpu_seconds"]  # counted per phase
    assert result["sampled"]["samples"] == len(in_program)


def test_the_time_of_the_program_ends_when_it_exits_not_when_the_monitor_has_tidied_up(
    tmp_path: Path,
) -> None:
    write_spec(
        tmp_path,
        python(
            f"""
            import subprocess, sys, time
            subprocess.Popen([sys.executable, "-c", {SLEEP_FOREVER!r}])  # keeps the output open
            time.sleep(0.3)
            """
        ),
    )

    result = run_monitor(tmp_path)

    assert result["exit_code"] == 0
    assert 0.3 <= result["program_seconds"] < 1.5
    assert result["wall_seconds"] >= 2.0  # waiting for the output and stopping what was left


def test_a_run_shorter_than_the_sampling_interval_has_exact_totals_but_no_samples(
    tmp_path: Path,
) -> None:
    write_spec(tmp_path, python("print('quick')"), resource_interval_seconds=5.0)

    result = run_monitor(tmp_path)

    assert read_jsonl(tmp_path / layout.RESOURCES) == []
    assert result["sampled"] == {"samples": 0, "max_rss_bytes": 0}
    assert result["rusage"]["max_rss_bytes"] > 1 * MB
    assert 0 < result["program_seconds"] < 5.0
