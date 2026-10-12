"""Model and effort per task of the agent: the project's policy, session overrides, what a
turn was started with and what it consumed of the plan.

Revision ID: 0007
Revises: 0006
Create Date: 2026-10-12
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0007"
down_revision = "0006"
branch_labels = None
depends_on = None

TASKS = (
    "'conversation', 'clarify', 'resolve', 'theory', 'file_description', "
    "'execution_description', 'plan'"
)


def upgrade() -> None:
    with op.batch_alter_table("agent_sessions") as batch:
        batch.add_column(
            sa.Column("task", sa.String(length=30), nullable=False, server_default="conversation")
        )
        batch.add_column(sa.Column("effort", sa.String(length=20), nullable=True))
        batch.create_check_constraint(batch.f("ck_agent_sessions_task"), f"task IN ({TASKS})")
    with op.batch_alter_table("agent_sessions") as batch:
        batch.alter_column("task", server_default=None)

    with op.batch_alter_table("messages") as batch:
        batch.add_column(sa.Column("model_requested", sa.String(length=100), nullable=True))
        batch.add_column(sa.Column("effort", sa.String(length=20), nullable=True))
        batch.add_column(sa.Column("plan_usage", sa.JSON(), nullable=True))

    op.create_table(
        "agent_policies",
        sa.Column("project_id", sa.String(length=40), nullable=False),
        sa.Column("provider", sa.String(length=20), nullable=False),
        sa.Column("tasks", sa.JSON(), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.String(length=27), nullable=False),
        sa.Column("updated_at", sa.String(length=27), nullable=False),
        sa.CheckConstraint("provider IN ('claude_code')", name=op.f("ck_agent_policies_provider")),
        sa.ForeignKeyConstraint(
            ["project_id"],
            ["projects.id"],
            name=op.f("fk_agent_policies_project_id_projects"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("project_id", name=op.f("pk_agent_policies")),
    )


def downgrade() -> None:
    op.drop_table("agent_policies")
    with op.batch_alter_table("messages") as batch:
        batch.drop_column("plan_usage")
        batch.drop_column("effort")
        batch.drop_column("model_requested")
    with op.batch_alter_table("agent_sessions") as batch:
        batch.drop_constraint(batch.f("ck_agent_sessions_task"), type_="check")
        batch.drop_column("effort")
        batch.drop_column("task")
