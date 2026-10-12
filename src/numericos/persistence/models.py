"""ORM mappings. Tables are created only by Alembic migrations, never by ``metadata.create_all``."""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Any

from sqlalchemy import (
    JSON,
    Boolean,
    CheckConstraint,
    Float,
    ForeignKey,
    Index,
    Integer,
    MetaData,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

from numericos.core.enums import (
    AgentProvider,
    CardType,
    EpistemicStatus,
    FailureClass,
    MessageRole,
    MessageStatus,
    PermissionMode,
    RunStatus,
    Severity,
    WorkflowStatus,
)
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
    #: Set by an explicit action: commands may be executed in ``root_path`` from then on.
    execution_trusted_at: Mapped[datetime | None] = mapped_column(UTCDateTime)
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


class Hypothesis(Base):
    """A falsifiable claim. Its epistemic status is separate from any workflow status."""

    __tablename__ = "hypotheses"
    __table_args__ = (
        CheckConstraint(one_of("epistemic_status", EpistemicStatus), name="epistemic_status"),
        CheckConstraint("length(title) BETWEEN 1 AND 300", name="title_length"),
        Index("ix_hypotheses_project_created", "project_id", "created_at"),
    )

    id: Mapped[str] = mapped_column(String(40), primary_key=True)
    project_id: Mapped[str] = mapped_column(
        String(40), ForeignKey("projects.id", ondelete="RESTRICT")
    )
    title: Mapped[str] = mapped_column(String(300))
    claim: Mapped[str] = mapped_column(Text)
    rationale: Mapped[str] = mapped_column(Text, default="")
    prediction: Mapped[str] = mapped_column(Text, default="")
    falsification: Mapped[list[str]] = mapped_column(JSON, default=list)
    assumptions: Mapped[list[str]] = mapped_column(JSON, default=list)
    epistemic_status: Mapped[str] = mapped_column(
        String(20), default=EpistemicStatus.PROPOSED.value
    )
    version: Mapped[int] = mapped_column(Integer, default=1)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime)
    updated_at: Mapped[datetime] = mapped_column(UTCDateTime)


class Experiment(Base):
    """A protocol that tests a hypothesis (or characterises a baseline) through runs."""

    __tablename__ = "experiments"
    __table_args__ = (
        CheckConstraint("length(name) BETWEEN 1 AND 300", name="name_length"),
        Index("ix_experiments_project_created", "project_id", "created_at"),
    )

    id: Mapped[str] = mapped_column(String(40), primary_key=True)
    project_id: Mapped[str] = mapped_column(
        String(40), ForeignKey("projects.id", ondelete="RESTRICT")
    )
    hypothesis_id: Mapped[str | None] = mapped_column(
        String(40), ForeignKey("hypotheses.id", ondelete="RESTRICT"), index=True
    )
    name: Mapped[str] = mapped_column(String(300))
    protocol: Mapped[dict[str, Any]] = mapped_column(JSON)
    protocol_digest: Mapped[str] = mapped_column(String(64))
    version: Mapped[int] = mapped_column(Integer, default=1)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime)
    updated_at: Mapped[datetime] = mapped_column(UTCDateTime)


