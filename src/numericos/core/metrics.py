"""Scientific metrics of a run.

Three shapes: the **record** a program emits (``numericos.metric.v1``, one JSON object per
line), the **sample** that is stored and returned, and the **summary** of a series. JSON has no
NaN and no infinity, so NumericOS never writes them as numbers: a non-finite value is a sample
whose ``value`` is null and whose ``non_finite`` says which kind it is.
"""

from __future__ import annotations

import math
import re
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from numericos.core.experiment import METRIC_NAME

METRIC_SCHEMA = "numericos.metric.v1"
EVENT_SCHEMA = "numericos.event.v1"

NonFinite = Literal["nan", "inf", "-inf"]
MetricSource = Literal["instrumentation", "parser", "supervisor"]

_NON_FINITE_WORDS: dict[str, NonFinite] = {
    "nan": "nan",
    "+nan": "nan",
    "-nan": "nan",
    "inf": "inf",
    "+inf": "inf",
    "-inf": "-inf",
    "infinity": "inf",
    "+infinity": "inf",
    "-infinity": "-inf",
}
_NAME = re.compile(METRIC_NAME)
#: A Fortran real with a D exponent (1.5D-03), as legacy solvers print it.
_FORTRAN_REAL = re.compile(r"^[+-]?(\d+\.?\d*|\.\d+)[dD][+-]?\d+$")
_RECORD_FIELDS = frozenset(
    {"schema", "name", "value", "step", "time", "unit", "timestamp_utc", "run_id"}
)
_EVENT_FIELDS = frozenset({"schema", "name", "message", "severity", "step", "run_id"})


class RecordError(ValueError):
    """A line that claims to be a NumericOS record but is not a valid one."""


def split_value(value: float) -> tuple[float | None, NonFinite | None]:
    """A finite value, or which kind of non-finite value it is."""
    if math.isnan(value):
        return None, "nan"
    if math.isinf(value):
        return None, "inf" if value > 0 else "-inf"
    return value, None


def number_from_text(text: str) -> tuple[float | None, NonFinite | None]:
    """A number as programs print it: decimal, exponent with E or Fortran D, nan, inf.

    Raises ``ValueError`` when the text is not a number at all.
    """
    cleaned = text.strip()
    word = _NON_FINITE_WORDS.get(cleaned.lower())
    if word is not None:
        return None, word
    if _FORTRAN_REAL.match(cleaned):
        cleaned = cleaned.replace("d", "e").replace("D", "e")
    return split_value(float(cleaned))


class MetricRecord(BaseModel):
    """One ``numericos.metric.v1`` record, validated."""

    name: str
    value: float | None
    non_finite: NonFinite | None
    step: int | None
    time: float | None
    unit: str | None
    timestamp_utc: str | None
    run_id: str | None


class ProgramEvent(BaseModel):
    """One ``numericos.event.v1`` record: something the program wants on the run's timeline."""

    name: str
    message: str
    severity: Literal["info", "warning", "error"]
    step: int | None


def _integer(document: dict[str, Any], field: str) -> int | None:
    value = document.get(field)
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise RecordError(f"'{field}' must be a non-negative integer")
    return value


def _text(document: dict[str, Any], field: str, limit: int) -> str | None:
    value = document.get(field)
    if value is None:
        return None
    if not isinstance(value, str) or len(value) > limit:
        raise RecordError(f"'{field}' must be text of at most {limit} characters")
    return value


def _name(document: dict[str, Any]) -> str:
    name = document.get("name")
    if not isinstance(name, str) or not _NAME.match(name):
        raise RecordError("'name' must start with a letter and use only letters, digits, _ . -")
    return name


def _value(raw: Any) -> tuple[float | None, NonFinite | None]:
    """The value of a record: a JSON number, or a word for a non-finite value."""
    wrong = RecordError('\'value\' must be a number or one of "nan", "inf", "-inf"')
    if isinstance(raw, bool) or raw is None:
        raise wrong
    if isinstance(raw, str):
        word = _NON_FINITE_WORDS.get(raw.strip().lower())
        if word is None:
            raise wrong
        return None, word
    if not isinstance(raw, int | float):
        raise wrong
    try:
        return split_value(float(raw))
    except OverflowError:
        raise RecordError("'value' is too large for a floating-point number") from None


def parse_metric_record(document: dict[str, Any]) -> MetricRecord:
    """Validate a decoded metric record. Every rejection says what is wrong with it.

    The decoder may already have turned the non-standard literals ``NaN`` and ``Infinity``
    into floats; they are accepted on the way in and stored as typed non-finite values.
    """
    unknown = sorted(set(document) - _RECORD_FIELDS)
    if unknown:
        raise RecordError(f"unknown field {unknown[0]!r}")
    value, non_finite = _value(document.get("value"))
    time = document.get("time")
    if time is not None and (
        isinstance(time, bool) or not isinstance(time, int | float) or not math.isfinite(time)
    ):
        raise RecordError("'time' must be a finite number")
    return MetricRecord(
        name=_name(document),
        value=value,
        non_finite=non_finite,
        step=_integer(document, "step"),
        time=float(time) if time is not None else None,
        unit=_text(document, "unit", 60),
        timestamp_utc=_text(document, "timestamp_utc", 40),
        run_id=_text(document, "run_id", 64),
    )


def parse_program_event(document: dict[str, Any]) -> ProgramEvent:
    unknown = sorted(set(document) - _EVENT_FIELDS)
    if unknown:
        raise RecordError(f"unknown field {unknown[0]!r}")
    severity = document.get("severity", "info")
    if severity not in ("info", "warning", "error"):
        raise RecordError("'severity' must be info, warning or error")
    return ProgramEvent(
        name=_name(document),
        message=_text(document, "message", 500) or "",
        severity=severity,
        step=_integer(document, "step"),
    )


