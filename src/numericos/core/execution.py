"""How a run went: the shapes a monitor writes and the API returns."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field


class Termination(BaseModel):
    reason: Literal[
        "exited",
        "cancelled",
        "limit_wall",
        "limit_rss",
        "guardrail",
        "build_failed",
        "launch_failed",
        "monitor_terminated",
        "monitor_error",
    ] = Field(
        description="'exited': the program ended by itself; otherwise who stopped it and why."
    )
    detail: str
    sigterm_sent: bool
    sigkill_sent: bool


class ProcessUsage(BaseModel):
    """What the operating system measured for the program and the descendants it waited for,
    exact at exit. The build commands are not included."""

    cpu_user_seconds: float
    cpu_system_seconds: float
    max_rss_bytes: int = Field(
        description="Largest resident set of a single process of the program's tree."
    )


class SampledUsage(BaseModel):
    """What the periodic samples saw while the program ran. A peak between two samples is
    missed; a run shorter than the sampling interval has no sample at all."""

    samples: int
    max_rss_bytes: int = Field(description="Largest sum over the process tree in one sample.")


class OutputSummary(BaseModel):
    stdout_lines: int
    stderr_lines: int
    build_lines: int
    bytes: int
    truncated: bool = Field(description="Output beyond the run's limit was seen but not stored.")


class RunOutcome(BaseModel):
    """How the program ended, as recorded by its monitor (``exit.json``)."""

    exit_code: int | None = Field(description="Of the program; null if it never ran.")
    signal: str | None = Field(description="The signal that ended the program, if one did.")
    finished_at: str
    wall_seconds: float = Field(
        description="From the start of the monitor to its end: build commands and program."
    )
    program_seconds: float | None = Field(
        description=(
            "Wall time of the program alone, from just before it was started until its exit "
            "was noticed. Null if it never ran."
        )
    )
    termination: Termination
    rusage: ProcessUsage | None = Field(description="Null if the program never ran.")
    sampled: SampledUsage
    output: OutputSummary
    observed: dict[str, Any] = Field(default_factory=dict)


class ResourceSample(BaseModel):
    """One sample of the program's process tree."""

    t: float = Field(description="Epoch seconds when the sample was taken.")
    elapsed: float = Field(description="Seconds since the monitor started.")
    phase: Literal["build", "program"] = Field(
        description="Whether a build command or the program was running."
    )
    cpu_percent: float = Field(
        description=(
            "CPU the process tree used since the previous sample (the first: since the "
            "command started), as a percentage of one core."
        )
    )
    cpu_seconds: float = Field(description="CPU seconds seen so far in this phase.")
    rss_bytes: int
    processes: int
    threads: int
    io_read_bytes: int | None = Field(description="Null where the platform does not report it.")
    io_write_bytes: int | None


class ResourceSummary(BaseModel):
    """The resource samples recorded so far, in short."""

    samples: int = Field(default=0, description="Samples taken while the program ran.")
    max_rss_bytes: int = Field(
        default=0, description="Largest sum over the process tree in one of those samples."
    )
    last: ResourceSample | None = Field(
        default=None, description="The latest sample, of the build or of the program."
    )


class LogLine(BaseModel):
    t: float = Field(description="Epoch seconds when the monitor received the line.")
    stream: Literal["stdout", "stderr", "build"]
    text: str
    metric: bool = Field(default=False, description="The line was consumed as a metric record.")
    cut: bool = Field(default=False, description="The line was longer than the limit and cut.")
