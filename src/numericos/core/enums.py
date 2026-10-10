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


class EventType(StrEnum):
    PROJECT_CREATED = "PROJECT_CREATED"
    PROJECT_UPDATED = "PROJECT_UPDATED"
    CARD_CREATED = "CARD_CREATED"
    CARD_UPDATED = "CARD_UPDATED"
    CARD_MOVED = "CARD_MOVED"


class Severity(StrEnum):
    DEBUG = "debug"
    INFO = "info"
    WARNING = "warning"
    ERROR = "error"
