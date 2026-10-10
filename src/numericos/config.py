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

    @field_validator("data_dir")
    @classmethod
    def _expand_user(cls, value: Path) -> Path:
        return value.expanduser()

    @property
    def db_path(self) -> Path:
        return self.data_dir / "numericos.db"
