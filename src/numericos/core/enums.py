"""Closed vocabularies of the domain. Workflow status is operational, never scientific validity."""

from __future__ import annotations

from enum import StrEnum


class CardType(StrEnum):
    TASK = "task"
    HYPOTHESIS = "hypothesis"
    EXPERIMENT = "experiment"
    ISSUE = "issue"
    DECISION = "decision"


class WorkflowStatus(StrEnum):
    BACKLOG = "backlog"
    PLANNED = "planned"
    ACTIVE = "active"
    REVIEW = "review"
    COMPLETED = "completed"
    BLOCKED = "blocked"


#: Column order on the board; also the order used when listing a whole board.
WORKFLOW_ORDER: tuple[WorkflowStatus, ...] = tuple(WorkflowStatus)


class EpistemicStatus(StrEnum):
    """What the evidence says about a hypothesis. Independent of any workflow status."""

    PROPOSED = "proposed"
    SUPPORTED = "supported"
    CONTRADICTED = "contradicted"
    INCONCLUSIVE = "inconclusive"


class RunStatus(StrEnum):
    """Operational state of one execution. ``succeeded`` means the process ended normally;
    it says nothing about the scientific validity of what it computed."""

    QUEUED = "queued"
    STARTING = "starting"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    CANCELLED = "cancelled"
    TIMED_OUT = "timed_out"
    LOST = "lost"


#: States in which a run may still change by itself.
ACTIVE_RUN_STATUSES: frozenset[RunStatus] = frozenset(
    {RunStatus.QUEUED, RunStatus.STARTING, RunStatus.RUNNING}
)


class FailureClass(StrEnum):
    """Why a run did not end normally. The classes call for different reactions."""

    CODE_ERROR = "code_error"
    RESOURCE_LIMIT = "resource_limit"
    NUMERICAL_INSTABILITY = "numerical_instability"
    INFRASTRUCTURE = "infrastructure"
    UNKNOWN = "unknown"


class EventType(StrEnum):
    PROJECT_CREATED = "PROJECT_CREATED"
    PROJECT_UPDATED = "PROJECT_UPDATED"
    PROJECT_EXECUTION_TRUSTED = "PROJECT_EXECUTION_TRUSTED"
    PROJECT_EXECUTION_TRUST_REVOKED = "PROJECT_EXECUTION_TRUST_REVOKED"
    CARD_CREATED = "CARD_CREATED"
    CARD_UPDATED = "CARD_UPDATED"
    CARD_MOVED = "CARD_MOVED"
    HYPOTHESIS_CREATED = "HYPOTHESIS_CREATED"
    HYPOTHESIS_UPDATED = "HYPOTHESIS_UPDATED"
    EXPERIMENT_CREATED = "EXPERIMENT_CREATED"
    EXPERIMENT_UPDATED = "EXPERIMENT_UPDATED"
    RUN_QUEUED = "RUN_QUEUED"


class Severity(StrEnum):
    DEBUG = "debug"
    INFO = "info"
    WARNING = "warning"
    ERROR = "error"
