"""The experiment contract ``numericos.experiment.v1``.

It states what an experiment tests and observes, and how one run of it is executed. The contract
is stored with its experiment, frozen as soon as the first run exists, and identified by a digest
that every run records.
"""

from __future__ import annotations

import hashlib
import json
import re
from pathlib import PurePosixPath
from string import Formatter
from typing import Annotated, Any, Literal, Self

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    StringConstraints,
    field_validator,
    model_validator,
)

from numericos.core.errors import InvalidRequestError

PARAMETER_NAME = r"^[A-Za-z_][A-Za-z0-9_]{0,63}$"
METRIC_NAME = r"^[A-Za-z][A-Za-z0-9_.-]{0,99}$"

#: ``{seed}`` in a command is filled from the run's seed, not from a variable or control.
SEED = "seed"

#: Quantities the supervisor measures itself, with their units.
SUPERVISOR_METRICS: dict[str, str] = {"wall_time": "s", "cpu_time": "s", "max_rss": "bytes"}

# bool before int: a JSON ``true`` must stay a boolean.
ParameterValue = bool | int | float | str
MetricName = Annotated[str, StringConstraints(pattern=METRIC_NAME)]
Text = Annotated[str, StringConstraints(max_length=5000)]
Argument = Annotated[str, StringConstraints(min_length=1, max_length=4000)]
Command = Annotated[list[Argument], Field(min_length=1, max_length=200)]


class Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")


def relative_path(value: str) -> str:
    """A path inside its base directory: relative, POSIX separators, without ``..``."""
    path = PurePosixPath(value)
    if not value or "\\" in value or path.is_absolute() or ".." in path.parts:
        raise ValueError("must be a relative path without '..'")
    return str(path)


def placeholders(argument: str) -> list[str]:
    """Names of the ``{name}`` placeholders of one command argument."""
    names = []
    for _literal, field, spec, conversion in Formatter().parse(argument):
        if field is None:
            continue
        if spec or conversion or not re.fullmatch(PARAMETER_NAME, field):
            raise ValueError(f"unsupported placeholder in {argument!r}: only {{name}} is allowed")
        names.append(field)
    return names


class MetricSpec(Strict):
    """A quantity the experiment measures, with its unit and who measures it."""

    name: MetricName
    unit: str = Field(default="", max_length=60)
    sampled_by: Literal["instrumentation", "parser", "supervisor"] = Field(
        description=(
            "instrumentation: the program emits numericos.metric.v1 records; "
            "parser: extracted from its output by a parser of this contract; "
            "supervisor: measured by the supervisor (wall_time, cpu_time, max_rss)."
        )
    )
    description: str = Field(default="", max_length=1000)


class ParserSpec(Strict):
    """Extracts metrics from the program's output lines (observability level L1).

    ``pattern`` is a Python regular expression. Every named group except ``step`` is a metric
    of that name; the optional group ``step`` is the sample's step.
    """

    name: Annotated[str, StringConstraints(pattern=PARAMETER_NAME)]
    pattern: str = Field(min_length=1, max_length=2000)
    stream: Literal["stdout", "stderr", "any"] = "stdout"

    @field_validator("pattern")
    @classmethod
    def _compiles_and_names_metrics(cls, value: str) -> str:
        try:
            compiled = re.compile(value)
        except re.error as error:
            raise ValueError(f"not a valid regular expression: {error}") from error
        if not set(compiled.groupindex) - {"step"}:
            raise ValueError("needs at least one named group besides 'step'")
        return value

    @property
    def metric_names(self) -> list[str]:
        return [name for name in re.compile(self.pattern).groupindex if name != "step"]


class GuardrailRule(Strict):
    """An explicit numeric limit on a metric. No threshold is ever assumed by NumericOS."""

    metric: MetricName
    above: float | None = None
    below: float | None = None
    patience: int = Field(default=1, ge=1, le=100000, description="Consecutive violating samples.")
    action: Literal["halt", "record"] = "halt"

    @model_validator(mode="after")
    def _one_bound(self) -> Self:
        if (self.above is None) == (self.below is None):
            raise ValueError("give exactly one of 'above' and 'below'")
        return self


class Guardrails(Strict):
    non_finite: Literal["halt", "record"] = Field(
        default="record",
        description="What to do when a metric is NaN or infinite. It is always recorded.",
    )
    rules: list[GuardrailRule] = Field(default_factory=list, max_length=50)


