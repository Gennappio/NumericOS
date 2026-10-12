"""What the monitor learns from output lines: records, parsed values, anomalies, guardrails."""

from __future__ import annotations

import json
import math
from pathlib import Path
from typing import Any

import pytest

from numericos.core.metrics import RecordError, number_from_text, parse_metric_record
from numericos.executor import collector as collector_module
from numericos.executor import layout
from numericos.executor.collector import PARSED, PLAIN, RECORD, MetricCollector
from numericos.executor.spec import RunSpec

Json = dict[str, Any]
NOW = 1_800_000_000.0


class Notes:
    """Stands in for the monitor's journal."""

    def __init__(self) -> None:
        self.entries: list[Json] = []

    def __call__(self, kind: str, **fields: Any) -> None:
        self.entries.append({"type": kind, **fields})

    def of(self, kind: str) -> list[Json]:
        return [entry for entry in self.entries if entry["type"] == kind]


def make(tmp_path: Path, **spec: Any) -> tuple[MetricCollector, Notes]:
    notes = Notes()
    tmp_path.mkdir(parents=True, exist_ok=True)  # a run directory exists before its monitor
    run_spec = RunSpec.model_validate(
        {
            "run_id": "run_this",
            "argv": ["solver"],
            "cwd": str(tmp_path),
            "env": {},
            "wall_seconds": 60,
            "grace_seconds": 1,
            "max_output_bytes": 1_000_000,
            "resource_interval_seconds": 1,
            **spec,
        }
    )
    return MetricCollector(tmp_path, run_spec, notes), notes


def metric(name: str, value: Any, **fields: Any) -> str:
    return json.dumps({"schema": "numericos.metric.v1", "name": name, "value": value, **fields})


def declared(name: str, sampled_by: str = "instrumentation", unit: str = "") -> Json:
    return {"name": name, "unit": unit, "sampled_by": sampled_by}


def samples(tmp_path: Path, name: str) -> list[Json]:
    path = tmp_path / layout.METRICS / f"{name}.jsonl"
    return [json.loads(line) for line in path.read_text().splitlines()]


def series(report: Json) -> dict[str, Json]:
    return {item["name"]: item for item in report["series"]}


def diagnostics(report: Json) -> dict[str, Json]:
    return {item["kind"]: item for item in report["diagnostics"]}


# --------------------------------------------------------------------------- records (L2)


def test_a_metric_record_becomes_a_sample_and_is_not_kept_as_output(tmp_path: Path) -> None:
    collector, _notes = make(tmp_path, metrics=[declared("residual_l2", unit="1")])

    first = collector.observe("stdout", metric("residual_l2", 0.5, step=1, time=0.01), NOW)
    second = collector.observe("stderr", metric("residual_l2", 0.25, step=2), NOW + 1)
    ordinary = collector.observe("stdout", "iteration 2 done", NOW + 1)
    report = collector.close()

    assert (first, second, ordinary) == (RECORD, RECORD, PLAIN)
    assert samples(tmp_path, "residual_l2") == [
        {"t": NOW, "v": 0.5, "s": 1, "x": 0.01},
        {"t": NOW + 1, "v": 0.25, "s": 2},
    ]
    assert series(report)["residual_l2"] == {
        "name": "residual_l2",
        "unit": "1",
        "source": "instrumentation",
        "declared": True,
        "samples": 2,
        "non_finite": 0,
        "stored": 2,
        "first_value": 0.5,
        "first_step": 1,
        "last_value": 0.25,
        "last_non_finite": None,
        "last_step": 2,
        "last_time": None,
        "last_at": NOW + 1,
        "min_value": 0.25,
        "max_value": 0.5,
    }
    assert (report["records"], report["parsed_lines"]) == (2, 0)
    assert json.loads((tmp_path / layout.METRICS_SUMMARY).read_text()) == report