class Run(Base):
    """One concrete execution of an experiment: a code revision, parameters and their outcome."""

    __tablename__ = "runs"
    __table_args__ = (
        CheckConstraint(one_of("status", RunStatus), name="status"),
        CheckConstraint(
            f"failure_class IS NULL OR {one_of('failure_class', FailureClass)}",
            name="failure_class",
        ),
        UniqueConstraint(
            "experiment_id", "idempotency_key", name="uq_runs_experiment_idempotency_key"
        ),
        Index("ix_runs_experiment_created", "experiment_id", "created_at"),
        Index("ix_runs_status", "status"),
    )

    id: Mapped[str] = mapped_column(String(40), primary_key=True)
    project_id: Mapped[str] = mapped_column(
        String(40), ForeignKey("projects.id", ondelete="RESTRICT")
    )
    experiment_id: Mapped[str] = mapped_column(
        String(40), ForeignKey("experiments.id", ondelete="RESTRICT")
    )
    label: Mapped[str] = mapped_column(String(200), default="")
    status: Mapped[str] = mapped_column(String(20))
    status_reason: Mapped[str | None] = mapped_column(String(300))
    failure_class: Mapped[str | None] = mapped_column(String(30))
    parameters: Mapped[dict[str, Any]] = mapped_column(JSON)
    seed: Mapped[int | None] = mapped_column(Integer)
    argv: Mapped[list[str]] = mapped_column(JSON)
    protocol_digest: Mapped[str] = mapped_column(String(64))
    idempotency_key: Mapped[str | None] = mapped_column(String(128))
    request_digest: Mapped[str | None] = mapped_column(String(64))
    #: Provenance. ``code`` is fixed at creation; inputs and environment when the run starts.
    code: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    code_sha: Mapped[str | None] = mapped_column(String(40), index=True)
    inputs: Mapped[list[dict[str, Any]] | None] = mapped_column(JSON)
    environment: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    reproduces_run_id: Mapped[str | None] = mapped_column(String(40))
    #: Correlation ID of the request that queued the run; the supervisor's events reuse it.
    correlation_id: Mapped[str | None] = mapped_column(String(64))
    #: Supervision. A process is identified by PID *and* start time, never by PID alone.
    worker_id: Mapped[str | None] = mapped_column(String(40), index=True)
    monitor_pid: Mapped[int | None] = mapped_column(Integer)
    monitor_started_at: Mapped[float | None] = mapped_column(Float)
    pid: Mapped[int | None] = mapped_column(Integer)
    process_started_at: Mapped[float | None] = mapped_column(Float)
    started_at: Mapped[datetime | None] = mapped_column(UTCDateTime)
    finished_at: Mapped[datetime | None] = mapped_column(UTCDateTime)
    heartbeat_at: Mapped[datetime | None] = mapped_column(UTCDateTime)
    cancel_requested_at: Mapped[datetime | None] = mapped_column(UTCDateTime)
    cancel_reason: Mapped[str | None] = mapped_column(String(300))
    exit_code: Mapped[int | None] = mapped_column(Integer)
    exit_signal: Mapped[str | None] = mapped_column(String(20))
    wall_seconds: Mapped[float | None] = mapped_column(Float)
    #: What the monitor wrote when the program ended (``exit.json``).
    outcome: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    #: Summary of the resource samples seen so far.
    resources: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    #: How far the supervisor has read the monitor's files.
    ingest: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    #: What the monitor learned from the output besides the series: counts and diagnostics.
    metric_report: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    version: Mapped[int] = mapped_column(Integer, default=1)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime)
    updated_at: Mapped[datetime] = mapped_column(UTCDateTime)


class Worker(Base):
    """A supervisor process. It is alive while it keeps its heartbeat and has not stopped."""

    __tablename__ = "workers"

    id: Mapped[str] = mapped_column(String(40), primary_key=True)
    pid: Mapped[int] = mapped_column(Integer)
    hostname: Mapped[str] = mapped_column(String(255))
    version: Mapped[str] = mapped_column(String(40))
    max_parallel_runs: Mapped[int] = mapped_column(Integer)
    started_at: Mapped[datetime] = mapped_column(UTCDateTime)
    heartbeat_at: Mapped[datetime] = mapped_column(UTCDateTime)
    stopped_at: Mapped[datetime | None] = mapped_column(UTCDateTime)


