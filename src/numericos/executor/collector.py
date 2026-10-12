"""What a monitor learns from the lines a program prints.

Two ways a number becomes a sample of a metric. The program emits a record
(``numericos.metric.v1``, level L2), or a parser of the experiment's contract extracts it from
an output line (level L1). Samples go to one file per metric. Non-finite values and violated
guardrails are noted the moment they are seen, and can require the program to be stopped: that
decision is taken here, in the monitor's process, so it holds even without a supervisor.

Nothing here judges whether a result is valid. A guardrail is an explicit bound of the contract.
"""

from __future__ import annotations

import json
import re
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, BinaryIO

from numericos.core.experiment import GuardrailRule, MetricSpec
from numericos.core.metrics import (
    EVENT_SCHEMA,
    METRIC_SCHEMA,
    MetricRecord,
    NonFinite,
    RecordError,
    number_from_text,
    parse_metric_record,
    parse_program_event,
)
from numericos.executor import layout
from numericos.executor.spec import RunSpec

#: What became of an output line.
PLAIN = "plain"  # an ordinary line of output
PARSED = "parsed"  # an output line from which a parser extracted values
RECORD = "record"  # a record: kept as a sample or an event, not as a line of output

#: A program can emit metrics the contract does not declare; they are kept, up to this many.
MAX_UNDECLARED = 50
#: Events a program puts on the run's timeline; more than this are counted, not kept.
MAX_PROGRAM_EVENTS = 200
MAX_EXAMPLES = 3
SUMMARY_SECONDS = 1.0

Note = Callable[..., None]


class LineObserver:
    """Sees every output line of a run. This one learns nothing from them."""

    def observe(self, stream: str, text: str, arrived: float) -> str:
        return PLAIN

    def tick(self) -> None:
        """Called regularly while the program runs."""

    def measured(self, values: dict[str, float | None], arrived: float) -> None:
        """Called once when the program has ended, with what the monitor measured of it."""

    def stop_request(self) -> tuple[str, str] | None:
        """A (reason, detail) pair when what was observed requires stopping the program."""
        return None

    def close(self) -> dict[str, Any]:
        """What was learned, for ``exit.json``."""
        return {}


@dataclass
class _Series:
    name: str
    unit: str
    source: str
    declared: bool
    handle: BinaryIO
    samples: int = 0
    non_finite: int = 0
    stored: int = 0
    first_value: float | None = None
    first_step: int | None = None
    last_value: float | None = None
    last_non_finite: NonFinite | None = None
    last_step: int | None = None
    last_time: float | None = None
    last_at: float | None = None
    min_value: float | None = None
    max_value: float | None = None

    def summary(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "unit": self.unit,
            "source": self.source,
            "declared": self.declared,
            "samples": self.samples,
            "non_finite": self.non_finite,
            "stored": self.stored,
            "first_value": self.first_value,
            "first_step": self.first_step,
            "last_value": self.last_value,
            "last_non_finite": self.last_non_finite,
            "last_step": self.last_step,
            "last_time": self.last_time,
            "last_at": self.last_at,
            "min_value": self.min_value,
            "max_value": self.max_value,
        }


@dataclass
class _Diagnosis:
    count: int = 0
    examples: list[str] = field(default_factory=list)


