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
AVAILABLE_TASKS: frozenset[AgentTask] = frozenset(
    {
        AgentTask.CONVERSATION,
        AgentTask.CLARIFY,
        AgentTask.RESOLVE,
        AgentTask.THEORY,
        AgentTask.FILE_DESCRIPTION,
        AgentTask.PLAN,
    }
)


class TargetType(StrEnum):
    """What a comment is attached to: an answer of the agent, or a document it wrote."""

    MESSAGE = "message"
    DOCUMENT = "document"


class AnnotationKind(StrEnum):
    """What the researcher wants about a passage. A clarification asks the agent to explain
    it; a change asks for the code or the text to be changed; a note is for people only."""

    CLARIFICATION = "clarification"
    CHANGE = "change"
    NOTE = "note"


class AnnotationStatus(StrEnum):
    OPEN = "open"
    #: Sent to the agent with Clarify or Resolve; its turn has not ended.
    PENDING = "pending"
    #: A clarification the agent answered.
    ANSWERED = "answered"
    #: A change the agent carried out.
    RESOLVED = "resolved"
    #: A change the agent decided not to make, with its reason.
    DECLINED = "declined"
    #: Withdrawn by the researcher.
    DISMISSED = "dismissed"


class AnchorState(StrEnum):
    """Whether the passage of a comment is found in the current text of its target."""

    ATTACHED = "attached"
    #: The text was rewritten and the passage is not in it any more, or not unambiguously.
    DETACHED = "detached"


class DocumentKind(StrEnum):
    """What a document written by the agent is about."""

    THEORY = "theory"
    FILE_DESCRIPTION = "file_description"
    PLAN = "plan"


class DocumentStatus(StrEnum):
    """Whether a document has content. Whether its content is still current is not a status:
    it is computed from the files it was written from, every time it is read."""

    GENERATING = "generating"
    READY = "ready"
    FAILED = "failed"


class FileCategory(StrEnum):
    """What a file of the project is. ``data`` is what can be told from the name alone; the
    agent's description says whether it is read (input) or written (output)."""

    CODE = "code"
    INPUT = "input"
    OUTPUT = "output"
    DATA = "data"
    IMAGE = "image"
    CONFIG = "config"
    DOCUMENTATION = "documentation"
    OTHER = "other"


class CardOrigin(StrEnum):
    USER = "user"
    AGENT = "agent"


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
    DOCUMENT_GENERATION_QUEUED = "DOCUMENT_GENERATION_QUEUED"
    DOCUMENT_GENERATION_FINISHED = "DOCUMENT_GENERATION_FINISHED"
    ANNOTATION_CREATED = "ANNOTATION_CREATED"
    ANNOTATION_UPDATED = "ANNOTATION_UPDATED"
    ANNOTATIONS_SENT = "ANNOTATIONS_SENT"
    ANNOTATIONS_ANSWERED = "ANNOTATIONS_ANSWERED"
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