@pytest.mark.parametrize(
    ("emitted", "kind"),
    [
        ('"nan"', "nan"),
        ('"inf"', "inf"),
        ('"-inf"', "-inf"),
        ('"NaN"', "nan"),
        ('"-Infinity"', "-inf"),
        # What json.dumps(float("nan")) writes. It is not JSON, but it is what programs do.
        ("NaN", "nan"),
        ("Infinity", "inf"),
        ("-Infinity", "-inf"),
    ],
)
def test_a_non_finite_value_is_kept_as_a_typed_sample_however_it_was_written(
    tmp_path: Path, emitted: str, kind: str
) -> None:
    collector, notes = make(tmp_path, metrics=[declared("energy")])
    line = '{"schema":"numericos.metric.v1","name":"energy","step":7,"value":' + emitted + "}"

    became = collector.observe("stdout", line, NOW)
    report = collector.close()

    stored = (tmp_path / layout.METRICS / "energy.jsonl").read_text()
    assert became == RECORD
    assert json.loads(stored) == {"t": NOW, "v": None, "nf": kind, "s": 7}
    assert "NaN" not in stored and "Infinity" not in stored  # never written as a number
    assert series(report)["energy"]["non_finite"] == 1
    assert series(report)["energy"]["last_non_finite"] == kind
    assert (series(report)["energy"]["min_value"], series(report)["energy"]["max_value"]) == (
        None,
        None,
    )
    assert notes.of("metric_non_finite") == [
        {
            "type": "metric_non_finite",
            "metric": "energy",
            "value": kind,
            "step": 7,
            "action": "record",
        }
    ]


@pytest.mark.parametrize(
    ("line", "reason"),
    [
        ('{"schema":"numericos.metric.v1","name":"r","value":true}', "'value' must be a number"),
        ('{"schema":"numericos.metric.v1","name":"r","value":"big"}', "'value' must be a number"),
        ('{"schema":"numericos.metric.v1","name":"r"}', "'value' must be a number"),
        ('{"schema":"numericos.metric.v1","name":"9r","value":1}', "'name' must start with"),
        ('{"schema":"numericos.metric.v1","name":"r","value":1,"step":-1}', "'step' must be"),
        ('{"schema":"numericos.metric.v1","name":"r","value":1,"step":1.5}', "'step' must be"),
        ('{"schema":"numericos.metric.v1","name":"r","value":1,"stpe":3}', "unknown field 'stpe'"),
        ('{"schema":"numericos.metric.v1","name":"r","value":1', "not valid JSON"),
        ('{"schema":"numericos.metric.v2","name":"r","value":1}', "numericos.metric.v2"),
    ],
)
def test_a_record_that_is_not_valid_is_diagnosed_and_stays_in_the_output(
    tmp_path: Path, line: str, reason: str
) -> None:
    collector, _notes = make(tmp_path, metrics=[declared("r")])

    became = collector.observe("stdout", line, NOW)
    report = collector.close()

    assert became == PLAIN  # the line is still there for a person to read
    assert report["series"] == []
    (diagnosis,) = report["diagnostics"]
    assert diagnosis["count"] == 1
    assert reason in diagnosis["examples"][0]


def test_json_that_is_not_a_numericos_record_is_ordinary_output(tmp_path: Path) -> None:
    collector, _notes = make(tmp_path)

    lines = ['{"level": "info", "msg": "starting"}', "[1, 2, 3]", '{"schema": "other.thing.v1"}']
    became = [collector.observe("stdout", line, NOW) for line in lines]

    assert became == [PLAIN, PLAIN, PLAIN]
    assert collector.close()["diagnostics"] == []


def test_a_metric_the_contract_does_not_declare_is_kept_and_marked(tmp_path: Path) -> None:
    collector, _notes = make(tmp_path, metrics=[declared("residual")])

    collector.observe("stdout", metric("residual", 1.0), NOW)
    collector.observe("stdout", metric("debug_norm", 3.0, unit="m"), NOW)
    report = collector.close()

    assert series(report)["residual"]["declared"] is True
    assert (series(report)["debug_norm"]["declared"], series(report)["debug_norm"]["unit"]) == (
        False,
        "m",
    )
    assert diagnostics(report)["undeclared_metric"]["examples"] == ["debug_norm"]


