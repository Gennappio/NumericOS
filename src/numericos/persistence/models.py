"""ORM mappings. Tables are created only by Alembic migrations, never by ``metadata.create_all``."""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Any

from sqlalchemy import (
    JSON,
    Boolean,
    CheckConstraint,
    ForeignKey,
    Index,
    Integer,
    MetaData,
    String,
    Text,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

from numericos.core.enums import CardType, Severity, WorkflowStatus
from numericos.persistence.engine import UTCDateTime

#: Named constraints are mandatory for Alembic batch mode on SQLite.
NAMING_CONVENTION = {
    "ix": "ix_%(column_0_label)s",
    "uq": "uq_%(table_name)s_%(column_0_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}


def one_of(column: str, values: type[StrEnum]) -> str:
    """SQL ``IN`` check built from an enum, so the DB and the domain share one vocabulary."""
    return f"{column} IN ({', '.join(repr(member.value) for member in values)})"


class Base(DeclarativeBase):
    metadata = MetaData(naming_convention=NAMING_CONVENTION)


class Project(Base):
    __tablename__ = "projects"
    __table_args__ = (CheckConstraint("length(name) BETWEEN 1 AND 200", name="name_length"),)

    id: Mapped[str] = mapped_column(String(40), primary_key=True)
    name: Mapped[str] = mapped_column(String(200))
    research_question: Mapped[str] = mapped_column(Text, default="")
    description: Mapped[str] = mapped_column(Text, default="")
    root_path: Mapped[str | None] = mapped_column(Text)
    is_demo: Mapped[bool] = mapped_column(
        Boolean(create_constraint=True, name="is_demo_bool"), default=False
    )
    version: Mapped[int] = mapped_column(Integer, default=1)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, index=True)
    updated_at: Mapped[datetime] = mapped_column(UTCDateTime)


class BoardCard(Base):
    """A typed card on the scientific board. Its status is workflow, never epistemic validity."""

    __tablename__ = "board_cards"
    __table_args__ = (
        CheckConstraint(one_of("card_type", CardType), name="card_type"),
        CheckConstraint(one_of("workflow_status", WorkflowStatus), name="workflow_status"),
        CheckConstraint("length(title) BETWEEN 1 AND 300", name="title_length"),
        Index("ix_board_cards_project_status_order", "project_id", "workflow_status", "sort_order"),
    )

    id: Mapped[str] = mapped_column(String(40), primary_key=True)
    project_id: Mapped[str] = mapped_column(
        String(40), ForeignKey("projects.id", ondelete="RESTRICT")
    )
    type: Mapped[str] = mapped_column("card_type", String(20))
    title: Mapped[str] = mapped_column(String(300))
    description: Mapped[str] = mapped_column(Text, default="")
    workflow_status: Mapped[str] = mapped_column(String(20))
    sort_order: Mapped[int] = mapped_column(Integer)
    entity_ref: Mapped[str | None] = mapped_column(String(40))
    version: Mapped[int] = mapped_column(Integer, default=1)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime)
    updated_at: Mapped[datetime] = mapped_column(UTCDateTime)


class Event(Base):
    """Append-only ledger row. ``seq`` is the only ordering authority; the timestamp is metadata."""

    __tablename__ = "events"
    __table_args__ = (
        CheckConstraint(one_of("severity", Severity), name="severity"),
        Index("ix_events_project_seq", "project_id", "seq"),
        {"sqlite_autoincrement": True},
    )

    seq: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    event_id: Mapped[str] = mapped_column(String(40), unique=True)
    project_id: Mapped[str] = mapped_column(String(40), ForeignKey("projects.id"))
    type: Mapped[str] = mapped_column("event_type", String(60))
    subject_id: Mapped[str] = mapped_column(String(40), index=True)
    actor: Mapped[str] = mapped_column(String(120))
    producer: Mapped[str] = mapped_column(String(60), default="api")
    severity: Mapped[str] = mapped_column(String(10), default=Severity.INFO.value)
    correlation_id: Mapped[str] = mapped_column(String(64), index=True)
    schema_version: Mapped[int] = mapped_column(Integer, default=1)
    payload: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    timestamp_utc: Mapped[datetime] = mapped_column(UTCDateTime)
