"""Public API schemas. Pydantic models here are the single source of the OpenAPI contract."""

from __future__ import annotations

from datetime import datetime
from pathlib import PurePath
from typing import Annotated, Any, Literal, Self

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    StringConstraints,
    field_validator,
    model_validator,
)

from numericos.core.enums import (
    CardType,
    EpistemicStatus,
    FailureClass,
    RunStatus,
    WorkflowStatus,
)
from numericos.core.experiment import ExperimentProtocol, ParameterValue


class StrictModel(BaseModel):
    """Request bodies reject unknown fields, so a typo never becomes a silent no-op."""

    model_config = ConfigDict(extra="forbid")


def _absolute_or_none(value: str | None) -> str | None:
    if value is not None and not PurePath(value).is_absolute():
        raise ValueError("root_path must be an absolute path")
    return value


def _reject_explicit_nulls(model: BaseModel, fields: tuple[str, ...]) -> None:
    """In a PATCH an absent field means "keep"; null is only valid for nullable columns."""
    for name in fields:
        if name in model.model_fields_set and getattr(model, name) is None:
            raise ValueError(f"{name} cannot be null")


class ProjectCreate(StrictModel):
    name: str = Field(min_length=1, max_length=200)
    research_question: str = Field(default="", max_length=5000)
    description: str = Field(default="", max_length=20000)
    root_path: str | None = Field(
        default=None,
        description="Absolute path of the research code. Stored as a reference, never opened.",
    )
    is_demo: bool = Field(default=False, description="Marks demo data so the GUI can label it.")

    @field_validator("root_path")
    @classmethod
    def _root_path_absolute(cls, value: str | None) -> str | None:
        return _absolute_or_none(value)


class ProjectPatch(StrictModel):
    version: int = Field(ge=1, description="Current version of the project (optimistic locking).")
    name: str | None = Field(default=None, min_length=1, max_length=200)
    research_question: str | None = Field(default=None, max_length=5000)
    description: str | None = Field(default=None, max_length=20000)
    root_path: str | None = Field(
        default=None, description="Explicit null clears the path; an absent field keeps it."
    )

    @field_validator("root_path")
    @classmethod
    def _root_path_absolute(cls, value: str | None) -> str | None:
        return _absolute_or_none(value)

    @model_validator(mode="after")
    def _no_explicit_nulls(self) -> Self:
        _reject_explicit_nulls(self, ("name", "research_question", "description"))
        return self


class ProjectOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    name: str
    research_question: str
    description: str
    root_path: str | None
    is_demo: bool
    version: int
    created_at: datetime
    updated_at: datetime


class ProjectList(BaseModel):
    projects: list[ProjectOut]


class CardCreate(StrictModel):
    type: CardType
    title: str = Field(min_length=1, max_length=300)
    description: str = Field(default="", max_length=20000)
    workflow_status: WorkflowStatus = WorkflowStatus.BACKLOG
    entity_ref: str | None = Field(
        default=None, max_length=40, description="Typed ID of a later entity (hyp_..., exp_...)."
    )


class CardPatch(StrictModel):
    version: int = Field(ge=1, description="Current version of the card (optimistic locking).")
    project_id: str | None = Field(
        default=None, description="If given, the card must belong to this project."
    )
    type: CardType | None = None
    title: str | None = Field(default=None, min_length=1, max_length=300)
    description: str | None = Field(default=None, max_length=20000)
    entity_ref: str | None = Field(default=None, max_length=40)
    workflow_status: WorkflowStatus | None = None
    position: int | None = Field(
        default=None,
        ge=0,
        description="Zero-based index in the destination column; omitted means append.",
    )

    @model_validator(mode="after")
    def _no_explicit_nulls(self) -> Self:
        _reject_explicit_nulls(self, ("type", "title", "description", "workflow_status"))
        return self


class CardOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    project_id: str
    type: CardType
    title: str
    description: str
    workflow_status: WorkflowStatus
    sort_order: int
    entity_ref: str | None
    version: int
    created_at: datetime
    updated_at: datetime


class BoardOut(BaseModel):
    project_id: str
    workflow_statuses: list[WorkflowStatus]
    cards: list[CardOut]


Statement = Annotated[str, StringConstraints(min_length=1, max_length=2000)]


class HypothesisCreate(StrictModel):
    title: str = Field(min_length=1, max_length=300)
    claim: str = Field(
        min_length=1,
        max_length=5000,
        description="What is asserted, so that it can turn out wrong.",
    )
    rationale: str = Field(default="", max_length=5000, description="Why it might hold.")
    prediction: str = Field(default="", max_length=5000, description="What should be observed.")
    falsification: list[Statement] = Field(
        default_factory=list, max_length=50, description="Outcomes that would contradict the claim."
    )
    assumptions: list[Statement] = Field(default_factory=list, max_length=50)