class MetricSample(BaseModel):
    """One stored sample of a metric."""

    t: float = Field(description="Epoch seconds when the monitor received the sample.")
    value: float | None = Field(description="Null when the value is not finite.")
    non_finite: NonFinite | None = Field(
        default=None, description="Which non-finite value it was, when 'value' is null."
    )
    step: int | None = Field(default=None, description="The program's step or iteration.")
    time: float | None = Field(
        default=None, description="The program's own time coordinate, e.g. simulated time."
    )
    source_timestamp: str | None = Field(
        default=None, description="The time the program itself attached to the sample, as sent."
    )


class SeriesSummary(BaseModel):
    """What is known about one metric of a run without reading its samples."""

    model_config = ConfigDict(from_attributes=True)

    name: str
    unit: str = Field(description="As declared in the contract; as sent, if it is not declared.")
    source: MetricSource = Field(
        description=(
            "instrumentation: records emitted by the program; parser: extracted from its "
            "output; supervisor: measured from outside."
        )
    )
    declared: bool = Field(description="Whether the experiment's contract declares the metric.")
    samples: int
    non_finite: int = Field(description="How many samples were NaN or infinite.")
    stored: int = Field(description="Samples kept in the series file; fewer if it was cut.")
    first_value: float | None = None
    first_step: int | None = None
    last_value: float | None = None
    last_non_finite: NonFinite | None = None
    last_step: int | None = None
    last_time: float | None = None
    last_at: float | None = Field(default=None, description="Arrival time of the last sample.")
    min_value: float | None = Field(default=None, description="Over the finite samples.")
    max_value: float | None = None


class MetricPage(BaseModel):
    """Samples of one metric after a cursor. ``complete``: the run ended and nothing follows."""

    samples: list[MetricSample]
    next_cursor: int = Field(description="Pass as 'after' to continue. It is a byte offset.")
    has_more: bool
    complete: bool


class MetricBucket(BaseModel):
    """A stretch of consecutive samples of one metric, reduced to what a chart needs."""

    samples: int
    non_finite: int
    first_step: int | None
    last_step: int | None
    first_time: float | None
    last_time: float | None
    first_t: float
    last_t: float
    first_value: float | None
    last_value: float | None
    min_value: float | None = Field(description="Over the finite samples of the stretch.")
    max_value: float | None


class MetricOverview(BaseModel):
    """A whole series in a bounded number of buckets, however many samples it has."""

    name: str
    samples: int = Field(description="Stored samples the buckets were built from.")
    buckets: list[MetricBucket]
    next_cursor: int = Field(
        description="Where the overview ends: read newer samples from here with 'after'."
    )
    complete: bool


CoverageStatus = Literal["observed", "partial", "waiting", "missing", "not_configured"]


class CoverageLevel(BaseModel):
    """How far one level of observation reaches for a run."""

    level: Literal["L0", "L1", "L2", "L3"]
    title: str
    status: CoverageStatus = Field(
        description=(
            "observed: everything the contract asks for at this level has data; partial: some "
            "of it; waiting: none yet, the run is still going; missing: none, and the run has "
            "ended; not_configured: the contract asks for nothing at this level."
        )
    )
    detail: str


class MetricCoverage(BaseModel):
    """Whether a metric the contract declares was actually measured."""

    name: str
    unit: str
    source: MetricSource
    status: Literal["observed", "waiting", "missing"]
    samples: int
    non_finite: int


class Coverage(BaseModel):
    """What of a run is observed and what is not. Nothing here says a result is valid."""

    levels: list[CoverageLevel]
    metrics: list[MetricCoverage]
    undeclared: list[str] = Field(
        description="Metrics the program emitted that the contract does not declare."
    )


class Diagnostic(BaseModel):
    """Something about the program's records or the parsers that needs a person's attention."""

    kind: str
    message: str = Field(description="What happened and what was done about it.")
    count: int
    examples: list[str]


#: What each kind of diagnostic means, in one sentence, for every surface that shows it.
DIAGNOSTIC_MESSAGES = {
    "malformed_record": (
        "Lines that look like NumericOS records but are not valid. They were left in the "
        "output and no sample was recorded."
    ),
    "unsupported_schema": (
        "Records of a schema this version does not know. They were left in the output."
    ),
    "undeclared_metric": (
        "Metrics the program emitted that the contract does not declare. They were kept and "
        "are marked as not declared."
    ),
    "undeclared_dropped": "Undeclared metrics beyond the number that is kept. They were ignored.",
    "unit_mismatch": (
        "Records whose unit differs from the contract's. The values were kept as sent: "
        "nothing was converted."
    ),
    "source_mismatch": (
        "Records for metrics the contract assigns to a parser or to the supervisor. They "
        "were ignored."
    ),
    "run_id_mismatch": "Records that carry the ID of another run. They were kept.",
    "name_collision": (
        "Metric names that differ from another one only by case. They were ignored."
    ),
    "unparsable_value": (
        "Text captured by a parser that is not a number. No sample was recorded for it."
    ),
}


class RunMetrics(BaseModel):
    series: list[SeriesSummary]
    coverage: Coverage
    records: int = Field(description="Metric records the program emitted.")
    parsed_lines: int = Field(description="Output lines from which a parser extracted values.")
    program_events: int
    truncated: bool = Field(description="Samples beyond the storage limit were not kept.")
    diagnostics: list[Diagnostic]
