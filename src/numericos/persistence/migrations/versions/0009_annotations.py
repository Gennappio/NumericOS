"""Comments on what the agent wrote, and the text a Clarify or Resolve session is about.

Revision ID: 0009
Revises: 0008
Create Date: 2026-10-13
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0009"
down_revision = "0008"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "annotations",
        sa.Column("id", sa.String(length=40), nullable=False),
        sa.Column("project_id", sa.String(length=40), nullable=False),
        sa.Column("target_type", sa.String(length=20), nullable=False),
        sa.Column("target_id", sa.String(length=40), nullable=False),
        sa.Column("target_version", sa.Integer(), nullable=False),
        sa.Column("kind", sa.String(length=20), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("status_reason", sa.String(length=300), nullable=True),
        sa.Column("body", sa.Text(), nullable=False),
        sa.Column("start_offset", sa.Integer(), nullable=False),
        sa.Column("end_offset", sa.Integer(), nullable=False),
        sa.Column("quote", sa.Text(), nullable=False),
        sa.Column("prefix", sa.Text(), nullable=False),
        sa.Column("suffix", sa.Text(), nullable=False),
        sa.Column("anchor_state", sa.String(length=20), nullable=False),
        sa.Column("response_markdown", sa.Text(), nullable=True),
        sa.Column("message_id", sa.String(length=40), nullable=True),
        sa.Column("pending_message_id", sa.String(length=40), nullable=True),
        sa.Column("responded_at", sa.String(length=27), nullable=True),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.String(length=27), nullable=False),
        sa.Column("updated_at", sa.String(length=27), nullable=False),
        sa.CheckConstraint(
            "target_type IN ('message', 'document')", name=op.f("ck_annotations_target_type")
        ),
        sa.CheckConstraint(
            "kind IN ('clarification', 'change', 'note')", name=op.f("ck_annotations_kind")
        ),
        sa.CheckConstraint(
            "status IN ('open', 'pending', 'answered', 'resolved', 'declined', 'dismissed')",
            name=op.f("ck_annotations_status"),
        ),
        sa.CheckConstraint(
            "anchor_state IN ('attached', 'detached')", name=op.f("ck_annotations_anchor_state")
        ),
        sa.CheckConstraint(
            "start_offset >= 0 AND end_offset > start_offset", name=op.f("ck_annotations_offsets")
        ),
        sa.ForeignKeyConstraint(
            ["project_id"],
            ["projects.id"],
            name=op.f("fk_annotations_project_id_projects"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_annotations")),
    )
    op.create_index(
        "ix_annotations_target",
        "annotations",
        ["target_type", "target_id", "start_offset"],
        unique=False,
    )
    op.create_index(
        "ix_annotations_pending_message_id", "annotations", ["pending_message_id"], unique=False
    )

    with op.batch_alter_table("agent_sessions") as batch:
        batch.add_column(sa.Column("target_type", sa.String(length=20), nullable=True))
        batch.add_column(sa.Column("target_id", sa.String(length=40), nullable=True))
        batch.add_column(sa.Column("target_version", sa.Integer(), nullable=True))
        batch.create_index(batch.f("ix_agent_sessions_target_id"), ["target_id"], unique=False)


def downgrade() -> None:
    with op.batch_alter_table("agent_sessions") as batch:
        batch.drop_index(batch.f("ix_agent_sessions_target_id"))
        batch.drop_column("target_version")
        batch.drop_column("target_id")
        batch.drop_column("target_type")
    op.drop_index("ix_annotations_pending_message_id", table_name="annotations")
    op.drop_index("ix_annotations_target", table_name="annotations")
    op.drop_table("annotations")