class HypothesisPatch(StrictModel):
    version: int = Field(ge=1, description="Current version of the hypothesis.")
    title: str | None = Field(default=None, min_length=1, max_length=300)
    claim: str | None = Field(default=None, min_length=1, max_length=5000)
    rationale: str | None = Field(default=None, max_length=5000)
    prediction: str | None = Field(default=None, max_length=5000)
    falsification: list[Statement] | None = Field(default=None, max_length=50)
    assumptions: list[Statement] | None = Field(default=None, max_length=50)

    @model_validator(mode="after")
    def _no_explicit_nulls(self) -> Self:
        _reject_explicit_nulls(
            self, ("title", "claim", "rationale", "prediction", "falsification", "assumptions")
        )
        return self


class HypothesisOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    project_id: str
    title: str
    claim: str
    rationale: str
    prediction: str
    falsification: list[str]
    assumptions: list[str]
    epistemic_status: EpistemicStatus = Field(
        description="What the evidence says so far. It changes only through recorded decisions."
    )
    version: int
    created_at: datetime
    updated_at: datetime


class HypothesisList(BaseModel):
    hypotheses: list[HypothesisOut]


class ExperimentCreate(StrictModel):
    name: str = Field(min_length=1, max_length=300)
    hypothesis_id: str | None = Field(
        default=None, description="The hypothesis this experiment tests, if any (not a baseline)."
    )
    protocol: ExperimentProtocol


class ExperimentPatch(StrictModel):
    version: int = Field(ge=1, description="Current version of the experiment.")
    name: str | None = Field(default=None, min_length=1, max_length=300)
    hypothesis_id: str | None = Field(
        default=None, description="Explicit null unlinks the hypothesis; an absent field keeps it."
    )
    protocol: ExperimentProtocol | None = Field(
        default=None, description="Replaceable only while the experiment has no runs."
    )

    @model_validator(mode="after")
    def _no_explicit_nulls(self) -> Self:
        _reject_explicit_nulls(self, ("name", "protocol"))
        return self


class ExperimentOut(BaseModel):
    id: str
    project_id: str
    hypothesis_id: str | None
    name: str
    protocol: ExperimentProtocol
    protocol_digest: str = Field(description="SHA-256 of the canonical protocol; runs record it.")
    run_count: int
    version: int
    created_at: datetime
    updated_at: datetime


class ExperimentList(BaseModel):
    experiments: list[ExperimentOut]


class RunCreate(StrictModel):
    parameters: dict[str, ParameterValue] = Field(
        default_factory=dict,
        description="One declared value for every independent variable of the experiment.",
    )
    seed: int | None = Field(default=None, ge=0, le=2**63 - 1)
    label: str = Field(default="", max_length=200)


class RunOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    project_id: str
    experiment_id: str
    label: str
    status: RunStatus = Field(
        description="Operational state. 'succeeded' is a normal process end, not a valid result."
    )
    status_reason: str | None
    failure_class: FailureClass | None
    parameters: dict[str, ParameterValue] = Field(
        description="The complete assignment: controls and the chosen independent values."
    )
    seed: int | None
    argv: list[str] = Field(description="The exact argument vector of the program.")
    protocol_digest: str
    version: int
    created_at: datetime
    updated_at: datetime


class RunList(BaseModel):
    runs: list[RunOut]


class EventOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    event_id: str
    seq: int = Field(description="Monotonic ledger position; the replay cursor.")
    project_id: str
    run_id: str | None = Field(default=None, description="The run this event belongs to, if any.")
    type: str
    subject_id: str
    actor: str
    producer: str
    severity: str
    correlation_id: str
    schema_version: int
    timestamp_utc: datetime
    payload: dict[str, Any]


class EventPage(BaseModel):
    events: list[EventOut]
    next_cursor: int | None
    has_more: bool


class HealthOut(BaseModel):
    status: Literal["ok", "degraded"]
    app: Literal["numericos"]
    version: str
    time_utc: datetime
    data_dir: str
    db: Literal["ok", "unavailable"]
    schema_revision: str | None
    expected_revision: str


class ErrorBody(BaseModel):
    code: str = Field(description="Stable machine-readable error code, e.g. NOT_FOUND.")
    message: str
    details: dict[str, Any] = Field(default_factory=dict)
    correlation_id: str | None = None


class ErrorEnvelope(BaseModel):
    """The one JSON shape of every non-2xx response."""

    error: ErrorBody
