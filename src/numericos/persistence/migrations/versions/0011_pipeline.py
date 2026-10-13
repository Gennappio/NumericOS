"""The pipeline of a project: a document with boxes and arrows, and the task that writes it
(which takes the place of the execution description, never built under that name).

Revision ID: 0011
Revises: 0010
Create Date: 2026-10-13
"""

from __future__ import annotations

import json

import sqlalchemy as sa
from alembic import op

revision = "0011"
down_revision = "0010"
branch_labels = None
depends_on = None

KINDS = "'theory', 'file_description', 'plan'"
TASKS = "'conversation', 'clarify', 'resolve', 'theory', 'file_description', {task}, 'plan'"
OLD_TASK, NEW_TASK = "execution_description", "pipeline"


def _rename_task(old: str, new: str) -> None:
    """Sessions and saved policies name the task: both follow it to its new name."""
    with op.batch_alter_table("agent_sessions") as batch:
        batch.drop_constraint(batch.f("ck_agent_sessions_task"), type_="check")
    connection = op.get_bind()
    connection.execute(
        sa.text("UPDATE agent_sessions SET task = :new WHERE task = :old"), {"old": old, "new": new}
    )
    for project_id, tasks in connection.execute(
        sa.text("SELECT project_id, tasks FROM agent_policies")
    ).fetchall():
        stored = json.loads(tasks) if isinstance(tasks, str) else tasks
        if old not in stored:
            continue
        stored[new] = stored.pop(old)
        connection.execute(
            sa.text("UPDATE agent_policies SET tasks = :tasks WHERE project_id = :project_id"),
            {"tasks": json.dumps(stored), "project_id": project_id},
        )
    with op.batch_alter_table("agent_sessions") as batch:
        batch.create_check_constraint(
            batch.f("ck_agent_sessions_task"), f"task IN ({TASKS.format(task=repr(new))})"
        )


def upgrade() -> None:
    with op.batch_alter_table("documents") as batch:
        batch.add_column(sa.Column("pipeline", sa.JSON(), nullable=True))
        batch.drop_constraint(batch.f("ck_documents_kind"), type_="check")
        batch.create_check_constraint(
            batch.f("ck_documents_kind"), f"kind IN ({KINDS}, 'pipeline')"
        )
    _rename_task(OLD_TASK, NEW_TASK)


def downgrade() -> None:
    _rename_task(NEW_TASK, OLD_TASK)
    # A pipeline has no place in the schema before: it goes, and so do the comments on it.
    connection = op.get_bind()
    connection.execute(
        sa.text(
            "DELETE FROM annotations WHERE target_type = 'document' AND target_id IN "
            "(SELECT id FROM documents WHERE kind = 'pipeline')"
        )
    )
    connection.execute(sa.text("DELETE FROM documents WHERE kind = 'pipeline'"))
    with op.batch_alter_table("documents") as batch:
        batch.drop_constraint(batch.f("ck_documents_kind"), type_="check")
        batch.create_check_constraint(batch.f("ck_documents_kind"), f"kind IN ({KINDS})")
        batch.drop_column("pipeline")
