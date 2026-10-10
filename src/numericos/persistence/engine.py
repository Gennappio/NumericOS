"""Engine policy for the local SQLite database.

- WAL journal, foreign keys ON, synchronous=FULL, busy timeout 5 s on every connection.
- pysqlite's implicit BEGIN is disabled and every transaction starts with ``BEGIN IMMEDIATE``:
  writers are serialised up front, so a read-then-write transaction can never fail with
  ``SQLITE_BUSY_SNAPSHOT`` and the busy timeout actually applies.
- Timestamps are stored as fixed-width UTC ISO-8601 text; naive datetimes are rejected.
"""

from __future__ import annotations

import sqlite3
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from sqlalchemy import String, create_engine, event
from sqlalchemy.engine import Connection, Dialect, Engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.types import TypeDecorator

TIMESTAMP_FORMAT = "%Y-%m-%dT%H:%M:%S.%fZ"
BUSY_TIMEOUT_MS = 5000


class UTCDateTime(TypeDecorator[datetime]):
    """Aware UTC datetime <-> ``YYYY-MM-DDTHH:MM:SS.ffffffZ`` text (27 characters)."""

    impl = String(27)
    cache_ok = True

    def process_bind_param(self, value: datetime | None, dialect: Dialect) -> str | None:
        if value is None:
            return None
        if value.tzinfo is None:
            raise ValueError("naive datetime rejected: timestamps must be timezone-aware UTC")
        return value.astimezone(UTC).strftime(TIMESTAMP_FORMAT)

    def process_result_value(self, value: Any | None, dialect: Dialect) -> datetime | None:
        if value is None:
            return None
        return datetime.strptime(str(value), TIMESTAMP_FORMAT).replace(tzinfo=UTC)


def utcnow() -> datetime:
    return datetime.now(UTC)


def database_url(db_path: Path) -> str:
    return f"sqlite+pysqlite:///{db_path}"


def make_engine(db_path: Path) -> Engine:
    """Engine for ``db_path``. The parent directory must exist; nothing is created here."""
    engine = create_engine(
        database_url(db_path),
        connect_args={"check_same_thread": False, "timeout": BUSY_TIMEOUT_MS / 1000},
    )

    @event.listens_for(engine, "connect")
    def _configure_connection(dbapi_connection: sqlite3.Connection, _record: Any) -> None:
        dbapi_connection.isolation_level = None  # no implicit BEGIN from pysqlite
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA journal_mode=WAL")
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.execute("PRAGMA synchronous=FULL")
        cursor.execute(f"PRAGMA busy_timeout={BUSY_TIMEOUT_MS}")
        cursor.close()

    @event.listens_for(engine, "begin")
    def _begin_immediate(connection: Connection) -> None:
        connection.exec_driver_sql("BEGIN IMMEDIATE")

    return engine


def make_session_factory(engine: Engine) -> sessionmaker[Session]:
    return sessionmaker(bind=engine, expire_on_commit=False)