class Artifact(Base):
    """A file of a run, kept in the run directory, with its size and checksum."""

    __tablename__ = "artifacts"
    __table_args__ = (UniqueConstraint("run_id", "name", name="uq_artifacts_run_name"),)

    id: Mapped[str] = mapped_column(String(40), primary_key=True)
    project_id: Mapped[str] = mapped_column(String(40), ForeignKey("projects.id"))
    run_id: Mapped[str] = mapped_column(String(40), ForeignKey("runs.id"))
    kind: Mapped[str] = mapped_column(String(40))
    name: Mapped[str] = mapped_column(String(1000))
    media_type: Mapped[str] = mapped_column(String(100))
    size_bytes: Mapped[int] = mapped_column(Integer)
    sha256: Mapped[str | None] = mapped_column(String(64))
    created_at: Mapped[datetime] = mapped_column(UTCDateTime)


class MetricSeries(Base):
    """What is known about one metric of one run without reading its samples, which stay in
    the run directory. One row per run and metric, so runs can be compared by a query."""

    __tablename__ = "metric_series"
    __table_args__ = (
        CheckConstraint("source IN ('instrumentation', 'parser', 'supervisor')", name="source"),
        UniqueConstraint("run_id", "name", name="uq_metric_series_run_name"),
        Index("ix_metric_series_experiment_name", "experiment_id", "name"),
    )

    id: Mapped[str] = mapped_column(String(40), primary_key=True)
    project_id: Mapped[str] = mapped_column(String(40), ForeignKey("projects.id"))
    experiment_id: Mapped[str] = mapped_column(String(40), ForeignKey("experiments.id"))
    run_id: Mapped[str] = mapped_column(String(40), ForeignKey("runs.id"))
    name: Mapped[str] = mapped_column(String(100))
    unit: Mapped[str] = mapped_column(String(60))
    source: Mapped[str] = mapped_column(String(20))
    declared: Mapped[bool] = mapped_column(Boolean)
    samples: Mapped[int] = mapped_column(Integer)
    non_finite: Mapped[int] = mapped_column(Integer)
    stored: Mapped[int] = mapped_column(Integer)
    first_value: Mapped[float | None] = mapped_column(Float)
    first_step: Mapped[int | None] = mapped_column(Integer)
    last_value: Mapped[float | None] = mapped_column(Float)
    last_non_finite: Mapped[str | None] = mapped_column(String(4))
    last_step: Mapped[int | None] = mapped_column(Integer)
    last_time: Mapped[float | None] = mapped_column(Float)
    last_at: Mapped[float | None] = mapped_column(Float)
    min_value: Mapped[float | None] = mapped_column(Float)
    max_value: Mapped[float | None] = mapped_column(Float)
    updated_at: Mapped[datetime] = mapped_column(UTCDateTime)


class AgentSession(Base):
    """A conversation with a coding agent about one project, in one provider session."""

    __tablename__ = "agent_sessions"
    __table_args__ = (
        CheckConstraint(one_of("provider", AgentProvider), name="provider"),
        CheckConstraint(one_of("permission_mode", PermissionMode), name="permission_mode"),
        CheckConstraint("length(title) BETWEEN 1 AND 200", name="title_length"),
        Index("ix_agent_sessions_project_created", "project_id", "created_at"),
    )

    id: Mapped[str] = mapped_column(String(40), primary_key=True)
    project_id: Mapped[str] = mapped_column(
        String(40), ForeignKey("projects.id", ondelete="RESTRICT")
    )
    title: Mapped[str] = mapped_column(String(200))
    provider: Mapped[str] = mapped_column(String(20))
    permission_mode: Mapped[str] = mapped_column(String(20))
    #: The model asked for; null leaves the choice to the provider.
    model: Mapped[str | None] = mapped_column(String(100))
    #: The provider's own session identifier, chosen by NumericOS before the first turn.
    native_session_id: Mapped[str] = mapped_column(String(64))
    #: The directory the agent works in: the project's trusted root when the session started.
    cwd: Mapped[str] = mapped_column(Text)
    system_prompt: Mapped[str] = mapped_column(Text)
    version: Mapped[int] = mapped_column(Integer, default=1)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime)
    updated_at: Mapped[datetime] = mapped_column(UTCDateTime)


