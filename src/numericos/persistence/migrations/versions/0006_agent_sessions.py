"""Conversations with a coding agent: sessions and messages (turns) of a project.

Revision ID: 0006
Revises: 0005
Create Date: 2026-10-12
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0006"
down_revision = "0005"
branch_labels = None
depends_on = None

PROVIDERS = "'claude_code'"
PERMISSION_MODES = "'read_only', 'edit', 'full'"
ROLES = "'user', 'assistant'"
STATUSES = "'queued', 'running', 'final', 'failed', 'cancelled', 'interrupted'"


def upgrade() -> None:
    op.create_table(
        "agent_sessions",
        sa.Column("id", sa.String(length=40), nullable=False),
        sa.Column("project_id", sa.String(length=40), nullable=False),
        sa.Column("title", sa.String(length=200), nullable=False),
        sa.Column("provider", sa.String(length=20), nullable=False),
        sa.Column("permission_mode", sa.String(length=20), nullable=False),
        sa.Column("model", sa.String(length=100), nullable=True),
        sa.Column("native_session_id", sa.String(length=64), nullable=False),
        sa.Column("cwd", sa.Text(), nullable=False),
        sa.Column("system_prompt", sa.Text(), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.String(length=27), nullable=False),
        sa.Column("updated_at", sa.String(length=27), nullable=False),
        sa.CheckConstraint(f"provider IN ({PROVIDERS})", name=op.f("ck_agent_sessions_provider")),
        sa.CheckConstraint(
            f"permission_mode IN ({PERMISSION_MODES})",
            name=op.f("ck_agent_sessions_permission_mode"),
        ),
        sa.CheckConstraint(
            "length(title) BETWEEN 1 AND 200", name=op.f("ck_agent_sessions_title_length")
        ),
        sa.ForeignKeyConstraint(
            ["project_id"],
            ["projects.id"],
            name=op.f("fk_agent_sessions_project_id_projects"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_agent_sessions")),
    )
    op.create_index(
        "ix_agent_sessions_project_created",
        "agent_sessions",
        ["project_id", "created_at"],
        unique=False,
    )

    op.create_table(
        "messages",
        sa.Column("id", sa.String(length=40), nullable=False),
        sa.Column("session_id", sa.String(length=40), nullable=False),
        sa.Column("project_id", sa.String(length=40), nullable=False),
        sa.Column("role", sa.String(length=10), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("status_reason", sa.String(length=300), nullable=True),
        sa.Column("markdown", sa.Text(), nullable=False),
        sa.Column("prompt_message_id", sa.String(length=40), nullable=True),
        sa.Column("correlation_id", sa.String(length=64), nullable=True),
        sa.Column("model", sa.String(length=100), nullable=True),
        sa.Column("activity", sa.JSON(), nullable=False),
        sa.Column("activity_dropped", sa.Integer(), nullable=False),
        sa.Column("files_read", sa.JSON(), nullable=False),
        sa.Column("files_written", sa.JSON(), nullable=False),
        sa.Column("permission_denials", sa.JSON(), nullable=False),
        sa.Column("cost_usd", sa.Float(), nullable=True),
        sa.Column("usage", sa.JSON(), nullable=True),
        sa.Column("num_turns", sa.Integer(), nullable=True),
        sa.Column("structured_output", sa.JSON(), nullable=True),
        sa.Column("worker_id", sa.String(length=40), nullable=True),
        sa.Column("pid", sa.Integer(), nullable=True),
        sa.Column("process_started_at", sa.Float(), nullable=True),
        sa.Column("started_at", sa.String(length=27), nullable=True),
        sa.Column("finished_at", sa.String(length=27), nullable=True),
        sa.Column("heartbeat_at", sa.String(length=27), nullable=True),
        sa.Column("cancel_requested_at", sa.String(length=27), nullable=True),
        sa.Column("cancel_reason", sa.String(length=300), nullable=True),
        sa.Column("exit_code", sa.Integer(), nullable=True),
        sa.Column("ingest", sa.JSON(), nullable=True),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.String(length=27), nullable=False),
        sa.Column("updated_at", sa.String(length=27), nullable=False),
        sa.CheckConstraint(f"role IN ({ROLES})", name=op.f("ck_messages_role")),
        sa.CheckConstraint(f"status IN ({STATUSES})", name=op.f("ck_messages_status")),
        sa.ForeignKeyConstraint(
            ["project_id"],
            ["projects.id"],
            name=op.f("fk_messages_project_id_projects"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["session_id"],
            ["agent_sessions.id"],
            name=op.f("fk_messages_session_id_agent_sessions"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_messages")),
    )
    op.create_index(
        "ix_messages_session_created", "messages", ["session_id", "created_at"], unique=False
    )
    op.create_index("ix_messages_status", "messages", ["status"], unique=False)
    op.create_index(op.f("ix_messages_worker_id"), "messages", ["worker_id"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_messages_worker_id"), table_name="messages")
    op.drop_index("ix_messages_status", table_name="messages")
    op.drop_index("ix_messages_session_created", table_name="messages")
    op.drop_table("messages")
    op.drop_index("ix_agent_sessions_project_created", table_name="agent_sessions")
    op.drop_table("agent_sessions")
