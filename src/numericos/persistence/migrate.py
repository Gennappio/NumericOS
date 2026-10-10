"""Programmatic Alembic entry points used by ``numericos serve``, ``numericos db`` and tests.

Migrations run inside one ``BEGIN IMMEDIATE`` transaction on our own engine. Foreign-key
enforcement is switched off *before* the transaction (a PRAGMA inside a transaction is a no-op),
because batch migrations recreate tables; integrity is verified with ``foreign_key_check`` and
enforcement restored before the connection goes back to the pool.
"""

from __future__ import annotations

import sqlite3
from collections.abc import Callable
from pathlib import Path
from typing import cast

from alembic import command
from alembic.config import Config
from alembic.runtime.migration import MigrationContext
from alembic.script import ScriptDirectory
from sqlalchemy.engine import Connection, Engine

MIGRATIONS_DIR = Path(__file__).parent / "migrations"


def alembic_config(connection: Connection | None = None) -> Config:
    config = Config()
    config.set_main_option("script_location", str(MIGRATIONS_DIR))
    if connection is not None:
        config.attributes["connection"] = connection
    return config


def head_revision() -> str:
    head = ScriptDirectory.from_config(alembic_config()).get_current_head()
    if head is None:
        raise RuntimeError("no migration head found")
    return head


def current_revision(engine: Engine) -> str | None:
    with engine.connect() as connection:
        return MigrationContext.configure(connection).get_current_revision()


def _dbapi(connection: Connection) -> sqlite3.Connection:
    return cast(sqlite3.Connection, connection.connection.dbapi_connection)


def _run(engine: Engine, action: Callable[[Config], None]) -> None:
    with engine.connect() as connection:
        raw = _dbapi(connection)
        raw.execute("PRAGMA foreign_keys=OFF")
        try:
            with connection.begin():
                action(alembic_config(connection))
            violations = raw.execute("PRAGMA foreign_key_check").fetchall()
            if violations:
                raise RuntimeError(f"foreign key violations after migration: {violations[:5]}")
        finally:
            raw.execute("PRAGMA foreign_keys=ON")


def upgrade(engine: Engine, revision: str = "head") -> None:
    _run(engine, lambda config: command.upgrade(config, revision))


def downgrade(engine: Engine, revision: str = "base") -> None:
    _run(engine, lambda config: command.downgrade(config, revision))


def check(engine: Engine) -> None:
    """Raise if the ORM models and the migrated schema have drifted apart."""
    _run(engine, command.check)
