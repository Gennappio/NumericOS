"""Documents written by the agent (theory, file descriptions, plan notes), the origin of a
board card and the JSON schema of a structured turn.

Revision ID: 0008
Revises: 0007
Create Date: 2026-10-12
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0008"
down_revision = "0007"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "documents",
        sa.Column("id", sa.String(length=40), nullable=False),
        sa.Column("project_id", sa.String(length=40), nullable=False),
        sa.Column("kind", sa.String(length=30), nullable=False),
        sa.Column("doc_key", sa.String(length=1000), nullable=False),
        sa.Column("title", sa.String(length=300), nullable=False),
        sa.Column("summary", sa.Text(), nullable=False),
        sa.Column("category", sa.String(length=20), nullable=True),
        sa.Column("markdown", sa.Text(), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("status_reason", sa.String(length=300), nullable=True),
        sa.Column("instructions", sa.Text(), nullable=False),
        sa.Column("subject_sha", sa.String(length=64), nullable=True),
        sa.Column("sources", sa.JSON(), nullable=False),
        sa.Column("session_id", sa.String(length=40), nullable=True),
        sa.Column("message_id", sa.String(length=40), nullable=True),
        sa.Column("pending_message_id", sa.String(length=40), nullable=True),
        sa.Column("model", sa.String(length=100), nullable=True),
        sa.Column("generated_at", sa.String(length=27), nullable=True),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.String(length=27), nullable=False),
        sa.Column("updated_at", sa.String(length=27), nullable=False),
        sa.CheckConstraint(
            "kind IN ('theory', 'file_description', 'plan')", name=op.f("ck_documents_kind")
        ),
        sa.CheckConstraint(
            "status IN ('generating', 'ready', 'failed')", name=op.f("ck_documents_status")
        ),
        sa.ForeignKeyConstraint(
            ["project_id"],
            ["projects.id"],
            name=op.f("fk_documents_project_id_projects"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_documents")),
        sa.UniqueConstraint("project_id", "kind", "doc_key", name="uq_documents_project_kind_key"),
    )
    op.create_index(
        "ix_documents_pending_message_id", "documents", ["pending_message_id"], unique=False
    )

    with op.batch_alter_table("board_cards") as batch:
        batch.add_column(
            sa.Column("origin", sa.String(length=10), nullable=False, server_default="user")
        )
        batch.create_check_constraint(
            batch.f("ck_board_cards_origin"), "origin IN ('user', 'agent')"
        )
    with op.batch_alter_table("board_cards") as batch:
        batch.alter_column("origin", server_default=None)

    with op.batch_alter_table("messages") as batch:
        batch.add_column(sa.Column("json_schema", sa.JSON(), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("messages") as batch:
        batch.drop_column("json_schema")
    with op.batch_alter_table("board_cards") as batch:
        batch.drop_constraint(batch.f("ck_board_cards_origin"), type_="check")
        batch.drop_column("origin")
    op.drop_index("ix_documents_pending_message_id", table_name="documents")
    op.drop_table("documents")