class Limits(Strict):
    """Resource envelope of one run, enforced by the supervisor."""

    wall_seconds: float = Field(gt=0, le=7 * 24 * 3600)
    max_rss_mb: int | None = Field(default=None, gt=0, le=4 * 1024 * 1024)
    grace_seconds: float = Field(
        default=10.0, ge=0, le=300, description="Between SIGTERM and SIGKILL when a run is stopped."
    )
    max_output_mb: int = Field(default=256, gt=0, le=65536)


class CodeSpec(Strict):
    """Which code a run executes.

    ``ref``: an exact commit, resolved when the run is created and executed from an export of
    that commit, never from the working tree. ``working_tree``: the project directory as it is
    when the run starts, uncommitted changes included; an explicit choice because it is only
    reproducible through the recorded diff.
    """

    mode: Literal["ref", "working_tree"] = "ref"
    ref: str = Field(default="HEAD", min_length=1, max_length=200, pattern=r"^[^-\s][^\s]*$")


class InputSpec(Strict):
    """A file the run reads; its checksum is recorded and, if given, enforced."""

    path: str = Field(max_length=1000)
    base: Literal["code", "project"] = Field(
        default="code",
        description="code: inside the executed code; project: under the project root.",
    )
    sha256: str | None = Field(default=None, pattern=r"^[0-9a-f]{64}$")

    _path = field_validator("path")(relative_path)


class ExecutionSpec(Strict):
    command: Command = Field(
        description="Argument vector, never a shell line. {name} is replaced by a parameter."
    )
    workdir: str = Field(default=".", max_length=1000, description="Inside the code root.")
    code: CodeSpec = Field(default_factory=CodeSpec)
    env: dict[str, str] = Field(default_factory=dict, description="Environment set for the run.")
    inherit_env: list[str] = Field(
        default_factory=list,
        max_length=100,
        description="Names passed through from the supervisor's environment.",
    )
    inputs: list[InputSpec] = Field(default_factory=list, max_length=200)
    environment_probes: list[Command] = Field(
        default_factory=list,
        max_length=20,
        description="Commands whose output is recorded as environment provenance.",
    )
    build: list[Command] = Field(
        default_factory=list,
        max_length=20,
        description="Commands run in the code directory before the program starts.",
    )

    _workdir = field_validator("workdir")(relative_path)

    @field_validator("env")
    @classmethod
    def _env_names(cls, value: dict[str, str]) -> dict[str, str]:
        for name in value:
            if not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", name):
                raise ValueError(f"{name!r} is not a valid environment variable name")
        return value


class ObservabilitySpec(Strict):
    parsers: list[ParserSpec] = Field(default_factory=list, max_length=20)
    resource_interval_seconds: float = Field(default=1.0, ge=0.2, le=60)


class ExperimentProtocol(Strict):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    schema_: Literal["numericos.experiment.v1"] = Field(alias="schema")
    question: Text = Field(min_length=1)
    prediction: Text = ""
    falsification: list[Text] = Field(default_factory=list, max_length=50)
    independent_variables: dict[str, list[ParameterValue]] = Field(
        default_factory=dict,
        description="What varies between runs, with the values the experiment will use.",
    )
    controls: dict[str, ParameterValue] = Field(
        default_factory=dict, description="Parameters that are identical in every run."
    )
    execution: ExecutionSpec
    metrics: list[MetricSpec] = Field(default_factory=list, max_length=100)
    observability: ObservabilitySpec = Field(default_factory=ObservabilitySpec)
    guardrails: Guardrails = Field(default_factory=Guardrails)
    limits: Limits

    @model_validator(mode="after")
    def _consistent(self) -> Self:
        names = [*self.independent_variables, *self.controls]
        for name in names:
            if not re.fullmatch(PARAMETER_NAME, name):
                raise ValueError(f"{name!r} is not a valid parameter name")
            if name == SEED:
                raise ValueError("'seed' is set per run, not as a variable or control")
        if len(set(names)) != len(names):
            raise ValueError("a parameter cannot be both an independent variable and a control")
        for name, values in self.independent_variables.items():
            if not values:
                raise ValueError(f"independent variable {name!r} needs at least one value")
            if any(same_value(a, b) for i, a in enumerate(values) for b in values[i + 1 :]):
                raise ValueError(f"independent variable {name!r} repeats a value")

        known = {*names, SEED}
        for command in (self.execution.command, *self.execution.build):
            for argument in command:
                unknown = set(placeholders(argument)) - known
                if unknown:
                    raise ValueError(
                        f"{argument!r} uses {sorted(unknown)}, which is neither an independent "
                        "variable nor a control"
                    )

        metric_names = [metric.name for metric in self.metrics]
        if len(set(metric_names)) != len(metric_names):
            raise ValueError("metric names must be unique")
        parser_names = [parser.name for parser in self.observability.parsers]
        if len(set(parser_names)) != len(parser_names):
            raise ValueError("parser names must be unique")
        parsed = {name for parser in self.observability.parsers for name in parser.metric_names}
        by_name = {metric.name: metric for metric in self.metrics}
        for name in sorted(parsed):
            if name not in by_name or by_name[name].sampled_by != "parser":
                raise ValueError(f"a parser extracts {name!r}: declare it with sampled_by: parser")
        for metric in self.metrics:
            if metric.sampled_by == "parser" and metric.name not in parsed:
                raise ValueError(f"no parser extracts the metric {metric.name!r}")
            if metric.sampled_by == "supervisor" and metric.name not in SUPERVISOR_METRICS:
                raise ValueError(
                    f"the supervisor does not measure {metric.name!r}; it measures "
                    f"{sorted(SUPERVISOR_METRICS)}"
                )
        for rule in self.guardrails.rules:
            if rule.metric not in by_name:
                raise ValueError(f"guardrail on {rule.metric!r}, which is not a declared metric")
        return self

    @property
    def needs_seed(self) -> bool:
        return any(SEED in placeholders(argument) for argument in self.execution.command)

    def to_json(self) -> dict[str, Any]:
        """The stored and transmitted form (aliases applied)."""
        return self.model_dump(mode="json", by_alias=True)


