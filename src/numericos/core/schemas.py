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

from numericos.core.agents import ActivityItem, PermissionDenial, PlanUsage, TurnUsage
from numericos.core.enums import (
    AgentProvider,
    AgentTask,
    CardOrigin,
    CardType,
    DocumentKind,
    DocumentStatus,
    EpistemicStatus,
    FailureClass,
    FileCategory,
    MessageRole,
    MessageStatus,
    PermissionMode,
    RunStatus,
    WorkflowStatus,
)
from numericos.core.execution import LogLine, ResourceSample, ResourceSummary, RunOutcome
from numericos.core.experiment import ExperimentProtocol, ParameterValue
from numericos.core.metrics import SeriesSummary
from numericos.core.provenance import CodeProvenance, EnvironmentRecord, InputRecord


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
    execution_trusted_at: datetime | None = Field(
        default=None,
        description="When executing commands in root_path was explicitly allowed; null if not.",
    )
    version: int
    created_at: datetime
    updated_at: datetime


class ExecutionTrust(StrictModel):
    """Allow NumericOS to execute commands in the project directory.

    The caller repeats the exact path: trust is given to a directory, not to a project name.
    """

    version: int = Field(ge=1, description="Current version of the project.")
    root_path: str = Field(description="Must equal the project's root_path.")


class ProjectVersion(StrictModel):
    version: int = Field(ge=1, description="Current version of the project.")


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
    origin: CardOrigin = Field(
        default=CardOrigin.USER, description="Who put the card on the board: you or the agent."
    )
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


class ContractImport(StrictModel):
    """An experiment contract to register: as text, or as a file of the project directory."""

    path: str | None = Field(
        default=None, max_length=1000, description="Relative to the project's code path."
    )
    text: str | None = Field(
        default=None, max_length=262144, description="The contract itself, YAML or JSON."
    )
    reuse: bool = Field(
        default=True,
        description="Return the experiment that already has this name and exactly this protocol.",
    )

    @model_validator(mode="after")
    def _one_source(self) -> Self:
        if (self.path is None) == (self.text is None):
            raise ValueError("give exactly one of 'path' and 'text'")
        return self


class ContractFile(BaseModel):
    """A file of the project's repository that is an experiment contract."""

    path: str = Field(description="Relative to the project's code path.")
    name: str = Field(description="The experiment's name: 'name' in the file, else the file's.")
    question: str
    valid: bool
    problems: list[str] = Field(description="Why it is not a valid contract, if it is not.")
    experiment_id: str | None = Field(
        description="The experiment already registered with this name and exactly this content."
    )


class ContractFileList(BaseModel):
    files: list[ContractFile]
    scanned: int = Field(description="How many YAML files of the repository were looked at.")
    truncated: bool = Field(description="The repository has more YAML files than are scanned.")


class ExperimentSeries(SeriesSummary):
    """The summary of one metric of one run, for looking at the runs of an experiment together."""

    run_id: str


class ExperimentSeriesList(BaseModel):
    series: list[ExperimentSeries]


class RunCreate(StrictModel):
    parameters: dict[str, ParameterValue] = Field(
        default_factory=dict,
        description="One declared value for every independent variable of the experiment.",
    )
    seed: int | None = Field(default=None, ge=0, le=2**63 - 1)
    label: str = Field(default="", max_length=200)
    code_ref: str | None = Field(
        default=None,
        min_length=1,
        max_length=200,
        pattern=r"^[^-\s][^\s]*$",
        description=(
            "The commit this run executes (branch, tag or SHA), instead of the protocol's "
            "default ref. This is how a candidate and a baseline differ under one protocol."
        ),
    )


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
    code: CodeProvenance | None = Field(description="The exact code this run executes.")
    inputs: list[InputRecord] | None = Field(
        description="Checksums of the declared inputs. Null until the run starts."
    )
    environment: EnvironmentRecord | None = Field(
        description="Host, program file, probes and variables. Null until the run starts."
    )
    reproduces_run_id: str | None = Field(
        description="The run this one repeats with the same code, parameters and seed."
    )
    worker_id: str | None = Field(description="The supervisor currently responsible for the run.")
    pid: int | None = Field(description="Process ID of the program while it runs.")
    started_at: datetime | None = Field(description="When the program started, not when queued.")
    finished_at: datetime | None
    heartbeat_at: datetime | None = Field(
        description="When a supervisor last recorded progress of this run."
    )
    cancel_requested_at: datetime | None
    cancel_reason: str | None = Field(description="Why the run was asked to stop, if it was.")
    exit_code: int | None
    exit_signal: str | None
    wall_seconds: float | None
    outcome: RunOutcome | None = Field(
        description="How the program ended, as its monitor recorded it. Null until then."
    )
    resources: ResourceSummary | None = Field(
        description="Summary of the resource samples taken so far."
    )
    version: int
    created_at: datetime
    updated_at: datetime


class RunList(BaseModel):
    runs: list[RunOut]


