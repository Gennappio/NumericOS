"""Runtime configuration. Every field can be set through a ``NUMERICOS_`` environment variable."""

from __future__ import annotations

from pathlib import Path

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="NUMERICOS_", extra="ignore")

    data_dir: Path = Field(
        default=Path("~/.numericos"),
        description="Local-first directory for the database and future artifacts.",
    )
    host: str = Field(default="127.0.0.1", description="Bind address; loopback by default.")
    port: int = Field(default=8765, ge=1, le=65535)
    cors_origins: list[str] = Field(
        default_factory=lambda: ["http://localhost:5173", "http://127.0.0.1:5173"],
        description="Browser origins allowed to call the API (JSON list in the environment).",
    )
    api_url: str = Field(
        default="http://127.0.0.1:8765", description="Base URL used by the CLI to reach the API."
    )
    sse_heartbeat_seconds: float = Field(
        default=15.0,
        gt=0,
        le=300,
        description=(
            "Event streams send a keep-alive and re-read the ledger at this interval. It bounds "
            "how late a subscriber learns of events committed by another process."
        ),
    )
    claude_command: list[str] = Field(
        default_factory=lambda: ["claude"],
        min_length=1,
        description=(
            "Command that starts the Claude Code CLI (JSON list in the environment). Tests point "
            "it at a stand-in that speaks the same protocol."
        ),
    )
    agent_max_budget_usd: float = Field(
        default=5.0,
        gt=0,
        description="Spending bound passed to the agent for one turn (--max-budget-usd).",
    )
    agent_max_parallel: int = Field(
        default=2, ge=1, le=16, description="Agent turns a supervisor serves at the same time."
    )
    agent_files_per_turn: int = Field(
        default=8, ge=1, le=50, description="Files the agent is asked to describe in one turn."
    )
    workspace_root: Path | None = Field(
        default=None,
        description=(
            "Where the NumericOS folder of each project is kept: everything NumericOS and its "
            "agent generate about a project. Unset: `.numericos/` inside the project "
            "directory, which ignores itself for Git. Set: `<this directory>/<project id>/`, "
            "outside the project."
        ),
    )

    @field_validator("data_dir", "workspace_root")
    @classmethod
    def _expand_user(cls, value: Path | None) -> Path | None:
        return value.expanduser() if value is not None else None

    @property
    def db_path(self) -> Path:
        return self.data_dir / "numericos.db"
