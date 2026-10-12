"""Coverage of a run, level by level: what is observed, what is awaited, what is missing."""

from __future__ import annotations

from typing import Any

from numericos.core.experiment import ExperimentProtocol
from numericos.core.metrics import SeriesSummary
from numericos.observability.coverage import build_coverage
from tests import factories


def protocol(**overrides: Any) -> ExperimentProtocol:
    return ExperimentProtocol.model_validate(factories.protocol(**overrides))


def summary(name: str, source: str, *, samples: int = 5, declared: bool = True) -> SeriesSummary:
    return SeriesSummary(
        name=name,
        unit="",
        source=source,
        declared=declared,
        samples=samples,
        non_finite=0,
        stored=samples,
    )


PARSED = {
    "metrics": [
        {"name": "residual_l2", "sampled_by": "instrumentation"},
        {"name": "energy", "sampled_by": "parser"},
        {"name": "wall_time", "unit": "s", "sampled_by": "supervisor"},
    ],
    "observability": {"parsers": [{"name": "log", "pattern": r"energy=(?P<energy>\S+)"}]},
}


def statuses(coverage: Any) -> dict[str, str]:
    return {level.level: level.status for level in coverage.levels}


def test_before_the_program_starts_everything_asked_for_is_awaited() -> None:
    coverage = build_coverage(protocol(**PARSED), [], {}, started=False, active=True)

    assert statuses(coverage) == {
        "L0": "waiting",
        "L1": "waiting",
        "L2": "waiting",
        "L3": "not_configured",
    }
    assert {metric.status for metric in coverage.metrics} == {"waiting"}


def test_a_finished_run_with_all_its_metrics_is_observed_but_not_validated() -> None:
    series = [
        summary("residual_l2", "instrumentation"),
        summary("energy", "parser"),
        summary("wall_time", "supervisor", samples=1),
    ]
    report = {"records": 5, "parsers": {"log": 5}}

    coverage = build_coverage(protocol(**PARSED), series, report, started=True, active=False)

    assert statuses(coverage) == {
        "L0": "observed",
        "L1": "observed",
        "L2": "observed",
        "L3": "not_configured",
    }
    assert {metric.status for metric in coverage.metrics} == {"observed"}


def test_what_was_asked_for_and_never_measured_is_missing_and_named() -> None:
    series = [summary("residual_l2", "instrumentation")]
    report = {"records": 5, "parsers": {"log": 0}}

    coverage = build_coverage(protocol(**PARSED), series, report, started=True, active=False)

    by_level = {level.level: level for level in coverage.levels}
    assert by_level["L1"].status == "missing"
    assert "no line matched log" in by_level["L1"].detail
    assert {metric.name: metric.status for metric in coverage.metrics} == {
        "residual_l2": "observed",
        "energy": "missing",
        "wall_time": "missing",
    }


def test_a_program_that_never_ran_has_no_process_level_either() -> None:
    coverage = build_coverage(protocol(**PARSED), [], {}, started=False, active=False)

    assert statuses(coverage)["L0"] == "missing"
    assert "never ran" in coverage.levels[0].detail


def test_metrics_outside_the_contract_are_listed_as_such() -> None:
    plain = protocol(metrics=[])
    series = [summary("debug_norm", "instrumentation", declared=False)]

    coverage = build_coverage(plain, series, {"records": 5}, started=True, active=False)

    assert coverage.undeclared == ["debug_norm"]
    assert statuses(coverage)["L2"] == "observed"
    assert "does not declare" in coverage.levels[2].detail
    assert coverage.metrics == []
