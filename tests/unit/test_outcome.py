"""From what a monitor recorded to a run status and a failure class."""

from __future__ import annotations

import pytest

from numericos.core.enums import FailureClass, RunStatus
from numericos.core.execution import RunOutcome
from numericos.executor.outcome import classify


def outcome(reason: str, *, exit_code: int | None = None, signal: str | None = None) -> RunOutcome:
    return RunOutcome.model_validate(
        {
            "exit_code": exit_code,
            "signal": signal,
            "finished_at": "2026-10-12T10:00:00.000000Z",
            "wall_seconds": 1.5,
            "program_seconds": 1.4,
            "termination": {
                "reason": reason,
                "detail": f"detail of {reason}",
                "sigterm_sent": False,
                "sigkill_sent": False,
            },
            "rusage": {"cpu_user_seconds": 0.1, "cpu_system_seconds": 0.0, "max_rss_bytes": 1},
            "sampled": {"samples": 1, "max_rss_bytes": 1},
            "output": {
                "stdout_lines": 0,
                "stderr_lines": 0,
                "build_lines": 0,
                "bytes": 0,
                "truncated": False,
            },
        }
    )


@pytest.mark.parametrize(
    ("recorded", "status", "failure_class"),
    [
        (outcome("exited", exit_code=0), RunStatus.SUCCEEDED, None),
        (outcome("exited", exit_code=2), RunStatus.FAILED, FailureClass.CODE_ERROR),
        (outcome("exited", signal="SIGSEGV"), RunStatus.FAILED, FailureClass.CODE_ERROR),
        (outcome("exited", signal="SIGFPE"), RunStatus.FAILED, FailureClass.CODE_ERROR),
        # Killed from outside, e.g. by the system's out-of-memory killer: the cause is not known.
        (outcome("exited", signal="SIGKILL"), RunStatus.FAILED, FailureClass.UNKNOWN),
        (outcome("cancelled", signal="SIGTERM"), RunStatus.CANCELLED, None),
        (outcome("monitor_terminated", signal="SIGTERM"), RunStatus.CANCELLED, None),
        (outcome("limit_wall", signal="SIGTERM"), RunStatus.TIMED_OUT, FailureClass.RESOURCE_LIMIT),
        (outcome("limit_rss", signal="SIGKILL"), RunStatus.FAILED, FailureClass.RESOURCE_LIMIT),
        (
            outcome("guardrail", signal="SIGTERM"),
            RunStatus.FAILED,
            FailureClass.NUMERICAL_INSTABILITY,
        ),
        (outcome("build_failed", exit_code=2), RunStatus.FAILED, FailureClass.CODE_ERROR),
        (outcome("launch_failed"), RunStatus.FAILED, FailureClass.CODE_ERROR),
        (outcome("monitor_error"), RunStatus.FAILED, FailureClass.INFRASTRUCTURE),
    ],
)
def test_classification(
    recorded: RunOutcome, status: RunStatus, failure_class: FailureClass | None
) -> None:
    assert classify(recorded)[:2] == (status, failure_class)


def test_who_stopped_the_program_decides_not_the_exit_code_it_then_returned() -> None:
    # A program that catches SIGTERM and exits 0 after its time ran out did not succeed.
    status, failure_class, reason = classify(outcome("limit_wall", exit_code=0))

    assert (status, failure_class) == (RunStatus.TIMED_OUT, FailureClass.RESOURCE_LIMIT)
    assert reason == "detail of limit_wall"


def test_a_normal_end_needs_no_reason_and_a_failure_names_its_exit_code() -> None:
    assert classify(outcome("exited", exit_code=0))[2] is None
    assert classify(outcome("exited", exit_code=7))[2] == "the program exited with code 7"
    assert "SIGSEGV" in str(classify(outcome("exited", signal="SIGSEGV"))[2])
