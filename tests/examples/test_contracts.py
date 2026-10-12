"""The contract files shipped with the examples say true things and are valid contracts."""

from __future__ import annotations

import math
from pathlib import Path

import pytest
import yaml

from numericos.core.experiment import ExperimentProtocol

EXAMPLES = Path(__file__).resolve().parents[2] / "examples"
CONTRACTS = sorted(EXAMPLES.glob("*/experiment*.yaml"))


def load(path: Path) -> ExperimentProtocol:
    document = yaml.safe_load(path.read_text())
    document.pop("name")
    return ExperimentProtocol.model_validate(document)


@pytest.mark.parametrize("path", CONTRACTS, ids=lambda path: f"{path.parent.name}/{path.name}")
def test_every_example_contract_is_a_valid_contract(path: Path) -> None:
    protocol = load(path)

    assert protocol.execution.workdir == f"examples/{path.parent.name}"
    assert (EXAMPLES / path.parent.name / protocol.execution.command[1]).exists() or (
        protocol.execution.build  # the program is built by the run
    )
    assert all(
        isinstance(value, float)
        for values in protocol.independent_variables.values()
        for value in values
        if not isinstance(value, str)
    )  # YAML reads 1e-05 without a dot as text


def test_the_examples_ship_three_contracts() -> None:
    assert [f"{path.parent.name}/{path.name}" for path in CONTRACTS] == [
        "heat2d-python/experiment-fine.yaml",
        "heat2d-python/experiment.yaml",
        "sparse-cg-cpp/experiment.yaml",
    ]


@pytest.mark.parametrize(
    ("name", "stable", "unstable"),
    [
        ("experiment.yaml", [0.0002, 0.00024], [0.00026, 0.0003]),
        ("experiment-fine.yaml", [1.4e-05], [1.7e-05]),
    ],
)
def test_the_heat_contracts_declare_time_steps_on_both_sides_of_the_exact_limit(
    name: str, stable: list[float], unstable: list[float]
) -> None:
    protocol = load(EXAMPLES / "heat2d-python" / name)
    grid, alpha = protocol.controls["grid"], protocol.controls["alpha"]
    assert isinstance(grid, int) and isinstance(alpha, float)
    # The limit of the FTCS scheme on a grid with N intervals and zero boundary values.
    limit = 1.0 / (4.0 * math.cos(math.pi / (2 * grid)) ** 2)

    r = {dt: alpha * dt * grid**2 for dt in protocol.independent_variables["dt"]}  # type: ignore[operator]

    assert sorted(r) == sorted([*stable, *unstable])
    assert all(r[dt] <= 0.25 < limit for dt in stable)  # sufficient on every grid
    assert all(r[dt] > limit for dt in unstable)
    rule = protocol.guardrails.rules[0]
    assert (rule.metric, rule.above, rule.action) == ("max_abs_u", 1.0, "halt")
    assert protocol.guardrails.non_finite == "halt"
