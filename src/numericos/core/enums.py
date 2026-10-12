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
    DATA_PROBLEM = "data_problem"
    INFRASTRUCTURE = "infrastructure"
    UNKNOWN = "unknown"


class AgentProvider(StrEnum):
    CLAUDE_CODE = "claude_code"


class PermissionMode(StrEnum):
    """What the agent may do in the project directory during a turn. The provider enforces it;
    what it refused is recorded on the answer."""

    READ_ONLY = "read_only"
    EDIT = "edit"
    FULL = "full"


class AgentTask(StrEnum):
    """What a session of the agent is for. The project's policy names a model and an effort
    for each task; a session may override them."""

    CONVERSATION = "conversation"
    CLARIFY = "clarify"
    RESOLVE = "resolve"
    THEORY = "theory"
    FILE_DESCRIPTION = "file_description"
    EXECUTION_DESCRIPTION = "execution_description"
    PLAN = "plan"


#: Tasks that a built feature uses today. The policy keeps a choice for the others ahead of
#: their ticket; the GUI says they are not available yet.
AVAILABLE_TASKS: frozenset[AgentTask] = frozenset({AgentTask.CONVERSATION})


class MessageRole(StrEnum):
    USER = "user"
    ASSISTANT = "assistant"


class MessageStatus(StrEnum):
    """Operational state of a message. A user message is ``final`` at once; an assistant
    message is a turn of the agent, served by a supervisor."""

    QUEUED = "queued"
    RUNNING = "running"
    FINAL = "final"
    FAILED = "failed"
    CANCELLED = "cancelled"
    INTERRUPTED = "interrupted"


#: States in which a turn may still change by itself.
ACTIVE_MESSAGE_STATUSES: frozenset[MessageStatus] = frozenset(
    {MessageStatus.QUEUED, MessageStatus.RUNNING}
)


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
    RUN_STARTED = "RUN_STARTED"
    RUN_FINISHED = "RUN_FINISHED"
    RUN_CANCEL_REQUESTED = "RUN_CANCEL_REQUESTED"
    RUN_LIMIT_EXCEEDED = "RUN_LIMIT_EXCEEDED"
    RUN_OUTPUT_TRUNCATED = "RUN_OUTPUT_TRUNCATED"
    RUN_LEFTOVER_PROCESSES = "RUN_LEFTOVER_PROCESSES"
    RUN_MONITOR_LOST = "RUN_MONITOR_LOST"
    RUN_SOURCE_CHANGED = "RUN_SOURCE_CHANGED"
    RUN_ADOPTED = "RUN_ADOPTED"
    RUN_REQUEUED = "RUN_REQUEUED"
    RUN_METRIC_NON_FINITE = "RUN_METRIC_NON_FINITE"
    RUN_GUARDRAIL_VIOLATED = "RUN_GUARDRAIL_VIOLATED"
    RUN_METRICS_TRUNCATED = "RUN_METRICS_TRUNCATED"
    RUN_PROGRAM_EVENT = "RUN_PROGRAM_EVENT"
    AGENT_SESSION_STARTED = "AGENT_SESSION_STARTED"
    AGENT_SESSION_UPDATED = "AGENT_SESSION_UPDATED"
    AGENT_POLICY_UPDATED = "AGENT_POLICY_UPDATED"
    AGENT_TURN_QUEUED = "AGENT_TURN_QUEUED"
    AGENT_TURN_STARTED = "AGENT_TURN_STARTED"
    AGENT_TURN_FINISHED = "AGENT_TURN_FINISHED"
    AGENT_TURN_CANCEL_REQUESTED = "AGENT_TURN_CANCEL_REQUESTED"
    AGENT_TURN_ADOPTED = "AGENT_TURN_ADOPTED"
    AGENT_TURN_REQUEUED = "AGENT_TURN_REQUEUED"


class Severity(StrEnum):
    DEBUG = "debug"
    INFO = "info"
    WARNING = "warning"
    ERROR = "error"
