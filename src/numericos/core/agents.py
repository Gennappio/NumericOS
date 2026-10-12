"""What is recorded about a turn of the coding agent: its visible actions and how it ended.

An agent event describes an observed action (a file read, a command run, text written), never
the model's hidden reasoning. The shapes here are provider-neutral; the adapter of each provider
maps its own protocol onto them.
"""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field

from numericos.core.enums import AgentProvider

#: Bounds on what is kept about one turn in the database. The complete stream stays in the
#: turn's file.
ACTIVITY_LIMIT = 400
TEXT_LIMIT = 4000
SUMMARY_LIMIT = 200


class ToolCall(BaseModel):
    """One use of a tool by the agent, summarised in a line: the file, the command, the pattern."""

    id: str
    name: str
    summary: str
    ok: bool | None = Field(
        default=None, description="Whether the tool succeeded; null until its result is seen."
    )


class ActivityItem(BaseModel):
    """What the agent did, in order: text it wrote between actions, or a tool it used."""

    kind: Literal["text", "tool"]
    at: float = Field(description="When the supervisor read it (epoch seconds).")
    text: str | None = None
    tool: ToolCall | None = None


class PermissionDenial(BaseModel):
    """A tool the agent asked for that the permission mode of the session refused."""

    tool_name: str
    summary: str


class TurnUsage(BaseModel):
    input_tokens: int = 0
    output_tokens: int = 0
    cache_read_input_tokens: int = 0
    cache_creation_input_tokens: int = 0


class TurnResult(BaseModel):
    """How a turn ended, as the provider reported it."""

    is_error: bool
    subtype: str = Field(description="The provider's own word for how the turn ended.")
    text: str = Field(description="The final answer, Markdown.")
    structured_output: Any | None = Field(
        default=None, description="The answer validated against the requested JSON schema, if any."
    )
    cost_usd: float | None = None
    usage: TurnUsage | None = None
    num_turns: int | None = None
    duration_ms: int | None = None
    permission_denials: list[PermissionDenial] = Field(default_factory=list)
    native_session_id: str | None = None


class WindowUsage(BaseModel):
    utilization: float = Field(description="Share of the window used, 0 to 1.")
    resets_at: float = Field(description="When the window resets (epoch seconds).")


class PlanUsage(BaseModel):
    """Use of the account's plan as the provider last reported it during a turn. With a
    subscription this, not a price, is what a turn consumes."""

    five_hour: WindowUsage | None = None
    seven_day: WindowUsage | None = None
    using_overage: bool = False


class ModelChoice(BaseModel):
    """A model the provider can be asked for."""

    id: str = Field(description="What is passed to the provider.")
    label: str
    note: str = Field(default="", description="What distinguishes it, in a few words.")


class AgentCapabilities(BaseModel):
    """Whether the provider can be started where NumericOS runs, as found, never assumed, and
    what it can be asked for."""

    provider: AgentProvider
    command: list[str]
    available: bool
    path: str | None = Field(default=None, description="Resolved executable, if found.")
    version: str | None = Field(default=None, description="What `--version` printed, if it ran.")
    problem: str | None = Field(default=None, description="Why it is not available, if it is not.")
    models: list[ModelChoice] = Field(
        default_factory=list, description="Models that can be asked for; empty when unavailable."
    )
    efforts: list[str] = Field(
        default_factory=list, description="Effort levels the provider accepts, lightest first."
    )
