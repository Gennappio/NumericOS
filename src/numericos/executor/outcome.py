"""From what a monitor recorded to the status of a run and the class of its failure."""

from __future__ import annotations

from numericos.core.enums import FailureClass, RunStatus
from numericos.core.execution import RunOutcome

#: Signals a program raises through its own fault.
FAULT_SIGNALS = frozenset({"SIGSEGV", "SIGBUS", "SIGFPE", "SIGILL", "SIGABRT", "SIGSYS", "SIGTRAP"})

Classification = tuple[RunStatus, FailureClass | None, str | None]


def classify(outcome: RunOutcome) -> Classification:
    """Status, failure class and a one-line reason.

    ``succeeded`` only says that the program ended by itself with exit code 0. Whether its
    result is scientifically valid is decided elsewhere, by validators.
    """
    reason, detail = outcome.termination.reason, outcome.termination.detail
    if reason in ("cancelled", "monitor_terminated"):
        return RunStatus.CANCELLED, None, detail
    if reason == "limit_wall":
        return RunStatus.TIMED_OUT, FailureClass.RESOURCE_LIMIT, detail
    if reason == "limit_rss":
        return RunStatus.FAILED, FailureClass.RESOURCE_LIMIT, detail
    if reason == "guardrail":
        return RunStatus.FAILED, FailureClass.NUMERICAL_INSTABILITY, detail
    if reason in ("build_failed", "launch_failed"):
        return RunStatus.FAILED, FailureClass.CODE_ERROR, detail
    if reason == "monitor_error":
        return RunStatus.FAILED, FailureClass.INFRASTRUCTURE, "the monitor of the run failed"
    if outcome.signal is not None:
        if outcome.signal in FAULT_SIGNALS:
            return (
                RunStatus.FAILED,
                FailureClass.CODE_ERROR,
                f"the program was terminated by {outcome.signal}",
            )
        return (
            RunStatus.FAILED,
            FailureClass.UNKNOWN,
            f"the program was stopped by {outcome.signal}, sent from outside NumericOS",
        )
    if outcome.exit_code == 0:
        return RunStatus.SUCCEEDED, None, None
    return (
        RunStatus.FAILED,
        FailureClass.CODE_ERROR,
        f"the program exited with code {outcome.exit_code}",
    )
