"""Alembic environment. Prefer ``numericos db upgrade``; ``alembic`` is for authoring revisions."""

from __future__ import annotations

from alembic import context
from sqlalchemy.engine import Connection

from numericos.persistence.models import Base

target_metadata = Base.metadata


def run_migrations_online(connection: Connection) -> None:
    context.configure(
        connection=connection,
        target_metadata=target_metadata,
        render_as_batch=True,
        compare_type=True,
    )
    with context.begin_transaction():
        context.run_migrations()


if context.is_offline_mode():
    raise RuntimeError("offline (--sql) migrations are not supported; run `numericos db upgrade`")

_connection = context.config.attributes.get("connection")
if _connection is not None:
    run_migrations_online(_connection)
else:
    # Developer commands (`uv run alembic revision --autogenerate`, `alembic check`).
    from numericos.config import Settings
    from numericos.persistence.engine import make_engine

    with make_engine(Settings().db_path).begin() as _developer_connection:
        run_migrations_online(_developer_connection)