class AgentMessage(Base):
    """A message of a session. A user message is the prompt; an assistant message is one turn
    of the agent, queued by the API and executed by a supervisor, with what was observed."""

    __tablename__ = "messages"
    __table_args__ = (
        CheckConstraint(one_of("role", MessageRole), name="role"),
        CheckConstraint(one_of("status", MessageStatus), name="status"),
        Index("ix_messages_session_created", "session_id", "created_at"),
        Index("ix_messages_status", "status"),
    )

    id: Mapped[str] = mapped_column(String(40), primary_key=True)
    session_id: Mapped[str] = mapped_column(
        String(40), ForeignKey("agent_sessions.id", ondelete="RESTRICT")
    )
    project_id: Mapped[str] = mapped_column(
        String(40), ForeignKey("projects.id", ondelete="RESTRICT")
    )
    role: Mapped[str] = mapped_column(String(10))
    status: Mapped[str] = mapped_column(String(20))
    status_reason: Mapped[str | None] = mapped_column(String(300))
    #: The prompt (user) or the final answer (assistant), Markdown. Immutable once final.
    markdown: Mapped[str] = mapped_column(Text, default="")
    #: Assistant: the user message this turn answers.
    prompt_message_id: Mapped[str | None] = mapped_column(String(40))
    #: Correlation ID of the request that queued the turn; the supervisor's events reuse it.
    correlation_id: Mapped[str | None] = mapped_column(String(64))
    #: What was observed while the agent worked.
    model: Mapped[str | None] = mapped_column(String(100))
    activity: Mapped[list[dict[str, Any]]] = mapped_column(JSON, default=list)
    activity_dropped: Mapped[int] = mapped_column(Integer, default=0)
    files_read: Mapped[list[str]] = mapped_column(JSON, default=list)
    files_written: Mapped[list[str]] = mapped_column(JSON, default=list)
    permission_denials: Mapped[list[dict[str, Any]]] = mapped_column(JSON, default=list)
    cost_usd: Mapped[float | None] = mapped_column(Float)
    usage: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    num_turns: Mapped[int | None] = mapped_column(Integer)
    structured_output: Mapped[dict[str, Any] | list[Any] | None] = mapped_column(JSON)
    #: Supervision. A process is identified by PID *and* start time, never by PID alone.
    worker_id: Mapped[str | None] = mapped_column(String(40), index=True)
    pid: Mapped[int | None] = mapped_column(Integer)
    process_started_at: Mapped[float | None] = mapped_column(Float)
    started_at: Mapped[datetime | None] = mapped_column(UTCDateTime)
    finished_at: Mapped[datetime | None] = mapped_column(UTCDateTime)
    heartbeat_at: Mapped[datetime | None] = mapped_column(UTCDateTime)
    cancel_requested_at: Mapped[datetime | None] = mapped_column(UTCDateTime)
    cancel_reason: Mapped[str | None] = mapped_column(String(300))
    exit_code: Mapped[int | None] = mapped_column(Integer)
    #: How far the supervisor has read the turn's files.
    ingest: Mapped[dict[str, Any] | None] = mapped_column(JSON)
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
    #: Correlation with a run. Like ``subject_id`` it is a reference without a foreign key.
    run_id: Mapped[str | None] = mapped_column(String(40), index=True)
    type: Mapped[str] = mapped_column("event_type", String(60))
    subject_id: Mapped[str] = mapped_column(String(40), index=True)
    actor: Mapped[str] = mapped_column(String(120))
    producer: Mapped[str] = mapped_column(String(60), default="api")
    severity: Mapped[str] = mapped_column(String(10), default=Severity.INFO.value)
    correlation_id: Mapped[str] = mapped_column(String(64), index=True)
    schema_version: Mapped[int] = mapped_column(Integer, default=1)
    payload: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    timestamp_utc: Mapped[datetime] = mapped_column(UTCDateTime)