class RunCancel(StrictModel):
    reason: str = Field(default="", max_length=300)


class LogPage(BaseModel):
    """Output lines after a cursor. ``complete`` means the run ended and nothing follows."""

    lines: list[LogLine]
    next_cursor: int = Field(description="Pass as 'after' to continue. It is a byte offset.")
    has_more: bool = Field(description="More lines are already recorded after 'next_cursor'.")
    complete: bool = Field(description="The run ended and every line has been returned.")


class ResourcePage(BaseModel):
    samples: list[ResourceSample]
    next_cursor: int
    has_more: bool
    complete: bool


class ArtifactOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    run_id: str
    kind: str
    name: str = Field(description="Path inside the run directory.")
    media_type: str
    size_bytes: int
    sha256: str | None = Field(description="Null for files too large to hash.")
    created_at: datetime


class ArtifactList(BaseModel):
    artifacts: list[ArtifactOut]


class WorkerOut(BaseModel):
    id: str
    pid: int
    hostname: str
    version: str
    max_parallel_runs: int
    started_at: datetime
    heartbeat_at: datetime
    stopped_at: datetime | None
    alive: bool = Field(description="It has not stopped and its heartbeat is recent.")
    active_runs: int


class WorkerList(BaseModel):
    workers: list[WorkerOut]
    alive: int = Field(description="How many supervisors can currently start queued runs.")


class AgentSessionCreate(StrictModel):
    title: str | None = Field(
        default=None, min_length=1, max_length=200, description="Defaults to the first prompt."
    )
    permission_mode: PermissionMode = Field(
        default=PermissionMode.EDIT,
        description=(
            "read_only: the agent reads the repository, edits and commands are refused; edit: "
            "file edits are allowed, commands are refused; full: everything is allowed."
        ),
    )
    model: str | None = Field(
        default=None,
        max_length=100,
        description="Overrides the policy's model for this session; null takes the policy's.",
    )
    effort: str | None = Field(
        default=None,
        max_length=20,
        description="Overrides the policy's effort for this session; null takes the policy's.",
    )


class AgentSessionPatch(StrictModel):
    version: int = Field(ge=1, description="Current version of the session.")
    title: str | None = Field(default=None, min_length=1, max_length=200)
    permission_mode: PermissionMode | None = Field(
        default=None, description="Applies to the turns queued from now on."
    )
    model: str | None = Field(
        default=None,
        max_length=100,
        description="Explicit null takes the policy's choice again; an absent field keeps it.",
    )
    effort: str | None = Field(
        default=None,
        max_length=20,
        description="Explicit null takes the policy's choice again; an absent field keeps it.",
    )

    @model_validator(mode="after")
    def _no_explicit_nulls(self) -> Self:
        _reject_explicit_nulls(self, ("title", "permission_mode"))
        return self


class AgentSessionOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    project_id: str
    title: str
    provider: AgentProvider
    permission_mode: PermissionMode
    task: AgentTask = Field(description="What the session is for; names its row of the policy.")
    model: str | None = Field(description="This session's override of the policy, if any.")
    effort: str | None = Field(description="This session's override of the policy, if any.")
    native_session_id: str = Field(description="The provider's identifier of this session.")
    cwd: str = Field(description="The directory the agent works in.")
    message_count: int = 0
    version: int
    created_at: datetime
    updated_at: datetime


class AgentSessionList(BaseModel):
    sessions: list[AgentSessionOut]


class MessageCreate(StrictModel):
    content: str = Field(min_length=1, max_length=200_000, description="The prompt, Markdown.")


class MessageOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    session_id: str
    project_id: str
    role: MessageRole
    status: MessageStatus
    status_reason: str | None
    markdown: str = Field(description="The prompt, or the final answer once the turn ended.")
    prompt_message_id: str | None = Field(
        default=None, description="Assistant: the user message this turn answers."
    )
    model_requested: str | None = Field(
        default=None, description="The model the turn was started with (session or policy)."
    )
    effort: str | None = Field(default=None, description="The effort the turn was started with.")
    model: str | None = Field(default=None, description="The model that answered, as reported.")
    activity: list[ActivityItem] = Field(
        description="What the agent did, in order, while it worked; grows during the turn."
    )
    activity_dropped: int = Field(description="Actions beyond the bound, kept only in the file.")
    files_read: list[str]
    files_written: list[str]
    permission_denials: list[PermissionDenial]
    cost_usd: float | None = Field(
        description=(
            "What the turn would cost at the provider's list prices, as the provider computes "
            "it. With a subscription nothing is charged per turn: it measures the tokens used."
        )
    )
    usage: TurnUsage | None
    plan_usage: PlanUsage | None = Field(
        default=None, description="Use of the account's plan windows as last reported."
    )
    num_turns: int | None = Field(default=None, description="Model calls the turn took.")
    structured_output: Any | None = None
    worker_id: str | None = Field(default=None, description="The supervisor serving the turn.")
    pid: int | None = Field(default=None, description="The agent process, while it runs.")
    exit_code: int | None = None
    started_at: datetime | None
    finished_at: datetime | None
    cancel_requested_at: datetime | None
    cancel_reason: str | None
    version: int
    created_at: datetime
    updated_at: datetime


