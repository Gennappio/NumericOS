"""How much of a run is observed, level by level.

L0: the process, seen from outside. L1: values extracted from its output by the parsers of the
contract. L2: metrics the program emits itself. L3: validators that judge a result. A level
that has data says nothing about validity; a level without data says so instead of looking
complete.
"""

from __future__ import annotations

from typing import Any

from numericos.core.experiment import ExperimentProtocol
from numericos.core.metrics import (
    Coverage,
    CoverageLevel,
    CoverageStatus,
    MetricCoverage,
    SeriesSummary,
)


def _reach(observed: int, asked: int, *, active: bool) -> CoverageStatus:
    if observed == asked:
        return "observed"
    if observed > 0:
        return "partial"
    return "waiting" if active else "missing"


def build_coverage(
    protocol: ExperimentProtocol,
    series: list[SeriesSummary],
    report: dict[str, Any],
    *,
    started: bool,
    active: bool,
) -> Coverage:
    """Coverage of one run. ``started``: its program was started; ``active``: it may still
    change by itself."""
    by_name = {item.name: item for item in series}

    def has_samples(name: str) -> bool:
        return name in by_name and by_name[name].samples > 0

    metrics = [
        MetricCoverage(
            name=metric.name,
            unit=metric.unit,
            source=metric.sampled_by,
            status=("observed" if has_samples(metric.name) else "waiting" if active else "missing"),
            samples=by_name[metric.name].samples if metric.name in by_name else 0,
            non_finite=by_name[metric.name].non_finite if metric.name in by_name else 0,
        )
        for metric in protocol.metrics
    ]
    undeclared = sorted(item.name for item in series if not item.declared)

    if started:
        process = CoverageLevel(
            level="L0",
            title="Process",
            status="observed",
            detail=(
                "output and resource samples of the process; exit status and exact totals "
                "follow when it ends"
                if active
                else "exit status, wall and CPU time, memory and output of the process"
            ),
        )
    else:
        process = CoverageLevel(
            level="L0",
            title="Process",
            status="waiting" if active else "missing",
            detail="the program has not started" if active else "the program never ran",
        )

    parsed = [metric.name for metric in protocol.metrics if metric.sampled_by == "parser"]
    parsers = protocol.observability.parsers
    if not parsers:
        from_output = CoverageLevel(
            level="L1",
            title="Output parsers",
            status="not_configured",
            detail="the contract declares no parser for the program's output",
        )
    else:
        seen = sum(has_samples(name) for name in parsed)
        matched = report.get("parsers", {})
        silent = sorted(parser.name for parser in parsers if not matched.get(parser.name))
        detail = f"{seen} of {len(parsed)} parsed metrics have samples"
        if silent and started:
            detail += "; no line matched " + ", ".join(silent)
        from_output = CoverageLevel(
            level="L1",
            title="Output parsers",
            status=_reach(seen, len(parsed), active=active),
            detail=detail,
        )

    emitted = [metric.name for metric in protocol.metrics if metric.sampled_by == "instrumentation"]
    records = int(report.get("records", 0))
    if emitted:
        seen = sum(has_samples(name) for name in emitted)
        instrumented = CoverageLevel(
            level="L2",
            title="Instrumentation",
            status=_reach(seen, len(emitted), active=active),
            detail=f"{seen} of {len(emitted)} metrics the program should emit have samples",
        )
    elif undeclared:
        instrumented = CoverageLevel(
            level="L2",
            title="Instrumentation",
            status="observed",
            detail=f"{records} records, all of metrics the contract does not declare",
        )
    else:
        instrumented = CoverageLevel(
            level="L2",
            title="Instrumentation",
            status="not_configured",
            detail="the contract declares no metric emitted by the program",
        )

    validators = CoverageLevel(
        level="L3",
        title="Validators",
        status="not_configured",
        detail="no validator is configured: nothing here says whether the result is valid",
    )
    return Coverage(
        levels=[process, from_output, instrumented, validators],
        metrics=metrics,
        undeclared=undeclared,
    )
