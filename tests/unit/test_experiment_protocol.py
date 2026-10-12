"""The experiment contract: what it accepts, how runs are derived from it."""

from __future__ import annotations

from typing import Any

import pytest
from pydantic import ValidationError

from numericos.core.errors import InvalidRequestError
from numericos.core.experiment import (
    ExperimentProtocol,
    protocol_digest,
    render_command,
    render_value,
    resolve_parameters,
)
from tests import factories


def parse(**overrides: Any) -> ExperimentProtocol:
    return ExperimentProtocol.model_validate(factories.protocol(**overrides))


def execution(**overrides: Any) -> dict[str, Any]:
    return {**factories.protocol()["execution"], **overrides}


def test_a_complete_contract_is_accepted_and_keeps_its_schema_tag() -> None:
    protocol = parse()

    assert protocol.to_json()["schema"] == "numericos.experiment.v1"
    assert protocol.execution.code.mode == "ref"
    assert protocol.execution.code.ref == "HEAD"
    assert protocol.guardrails.non_finite == "record"
    assert protocol.limits.grace_seconds == 10.0
    assert not protocol.needs_seed


@pytest.mark.parametrize(
    ("overrides", "message"),
    [
        ({"schema": "numericos.experiment.v2"}, "numericos.experiment.v1"),
        ({"limits": {}}, "wall_seconds"),
        ({"limits": {"wall_seconds": 0}}, "greater than 0"),
        ({"surprise": 1}, "Extra inputs are not permitted"),
        ({"independent_variables": {"dt": []}}, "needs at least one value"),
        ({"independent_variables": {"dt": [0.01, 0.01]}}, "repeats a value"),
        ({"controls": {"dt": 0.01, "grid": 32, "steps": 1}}, "both an independent variable"),
        ({"controls": {"seed": 1, "grid": 32, "steps": 1}}, "'seed' is set per run"),
        ({"controls": {"grid size": 32, "steps": 1}}, "not a valid parameter name"),
        ({"execution": execution(command=[])}, "at least 1 item"),
        ({"execution": execution(command=["solve", "--tol", "{tolerance}"])}, "tolerance"),
        ({"execution": execution(command=["solve", "{dt:.3f}"])}, "only {name} is allowed"),
        ({"execution": execution(command=["solve", "{dt.real}"])}, "only {name} is allowed"),
        ({"execution": execution(workdir="../elsewhere")}, "relative path"),
        ({"execution": execution(workdir="/abs")}, "relative path"),
        ({"execution": execution(code={"mode": "ref", "ref": "--upload-pack=x"})}, "pattern"),
        ({"execution": execution(env={"NOT VALID": "1"})}, "environment variable name"),
        ({"execution": execution(inputs=[{"path": "data.bin", "sha256": "abc"}])}, "pattern"),
    ],
)
def test_malformed_contracts_are_rejected(overrides: dict[str, Any], message: str) -> None:
    with pytest.raises(ValidationError, match=message):
        parse(**overrides)


def test_metrics_must_be_measurable_by_what_the_contract_declares() -> None:
    parser = {"name": "residuals", "pattern": r"^iter (?P<step>\d+) res (?P<residual>\S+)$"}
    parsed_metric = {"name": "residual", "unit": "1", "sampled_by": "parser"}

    accepted = parse(metrics=[parsed_metric], observability={"parsers": [parser]})
    assert accepted.observability.parsers[0].metric_names == ["residual"]

    with pytest.raises(ValidationError, match="no parser extracts"):
        parse(metrics=[parsed_metric])
    with pytest.raises(ValidationError, match="declare it with sampled_by: parser"):
        parse(observability={"parsers": [parser]})
    with pytest.raises(ValidationError, match="not a valid regular expression"):
        parse(observability={"parsers": [{"name": "broken", "pattern": "(?P<x>["}]})
    with pytest.raises(ValidationError, match="at least one named group"):
        parse(observability={"parsers": [{"name": "nothing", "pattern": r"^(?P<step>\d+)$"}]})
    with pytest.raises(ValidationError, match="the supervisor does not measure"):
        parse(metrics=[{"name": "gpu_power", "sampled_by": "supervisor"}])
    with pytest.raises(ValidationError, match="metric names must be unique"):
        parse(metrics=[parsed_metric, parsed_metric], observability={"parsers": [parser]})


def test_guardrails_need_an_explicit_bound_on_a_declared_metric() -> None:
    rule = {"metric": "residual_l2", "above": 1e6, "patience": 3}

    assert parse(guardrails={"rules": [rule]}).guardrails.rules[0].action == "halt"
    with pytest.raises(ValidationError, match="exactly one of 'above' and 'below'"):
        parse(guardrails={"rules": [{"metric": "residual_l2"}]})
    with pytest.raises(ValidationError, match="exactly one of 'above' and 'below'"):
        parse(guardrails={"rules": [{**rule, "below": 0.0}]})
    with pytest.raises(ValidationError, match="not a declared metric"):
        parse(guardrails={"rules": [{**rule, "metric": "energy"}]})