class MessageList(BaseModel):
    messages: list[MessageOut]


class MessageCancel(StrictModel):
    reason: str = Field(default="", max_length=300)


class TaskPolicy(StrictModel):
    """The model and effort for one kind of task; null takes the provider's default."""

    model: str | None = Field(default=None, max_length=100)
    effort: str | None = Field(default=None, max_length=20)


class AgentPolicyOut(BaseModel):
    project_id: str
    provider: AgentProvider
    tasks: dict[AgentTask, TaskPolicy] = Field(description="One entry per task, always.")
    available: list[AgentTask] = Field(
        description="Tasks a built feature uses today; the others wait for theirs."
    )
    version: int = Field(description="0 until the policy was saved once.")
    updated_at: datetime | None


class AgentPolicyPut(StrictModel):
    version: int = Field(ge=0, description="Current version; 0 saves it for the first time.")
    tasks: dict[AgentTask, TaskPolicy] = Field(
        description="Tasks to set; a task left out keeps the provider's default."
    )


class SourceRef(BaseModel):
    path: str
    sha: str | None = Field(description="Content hash of the file when the document was written.")


class DocumentOut(BaseModel):
    """A document the agent wrote about the project."""

    model_config = ConfigDict(from_attributes=True)

    id: str
    project_id: str
    kind: DocumentKind
    key: str = Field(description="The file's path for a file description; else the kind.")
    title: str
    summary: str
    category: FileCategory | None
    markdown: str
    status: DocumentStatus
    status_reason: str | None
    instructions: str = Field(description="What the researcher added to the request.")
    sources: list[SourceRef] = Field(description="The files the content was written from.")
    session_id: str | None = Field(description="The conversation in which it was written.")
    message_id: str | None = Field(description="The turn that wrote the current content.")
    pending_message_id: str | None = Field(
        description="The turn that is writing the next content, while there is one."
    )
    model: str | None
    generated_at: datetime | None
    version: int = Field(description="How many times the content was written; 0 before the first.")
    created_at: datetime
    updated_at: datetime
    stale: bool = Field(
        default=False, description="A file it was written from has changed since, or is gone."
    )
    changed_sources: list[str] = Field(
        default_factory=list, description="Those files, as they are found now."
    )


class DocumentSlot(BaseModel):
    """A document that exists once per project (the theory, the plan notes), or nothing yet."""

    document: DocumentOut | None


class GenerateRequest(StrictModel):
    instructions: str | None = Field(
        default=None,
        max_length=5000,
        description=(
            "Added to what the agent is asked (a language, an emphasis). Absent keeps the "
            "instructions of the previous request."
        ),
    )


class FileDescriptionState(BaseModel):
    document_id: str
    status: DocumentStatus
    summary: str
    stale: bool = Field(description="The file has changed since it was described.")
    pending: bool = Field(description="The agent is describing it now.")
    status_reason: str | None
    updated_at: datetime


class FileEntry(BaseModel):
    path: str
    size_bytes: int
    category: FileCategory = Field(
        description="From the description when there is one, else guessed from the name."
    )
    sha: str | None = Field(description="Content hash of the file as it is now.")
    viewable_image: bool
    description: FileDescriptionState | None


class FileCounts(BaseModel):
    total: int
    described: int = Field(description="Described and unchanged since.")
    stale: int
    generating: int
    failed: int
    undescribed: int


class FileList(BaseModel):
    root: str
    files: list[FileEntry]
    counts: FileCounts
    truncated: bool = Field(description="The project has more files than are listed.")


class DescribeRequest(StrictModel):
    paths: list[str] | None = Field(default=None, min_length=1, max_length=400)
    scope: Literal["undescribed", "stale", "all"] | None = Field(
        default=None, description="Instead of paths: every file in that state."
    )
    instructions: str | None = Field(default=None, max_length=5000)

    @model_validator(mode="after")
    def _one_selection(self) -> Self:
        if (self.paths is None) == (self.scope is None):
            raise ValueError("pass either paths or scope")
        return self


class DescribeOut(BaseModel):
    queued: int = Field(description="Files the agent was asked to describe.")
    turns: int = Field(description="Agent turns queued for them.")
    skipped: int = Field(description="Files left out because they are being described already.")
    left: int = Field(description="Files of the scope beyond the bound of one request.")
    message_ids: list[str]


class RunRecord(BaseModel):
    """Everything needed to repeat a run: the run, with its provenance, and its protocol."""

    model_config = ConfigDict(populate_by_name=True)

    schema_: Literal["numericos.run-record.v1"] = Field(
        default="numericos.run-record.v1", alias="schema"
    )
    exported_at: datetime
    run: RunOut
    experiment: ExperimentOut


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