class MetricCollector(LineObserver):
    def __init__(self, run_dir: Path, spec: RunSpec, note: Note) -> None:
        self._dir = run_dir
        self._run_id = spec.run_id
        self._note = note
        self._declared: dict[str, MetricSpec] = {metric.name: metric for metric in spec.metrics}
        self._parsers = [(parser, re.compile(parser.pattern)) for parser in spec.parsers]
        self._matched = {parser.name: 0 for parser in spec.parsers}
        self._non_finite_policy = spec.guardrails.non_finite
        self._rules: dict[str, list[tuple[int, GuardrailRule]]] = {}
        for index, rule in enumerate(spec.guardrails.rules):
            self._rules.setdefault(rule.metric, []).append((index, rule))
        self._streaks = [0] * len(spec.guardrails.rules)
        self._max_bytes = spec.max_metrics_bytes
        self._series: dict[str, _Series] = {}
        self._file_names: dict[str, str] = {}  # lower-cased name -> name: files ignore case
        self._diagnoses: dict[str, _Diagnosis] = {}
        self._non_finite_noted: set[str] = set()
        self._stop: tuple[str, str] | None = None
        self._records = 0
        self._parsed_lines = 0
        self._program_events = 0
        self._bytes = 0
        self._truncated = False
        #: Grows with everything that is learned; tells readers whether the summary changed.
        self._revision = 0
        self._written_revision = -1
        self._last_summary = time.monotonic()

    # ------------------------------------------------------------------ lines

    def observe(self, stream: str, text: str, arrived: float) -> str:
        if stream == "build":
            return PLAIN
        if text.startswith("{") and '"numericos.' in text:
            became = self._record(text, arrived)
            if became is not None:
                return became
        matched = False
        for parser, pattern in self._parsers:
            if parser.stream not in ("any", stream):
                continue
            match = pattern.search(text)
            if match is None:
                continue
            matched = True
            self._matched[parser.name] += 1
            groups = match.groupdict()
            step = self._parsed_step(parser.name, groups.get("step"))
            sim_time = self._parsed_time(parser.name, groups.get("time"))
            for name in parser.metric_names:
                captured = groups.get(name)
                if captured is None:
                    continue
                try:
                    value, non_finite = number_from_text(captured)
                except ValueError:
                    self._diagnose(
                        "unparsable_value",
                        f"parser {parser.name}: {name} = {captured!r} is not a number",
                    )
                    continue
                self._sample(name, value, non_finite, step, sim_time, None, "parser", arrived)
        if matched:
            self._parsed_lines += 1
            self._revision += 1
        return PARSED if matched else PLAIN

    def _parsed_step(self, parser: str, captured: str | None) -> int | None:
        if captured is None:
            return None
        try:
            step = int(captured)
        except ValueError:
            self._diagnose("unparsable_value", f"parser {parser}: step = {captured!r}")
            return None
        return step if step >= 0 else None

    def _parsed_time(self, parser: str, captured: str | None) -> float | None:
        if captured is None:
            return None
        try:
            value, _non_finite = number_from_text(captured)
        except ValueError:
            value = None
        if value is None:
            self._diagnose("unparsable_value", f"parser {parser}: time = {captured!r}")
        return value

    def _record(self, text: str, arrived: float) -> str | None:
        """Handle a line that looks like a NumericOS record. None: it is not one after all."""
        try:
            document = json.loads(text)
        except ValueError:
            self._diagnose("malformed_record", f"not valid JSON: {text[:160]}")
            return PLAIN
        if not isinstance(document, dict):
            return None
        schema = document.get("schema")
        try:
            if schema == METRIC_SCHEMA:
                self._metric_record(parse_metric_record(document), arrived)
                return RECORD
            if schema == EVENT_SCHEMA:
                event = parse_program_event(document)
                self._program_events += 1
                self._revision += 1
                if self._program_events <= MAX_PROGRAM_EVENTS:
                    self._note("program_event", **event.model_dump())
                return RECORD
        except RecordError as error:
            self._diagnose("malformed_record", f"{error}: {text[:160]}")
            return PLAIN
        if isinstance(schema, str) and schema.startswith("numericos."):
            self._diagnose("unsupported_schema", schema)
            return PLAIN
        return None

    def _metric_record(self, record: MetricRecord, arrived: float) -> None:
        self._records += 1
        if record.run_id is not None and record.run_id != self._run_id:
            self._diagnose("run_id_mismatch", f"{record.name}: record says {record.run_id}")
        declared = self._declared.get(record.name)
        if declared is not None and declared.sampled_by != "instrumentation":
            self._diagnose(
                "source_mismatch",
                f"{record.name} is declared as measured by the {declared.sampled_by}; "
                "the record the program emitted for it was ignored",
            )
            return
        if declared is not None and record.unit and declared.unit and record.unit != declared.unit:
            self._diagnose(
                "unit_mismatch",
                f"{record.name}: the contract says {declared.unit!r}, the record {record.unit!r}",
            )
        self._sample(
            record.name,
            record.value,
            record.non_finite,
            record.step,
            record.time,
            record.timestamp_utc,
            "instrumentation",
            arrived,
            unit=record.unit or "",
        )

    # ------------------------------------------------------------------ samples

    def _open(self, name: str, source: str, unit: str) -> _Series | None:
        declared = self._declared.get(name)
        taken = self._file_names.get(name.lower())
        if taken is not None and taken != name:
            self._diagnose("name_collision", f"{name} differs from {taken} only by case; ignored")
            return None
        if declared is None:
            undeclared = sum(not series.declared for series in self._series.values())
            if undeclared >= MAX_UNDECLARED:
                self._diagnose("undeclared_dropped", name)
                return None
            self._diagnose("undeclared_metric", name)
        directory = self._dir / layout.METRICS
        directory.mkdir(exist_ok=True)
        self._file_names[name.lower()] = name
        series = _Series(
            name=name,
            unit=declared.unit if declared is not None else unit,
            source=source,
            declared=declared is not None,
            handle=(directory / f"{name}.jsonl").open("ab", buffering=0),
        )
        self._series[name] = series
        return series

    def _sample(
        self,
        name: str,
        value: float | None,
        non_finite: NonFinite | None,
        step: int | None,
        sim_time: float | None,
        source_timestamp: str | None,
        source: str,
        arrived: float,
        *,
        unit: str = "",
    ) -> None:
        series = self._series.get(name) or self._open(name, source, unit)
        if series is None:
            return
        series.samples += 1
        if series.samples == 1:
            series.first_value, series.first_step = value, step
        series.last_value, series.last_non_finite = value, non_finite
        series.last_step, series.last_time, series.last_at = step, sim_time, round(arrived, 6)
        if value is None:
            series.non_finite += 1
        else:
            series.min_value = value if series.min_value is None else min(series.min_value, value)
            series.max_value = value if series.max_value is None else max(series.max_value, value)

        stored: dict[str, Any] = {"t": round(arrived, 6), "v": value}
        if non_finite is not None:
            stored["nf"] = non_finite
        if step is not None:
            stored["s"] = step
        if sim_time is not None:
            stored["x"] = sim_time
        if source_timestamp is not None:
            stored["ts"] = source_timestamp
        encoded = json.dumps(stored, separators=(",", ":")).encode() + b"\n"
        if self._bytes + len(encoded) <= self._max_bytes:
            series.handle.write(encoded)
            series.stored += 1
            self._bytes += len(encoded)
        elif not self._truncated:
            self._truncated = True
            self._note("metrics_truncated", limit_bytes=self._max_bytes)
        self._revision += 1
        self._guard(name, value, non_finite, step)

    def _guard(
        self, name: str, value: float | None, non_finite: NonFinite | None, step: int | None
    ) -> None:
        """A NaN or an infinity is always noted. A bound of the contract is violated when the
        metric has been beyond it for as many consecutive samples as its patience says; a
        non-finite sample is beyond every bound."""
        at_step = f" at step {step}" if step is not None else ""
        if non_finite is not None and name not in self._non_finite_noted:
            self._non_finite_noted.add(name)
            self._note(
                "metric_non_finite",
                metric=name,
                value=non_finite,
                step=step,
                action=self._non_finite_policy,
            )
            if self._non_finite_policy == "halt" and self._stop is None:
                self._stop = ("guardrail", f"metric {name} became {non_finite}{at_step}")
        for index, rule in self._rules.get(name, ()):
            if value is None:
                beyond = True
            elif rule.above is not None:
                beyond = value > rule.above
            else:
                assert rule.below is not None  # a rule has exactly one bound
                beyond = value < rule.below
            self._streaks[index] = self._streaks[index] + 1 if beyond else 0
            if self._streaks[index] != rule.patience:
                continue  # not there yet, or already said for this stretch
            bound = "above" if rule.above is not None else "below"
            threshold = rule.above if rule.above is not None else rule.below
            self._note(
                "guardrail_violated",
                metric=name,
                bound=bound,
                threshold=threshold,
                value=value,
                non_finite=non_finite,
                step=step,
                consecutive=rule.patience,
                action=rule.action,
            )
            if rule.action == "halt" and self._stop is None:
                shown = non_finite if value is None else repr(value)
                self._stop = (
                    "guardrail",
                    f"metric {name} was {bound} {threshold} for {rule.patience} consecutive "
                    f"sample(s); the last one was {shown}{at_step}",
                )

    def _diagnose(self, kind: str, example: str) -> None:
        diagnosis = self._diagnoses.setdefault(kind, _Diagnosis())
        diagnosis.count += 1
        if len(diagnosis.examples) < MAX_EXAMPLES and example not in diagnosis.examples:
            diagnosis.examples.append(example)
        self._revision += 1

    def measured(self, values: dict[str, float | None], arrived: float) -> None:
        """Record what the monitor itself measured of the program (wall time, CPU time, peak
        memory) for the metrics the contract asks the supervisor to measure."""
        for name, value in values.items():
            declared = self._declared.get(name)
            if declared is None or declared.sampled_by != "supervisor" or value is None:
                continue
            self._sample(name, float(value), None, None, None, None, "supervisor", arrived)

    # ------------------------------------------------------------------ reporting

    def stop_request(self) -> tuple[str, str] | None:
        return self._stop

    def report(self) -> dict[str, Any]:
        """Everything learned so far, in a form that can be written as JSON."""
        return {
            "revision": self._revision,
            "records": self._records,
            "parsed_lines": self._parsed_lines,
            "program_events": self._program_events,
            "stored_bytes": self._bytes,
            "truncated": self._truncated,
            "parsers": dict(self._matched),
            "series": [self._series[name].summary() for name in sorted(self._series)],
            "diagnostics": [
                {"kind": kind, "count": diagnosis.count, "examples": diagnosis.examples}
                for kind, diagnosis in sorted(self._diagnoses.items())
            ],
        }

    def _write_summary(self) -> None:
        layout.write_json_atomic(self._dir / layout.METRICS_SUMMARY, self.report())
        self._written_revision = self._revision
        self._last_summary = time.monotonic()

    def tick(self) -> None:
        if (
            self._revision > 0
            and self._revision != self._written_revision
            and time.monotonic() - self._last_summary >= SUMMARY_SECONDS
        ):
            self._write_summary()

    def close(self) -> dict[str, Any]:
        for series in self._series.values():
            series.handle.close()
        if self._revision != self._written_revision:
            self._write_summary()  # also when nothing was learned: that is a result too
        return self.report()