def test_the_digest_identifies_the_contract_not_its_formatting() -> None:
    document = factories.protocol()
    reordered = dict(reversed(list(document.items())))
    changed = factories.protocol(limits={"wall_seconds": 61})

    assert protocol_digest(parse()) == protocol_digest(ExperimentProtocol.model_validate(reordered))
    assert protocol_digest(parse()) != protocol_digest(ExperimentProtocol.model_validate(changed))
    assert len(protocol_digest(parse())) == 64


def test_spelling_out_a_default_does_not_make_a_different_contract() -> None:
    # The digest covers what a contract states. Defaults belong to the schema version, so a
    # contract keeps its digest when the schema later gains an optional field.
    explicit = factories.protocol(
        limits={"wall_seconds": 60, "grace_seconds": 10.0, "max_output_mb": 256},
        guardrails={"non_finite": "record", "rules": []},
        observability={"parsers": [], "resource_interval_seconds": 1.0},
    )
    different = factories.protocol(limits={"wall_seconds": 60, "grace_seconds": 5.0})

    assert protocol_digest(ExperimentProtocol.model_validate(explicit)) == protocol_digest(parse())
    assert protocol_digest(ExperimentProtocol.model_validate(different)) != protocol_digest(parse())


def test_metric_names_and_supervisor_units_are_checked() -> None:
    with pytest.raises(ValidationError, match="also when case is ignored"):
        parse(
            metrics=[
                {"name": "Residual", "sampled_by": "instrumentation"},
                {"name": "residual", "sampled_by": "instrumentation"},
            ]
        )
    with pytest.raises(ValidationError, match="measures 'max_rss' in 'bytes'"):
        parse(metrics=[{"name": "max_rss", "unit": "MB", "sampled_by": "supervisor"}])
    assert parse(metrics=[{"name": "max_rss", "sampled_by": "supervisor"}]).metrics[0].unit == ""
    assert parse().limits.max_metrics_mb == 256


def test_a_run_gets_the_controls_and_one_declared_value_per_variable() -> None:
    protocol = parse()

    parameters = resolve_parameters(protocol, {"dt": 0.01})

    assert parameters == {"grid": 32, "steps": 100, "dt": 0.01}
    assert render_command(protocol, parameters, seed=None) == [
        "python3",
        "heat2d.py",
        "--dt",
        "0.01",
        "--grid",
        "32",
        "--steps",
        "100",
    ]


@pytest.mark.parametrize(
    ("provided", "kind"),
    [
        ({}, "missing"),
        ({"dt": 0.5}, "undeclared"),
        ({"dt": "0.01"}, "undeclared"),
        ({"dt": 0.01, "grid": 64}, "control"),
        ({"dt": 0.01, "tolerance": 1e-6}, "unknown"),
    ],
)
def test_a_run_cannot_drift_from_its_protocol(provided: dict[str, Any], kind: str) -> None:
    with pytest.raises(InvalidRequestError) as raised:
        resolve_parameters(parse(), provided)

    (issue,) = raised.value.details["errors"]
    assert issue["type"] == kind
    assert issue["loc"][:2] == ["body", "parameters"]


def test_numbers_match_numerically_and_keep_the_declared_form() -> None:
    protocol = parse(
        independent_variables={"order": [1.0, 2.0], "implicit": [True, False]},
        controls={},
        execution=execution(command=["solve", "{order}", "{implicit}"]),
    )

    parameters = resolve_parameters(protocol, {"order": 2, "implicit": False})

    assert parameters == {"order": 2.0, "implicit": False}
    assert render_command(protocol, parameters, seed=None) == ["solve", "2.0", "false"]
    with pytest.raises(InvalidRequestError):
        resolve_parameters(protocol, {"order": 1, "implicit": 1})  # 1 is not the boolean true


def test_the_seed_is_a_run_field_required_when_the_command_uses_it() -> None:
    protocol = parse(execution=execution(command=["sim", "--seed", "{seed}", "--dt", "{dt}"]))
    parameters = resolve_parameters(protocol, {"dt": 0.005})

    assert protocol.needs_seed
    assert render_command(protocol, parameters, seed=42) == ["sim", "--seed", "42", "--dt", "0.005"]
    with pytest.raises(InvalidRequestError, match=r"uses \{seed\}"):
        render_command(protocol, parameters, seed=None)


def test_values_render_predictably_on_the_command_line() -> None:
    assert [render_value(value) for value in (True, False, 3, 1e-05, 0.1, "cg")] == [
        "true",
        "false",
        "3",
        "1e-05",
        "0.1",
        "cg",
    ]
