"""The heat-equation example by itself: what it prints, checked against closed forms.

The initial condition is one discrete sine mode, so in exact arithmetic the scheme multiplies
it by g = 1 - 8 r sin^2(pi h / 2) at every step. Norm and error then have closed forms, which
the program must reproduce to round-off.
"""

from __future__ import annotations

import json
import math
import subprocess
import sys
from pathlib import Path
from typing import Any

import pytest

from numericos.core.metrics import METRIC_SCHEMA, parse_metric_record

EXAMPLE = Path(__file__).resolve().parents[2] / "examples" / "heat2d-python"
Json = dict[str, Any]


def run_program(tmp_path: Path, *arguments: str) -> tuple[list[Json], list[str]]:
    """Run heat2d.py; return its metric records and its other output lines."""
    completed = subprocess.run(
        [sys.executable, str(EXAMPLE / "heat2d.py"), *arguments],
        capture_output=True,
        text=True,
        cwd=tmp_path,
        timeout=120,
        check=True,
    )
    records, lines = [], []
    for line in completed.stdout.splitlines():
        if line.startswith("{"):
            records.append(json.loads(line))
        else:
            lines.append(line)
    return records, lines


def series(records: list[Json], name: str) -> dict[int, Any]:
    return {record["step"]: record["value"] for record in records if record["name"] == name}


def test_norm_and_error_follow_their_closed_forms(tmp_path: Path) -> None:
    grid, dt, steps, alpha = 16, 0.0008, 60, 1.0
    records, lines = run_program(
        tmp_path, "--dt", str(dt), "--grid", str(grid), "--steps", str(steps)
    )
    h = 1.0 / grid
    r = alpha * dt / h**2
    g = 1.0 - 8.0 * r * math.sin(math.pi * h / 2.0) ** 2
    assert r < 0.25  # a stable setting of this scheme

    errors = series(records, "l2_error")
    largest = series(records, "max_abs_u")
    norms = {
        int(line.split()[1]): float(line.split("norm=")[1])
        for line in lines
        if line.startswith("step")
    }

    assert sorted(errors) == sorted(largest) == sorted(norms) == list(range(0, steps + 1, 10))
    for step in errors:
        decay = math.exp(-2.0 * math.pi**2 * alpha * step * dt)
        assert errors[step] == pytest.approx(0.5 * abs(g**step - decay), abs=1e-13)
        assert norms[step] == pytest.approx(0.5 * g**step, rel=1e-9)  # printed with 11 digits
        assert largest[step] == pytest.approx(g**step, abs=1e-13)
    assert largest[0] == 1.0
    assert all(
        later <= earlier
        for earlier, later in zip(largest.values(), list(largest.values())[1:], strict=False)
    )
    assert (tmp_path / "u_final.csv").read_text().count("\n") == grid + 1


def test_every_record_is_a_valid_metric_record_with_step_and_time(tmp_path: Path) -> None:
    records, _lines = run_program(tmp_path, "--dt", "0.0008", "--grid", "8", "--steps", "20")

    assert {record["schema"] for record in records} == {METRIC_SCHEMA}
    for record in records:
        parsed = parse_metric_record(record)
        assert parsed.step is not None
        assert parsed.time == pytest.approx(parsed.step * 0.0008)


def test_above_the_limit_of_the_scheme_round_off_grows_without_bound(tmp_path: Path) -> None:
    grid = 16
    limit = 1.0 / (4.0 * math.cos(math.pi / (2 * grid)) ** 2)  # exact for this grid
    h2 = 1.0 / grid**2

    just_below, _ = run_program(
        tmp_path, "--dt", repr(0.999 * limit * h2), "--grid", str(grid), "--steps", "400"
    )
    above, _ = run_program(
        tmp_path, "--dt", repr(1.2 * limit * h2), "--grid", str(grid), "--steps", "400"
    )

    assert max(series(just_below, "max_abs_u").values()) == 1.0  # bounded by its initial value
    assert series(above, "max_abs_u")[400] > 1e6


def test_overflow_is_reported_as_typed_non_finite_values_not_hidden(tmp_path: Path) -> None:
    # r = 0.5 on a coarse grid: the field overflows to infinity, then becomes NaN.
    completed = subprocess.run(
        [
            sys.executable,
            str(EXAMPLE / "heat2d.py"),
            "--dt",
            "0.0078125",
            "--grid",
            "8",
            "--steps",
            "1200",
            "--report-every",
            "50",
        ],
        capture_output=True,
        text=True,
        cwd=tmp_path,
        timeout=120,
        check=True,  # the program does not crash: it reports what it computed
    )

    assert "NaN" not in completed.stdout and "Infinity" not in completed.stdout  # valid JSON only
    records = [json.loads(line) for line in completed.stdout.splitlines() if line.startswith("{")]
    largest = series(records, "max_abs_u")
    assert largest[1200] == "nan"  # a NaN in the field is not lost by taking a maximum
    assert "inf" in largest.values() or "nan" in largest.values()
    assert parse_metric_record(records[-1]).non_finite in ("nan", "inf")