def test_undeclared_metrics_are_kept_only_up_to_a_limit(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(collector_module, "MAX_UNDECLARED", 2)
    collector, _notes = make(tmp_path)

    for index in range(5):  # e.g. a program that puts the step number into the name
        collector.observe("stdout", metric(f"residual_step_{index}", 1.0), NOW)
    report = collector.close()

    assert sorted(series(report)) == ["residual_step_0", "residual_step_1"]
    assert diagnostics(report)["undeclared_dropped"]["count"] == 3


def test_records_that_contradict_the_contract_are_said_so(tmp_path: Path) -> None:
    collector, _notes = make(
        tmp_path,
        metrics=[
            declared("length", unit="m"),
            declared("wall_time", "supervisor", "s"),
        ],
    )

    collector.observe("stdout", metric("length", 2.0, unit="cm"), NOW)
    collector.observe("stdout", metric("wall_time", 9.9), NOW)
    collector.observe("stdout", metric("length", 3.0, run_id="run_other"), NOW)
    report = collector.close()

    found = diagnostics(report)
    assert series(report)["length"]["samples"] == 2  # recorded as sent: nothing is converted
    assert series(report)["length"]["unit"] == "m"
    assert "wall_time" not in series(report)  # the supervisor measures it, not the program
    assert "'m'" in found["unit_mismatch"]["examples"][0]
    assert "supervisor" in found["source_mismatch"]["examples"][0]
    assert "run_other" in found["run_id_mismatch"]["examples"][0]


def test_names_that_differ_only_by_case_do_not_share_a_file(tmp_path: Path) -> None:
    collector, _notes = make(tmp_path)

    collector.observe("stdout", metric("Residual", 1.0), NOW)
    collector.observe("stdout", metric("residual", 2.0), NOW)
    report = collector.close()

    assert sorted(series(report)) == ["Residual"]
    assert diagnostics(report)["name_collision"]["count"] == 1


def test_a_program_can_put_events_on_the_timeline_of_its_run(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(collector_module, "MAX_PROGRAM_EVENTS", 2)
    collector, notes = make(tmp_path)
    event = {"schema": "numericos.event.v1", "name": "checkpoint", "message": "wrote u_100.npy"}

    became = [
        collector.observe("stdout", json.dumps({**event, "step": step}), NOW) for step in range(3)
    ]
    bad = collector.observe("stdout", json.dumps({**event, "severity": "fatal"}), NOW)
    report = collector.close()

    assert became == [RECORD, RECORD, RECORD]
    assert bad == PLAIN
    assert notes.of("program_event") == [
        {
            "type": "program_event",
            "name": "checkpoint",
            "message": "wrote u_100.npy",
            "severity": "info",
            "step": step,
        }
        for step in range(2)  # the third is counted, not kept
    ]
    assert report["program_events"] == 3


# --------------------------------------------------------------------------- parsers (L1)


def test_a_parser_extracts_metrics_from_ordinary_output_lines(tmp_path: Path) -> None:
    collector, _notes = make(
        tmp_path,
        metrics=[declared("residual", "parser"), declared("cfl", "parser")],
        parsers=[
            {
                "name": "iteration",
                "pattern": r"^it\s+(?P<step>\d+)\s+res=(?P<residual>\S+)(\s+cfl=(?P<cfl>\S+))?",
                "stream": "stdout",
            }
        ],
    )

    became = [
        collector.observe("stdout", "it 10 res=1.5e-03 cfl=0.4", NOW),
        collector.observe("stdout", "it 20 res=7.0E-04", NOW),
        collector.observe("stdout", "writing checkpoint", NOW),
        collector.observe("stderr", "it 30 res=1.0e-05", NOW),  # not the parser's stream
    ]
    report = collector.close()

    assert became == [PARSED, PARSED, PLAIN, PLAIN]  # parsed lines remain lines of output
    assert samples(tmp_path, "residual") == [
        {"t": NOW, "v": 0.0015, "s": 10},
        {"t": NOW, "v": 0.0007, "s": 20},
    ]
    assert samples(tmp_path, "cfl") == [{"t": NOW, "v": 0.4, "s": 10}]
    assert series(report)["residual"]["source"] == "parser"
    assert (report["parsed_lines"], report["records"]) == (2, 0)
    assert report["parsers"] == {"iteration": 2}


def test_a_parser_can_read_the_step_and_the_time_of_a_sample_from_the_line(
    tmp_path: Path,
) -> None:
    collector, _notes = make(
        tmp_path,
        metrics=[declared("residual", "parser")],
        parsers=[
            {
                "name": "log",
                "pattern": r"n=(?P<step>\S+)\s+t=(?P<time>\S+)\s+res=(?P<residual>\S+)",
            }
        ],
    )

    collector.observe("stdout", "n=4 t=2.5D-02 res=1.0e-3", NOW)
    collector.observe("stdout", "n=four t=soon res=5.0e-4", NOW)
    report = collector.close()

    assert samples(tmp_path, "residual") == [
        {"t": NOW, "v": 0.001, "s": 4, "x": 0.025},
        {"t": NOW, "v": 0.0005},  # the value is kept; what could not be read is left out
    ]
    assert diagnostics(report)["unparsable_value"]["count"] == 2


def test_numbers_are_read_as_solvers_print_them(tmp_path: Path) -> None:
    assert number_from_text("1.5D-03") == (0.0015, None)  # Fortran double precision
    assert number_from_text(" 2.d+2 ") == (200.0, None)
    assert number_from_text("-3") == (-3.0, None)
    assert number_from_text("NaN") == (None, "nan")
    assert number_from_text("-Infinity") == (None, "-inf")
    assert number_from_text("1e999") == (None, "inf")  # beyond double precision
    with pytest.raises(ValueError, match="could not convert"):
        number_from_text("****")  # a Fortran field overflow


def test_a_captured_text_that_is_not_a_number_is_diagnosed_not_guessed(tmp_path: Path) -> None:
    collector, _notes = make(
        tmp_path,
        metrics=[declared("residual", "parser")],
        parsers=[{"name": "res", "pattern": r"res=(?P<residual>\S+)"}],
    )

    collector.observe("stdout", "res=******", NOW)
    collector.observe("stdout", "res=0.5", NOW)
    report = collector.close()

    assert series(report)["residual"]["samples"] == 1
    assert diagnostics(report)["unparsable_value"]["count"] == 1
    assert "******" in diagnostics(report)["unparsable_value"]["examples"][0]


def test_a_parser_that_never_matches_is_visible_as_such(tmp_path: Path) -> None:
    collector, _notes = make(
        tmp_path,
        metrics=[declared("residual", "parser")],
        parsers=[{"name": "res", "pattern": r"residual:\s+(?P<residual>\S+)"}],
    )

    collector.observe("stdout", "res = 0.5", NOW)
    report = collector.close()

    assert report["parsers"] == {"res": 0}
    assert report["series"] == []


# --------------------------------------------------------------------------- guardrails


def test_a_bound_is_violated_only_after_its_patience_of_consecutive_samples(
    tmp_path: Path,
) -> None:
    collector, notes = make(
        tmp_path,
        metrics=[declared("max_abs_u")],
        guardrails={"rules": [{"metric": "max_abs_u", "above": 1.0, "patience": 3}]},
    )

    values = [0.9, 1.5, 1.6, 0.8, 1.2, 1.3]  # two samples beyond, back inside, two beyond
    for step, value in enumerate(values):
        collector.observe("stdout", metric("max_abs_u", value, step=step), NOW)
    not_yet = collector.stop_request()
    collector.observe("stdout", metric("max_abs_u", 1.4, step=6), NOW)

    assert not_yet is None  # noise is not divergence
    assert collector.stop_request() == (
        "guardrail",
        "metric max_abs_u was above 1.0 for 3 consecutive sample(s); "
        "the last one was 1.4 at step 6",
    )
    assert notes.of("guardrail_violated") == [
        {
            "type": "guardrail_violated",
            "metric": "max_abs_u",
            "bound": "above",
            "threshold": 1.0,
            "value": 1.4,
            "non_finite": None,
            "step": 6,
            "consecutive": 3,
            "action": "halt",
        }
    ]


def test_a_rule_that_only_records_does_not_stop_the_program_and_speaks_once_per_stretch(
    tmp_path: Path,
) -> None:
    collector, notes = make(
        tmp_path,
        metrics=[declared("mass")],
        guardrails={"rules": [{"metric": "mass", "below": 0.99, "action": "record"}]},
    )

    for step, value in enumerate([1.0, 0.98, 0.97, 0.96, 1.0, 0.5]):
        collector.observe("stdout", metric("mass", value, step=step), NOW)

    assert collector.stop_request() is None
    assert [note["step"] for note in notes.of("guardrail_violated")] == [1, 5]


def test_a_non_finite_value_stops_the_program_only_if_the_contract_says_so(
    tmp_path: Path,
) -> None:
    recording, recording_notes = make(tmp_path / "record", metrics=[declared("r")])
    halting, _notes = make(
        tmp_path / "halt", metrics=[declared("r")], guardrails={"non_finite": "halt"}
    )

    for collector in (recording, halting):
        collector.observe("stdout", metric("r", "nan", step=12), NOW)
        collector.observe("stdout", metric("r", "nan", step=13), NOW)

    assert recording.stop_request() is None
    assert len(recording_notes.of("metric_non_finite")) == 1  # said once, counted every time
    assert recording.close()["series"][0]["non_finite"] == 2
    assert halting.stop_request() == ("guardrail", "metric r became nan at step 12")


def test_a_non_finite_sample_is_beyond_every_bound(tmp_path: Path) -> None:
    collector, _notes = make(
        tmp_path,
        metrics=[declared("r", "parser")],
        parsers=[{"name": "res", "pattern": r"res=(?P<r>\S+)"}],
        guardrails={"rules": [{"metric": "r", "below": 0.0, "patience": 2}]},
    )

    collector.observe("stdout", "res=inf", NOW)
    collector.observe("stdout", "res=nan", NOW)

    stop = collector.stop_request()
    assert stop is not None and stop[1].endswith("the last one was nan")


# --------------------------------------------------------------------------- bounds


def test_samples_beyond_the_size_limit_are_counted_but_not_stored(tmp_path: Path) -> None:
    collector, notes = make(tmp_path, metrics=[declared("r")], max_metrics_bytes=100)

    for step in range(50):
        collector.observe("stdout", metric("r", float(step), step=step), NOW)
    report = collector.close()

    summary = series(report)["r"]
    assert summary["samples"] == 50
    assert 0 < summary["stored"] < 50
    assert summary["stored"] == len(samples(tmp_path, "r"))
    assert (summary["last_value"], summary["max_value"]) == (49.0, 49.0)  # the summary goes on
    assert report["truncated"] is True
    assert notes.of("metrics_truncated") == [{"type": "metrics_truncated", "limit_bytes": 100}]


def test_the_summary_is_rewritten_as_the_series_grow(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(collector_module, "SUMMARY_SECONDS", 0.0)
    collector, _notes = make(tmp_path, metrics=[declared("r")])
    summary = tmp_path / layout.METRICS_SUMMARY

    collector.tick()
    before = summary.exists()
    collector.observe("stdout", metric("r", 1.0), NOW)
    collector.tick()
    during = json.loads(summary.read_text())
    collector.observe("stdout", metric("r", 2.0), NOW)
    collector.tick()
    later = json.loads(summary.read_text())

    assert before is False  # nothing to say yet
    assert during["series"][0]["samples"] == 1
    assert later["series"][0]["samples"] == 2
    assert later["revision"] > during["revision"]


def test_build_output_is_never_read_for_metrics(tmp_path: Path) -> None:
    collector, _notes = make(tmp_path, metrics=[declared("r")])

    became = collector.observe("build", metric("r", 1.0), NOW)

    assert became == PLAIN
    assert collector.close()["series"] == []


# --------------------------------------------------------------------------- the record itself


def test_a_record_is_validated_field_by_field() -> None:
    record = parse_metric_record(
        {
            "schema": "numericos.metric.v1",
            "run_id": "run_x",
            "name": "residual_l2",
            "step": 42,
            "value": 0.00032,
            "unit": "dimensionless",
            "timestamp_utc": "2026-10-09T13:14:15Z",
        }
    )

    assert (record.name, record.value, record.step) == ("residual_l2", 0.00032, 42)
    assert record.timestamp_utc == "2026-10-09T13:14:15Z"
    assert parse_metric_record({"name": "n", "value": 3}).value == 3.0
    assert parse_metric_record({"name": "n", "value": json.loads("1e999")}).non_finite == "inf"
    with pytest.raises(RecordError, match="too large"):
        parse_metric_record({"name": "n", "value": 10**400})
    with pytest.raises(RecordError, match="finite"):
        parse_metric_record({"name": "n", "value": 1, "time": math.inf})
