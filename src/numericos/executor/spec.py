"""What a monitor is told to execute: the file contract between worker and monitor."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class RunSpec(BaseModel):
    """Written by the worker as ``spec.json`` (mode 0600: it holds the run's environment)."""

    model_config = ConfigDict(populate_by_name=True, extra="forbid")

    schema_: Literal["numericos.run-spec.v1"] = Field(
        default="numericos.run-spec.v1", alias="schema"
    )
    run_id: str
    argv: list[str] = Field(min_length=1)
    cwd: str
    env: dict[str, str]
    build: list[list[str]] = Field(default_factory=list)
    wall_seconds: float = Field(gt=0)
    max_rss_bytes: int | None = None
    grace_seconds: float = Field(ge=0)
    max_output_bytes: int = Field(gt=0)
    resource_interval_seconds: float = Field(gt=0)
