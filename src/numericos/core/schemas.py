"""Public API schemas. Pydantic models here are the single source of the OpenAPI contract."""

from __future__ import annotations

from datetime import datetime
from pathlib import PurePath
from typing import Any, Literal, Self

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from numericos.core.enums import CardType, WorkflowStatus


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


class EventOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    event_id: str
    seq: int = Field(description="Monotonic ledger position; the replay cursor.")
    project_id: str
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