def same_value(left: ParameterValue, right: ParameterValue) -> bool:
    """Equality of parameter values: numbers compare numerically, other types exactly."""
    if isinstance(left, bool | str) or isinstance(right, bool | str):
        return type(left) is type(right) and left == right
    return left == right


def protocol_digest(protocol: ExperimentProtocol) -> str:
    """SHA-256 of the canonical JSON form; identifies the contract a run was executed under."""
    canonical = json.dumps(
        protocol.to_json(), sort_keys=True, separators=(",", ":"), ensure_ascii=False
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _issue(field: str, message: str, kind: str) -> dict[str, Any]:
    return {"loc": ["body", "parameters", field], "msg": message, "type": kind}


def resolve_parameters(
    protocol: ExperimentProtocol, provided: dict[str, ParameterValue]
) -> dict[str, ParameterValue]:
    """The complete parameter assignment of one run: the controls plus one declared value for
    every independent variable. Anything else is rejected, so a run cannot drift from its
    protocol by a typo or an undeclared value."""
    issues = []
    for name in provided:
        if name in protocol.controls:
            issues.append(_issue(name, "is a control, fixed by the protocol", "control"))
        elif name not in protocol.independent_variables:
            issues.append(_issue(name, "is not a variable of this experiment", "unknown"))
    chosen: dict[str, ParameterValue] = {}
    for name, declared in protocol.independent_variables.items():
        if name not in provided:
            issues.append(_issue(name, f"required: one of {declared}", "missing"))
            continue
        match = next((value for value in declared if same_value(value, provided[name])), None)
        if match is None:
            issues.append(
                _issue(
                    name,
                    f"{provided[name]!r} is not among the declared values {declared}",
                    "undeclared",
                )
            )
        else:
            chosen[name] = match
    if issues:
        raise InvalidRequestError(
            "the parameters do not fit the experiment's protocol", details={"errors": issues}
        )
    return {**protocol.controls, **chosen}


def render_value(value: ParameterValue) -> str:
    """How a parameter appears on the command line: true/false, integers, shortest float repr."""
    if isinstance(value, bool):
        return "true" if value else "false"
    return value if isinstance(value, str) else repr(value)


def render_command(
    protocol: ExperimentProtocol, parameters: dict[str, ParameterValue], seed: int | None
) -> list[str]:
    values = {name: render_value(value) for name, value in parameters.items()}
    if protocol.needs_seed:
        if seed is None:
            raise InvalidRequestError(
                "the command of this experiment uses {seed}",
                details={
                    "errors": [
                        {
                            "loc": ["body", "seed"],
                            "msg": "required by the command",
                            "type": "missing",
                        }
                    ]
                },
            )
        values[SEED] = str(seed)
    return [argument.format_map(values) for argument in protocol.execution.command]
