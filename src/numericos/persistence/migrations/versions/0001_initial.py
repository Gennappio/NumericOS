"""Initial schema: projects, board_cards, events.

Revision ID: 0001
Revises:
Create Date: 2026-10-10
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None

CARD_TYPES = "'task', 'hypothesis', 'experiment', 'issue', 'decision'"
WORKFLOW_STATUSES = "'backlog', 'planned', 'active', 'review', 'completed', 'blocked'"
SEVERITIES = "'debug', 'info', 'warning', 'error'"


def upgrade() -> None:
    op.create_table(
        "projects",
        sa.Column("id", sa.String(length=40), nullable=False),
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column("research_question", sa.Text(), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("root_path", sa.Text(), nullable=True),
        sa.Column("is_demo", sa.Boolean(), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.String(length=27), nullable=False),
        sa.Column("updated_at", sa.String(length=27), nullable=False),
        sa.CheckConstraint("length(name) BETWEEN 1 AND 200", name=op.f("ck_projects_name_length")),
        sa.CheckConstraint("is_demo IN (0, 1)", name=op.f("ck_projects_is_demo_bool")),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_projects")),
    )
    op.create_index(op.f("ix_projects_created_at"), "projects", ["created_at"], unique=False)

    op.create_table(
        "board_cards",
        sa.Column("id", sa.String(length=40), nullable=False),
        sa.Column("project_id", sa.String(length=40), nullable=False),
        sa.Column("card_type", sa.String(length=20), nullable=False),
        sa.Column("title", sa.String(length=300), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("workflow_status", sa.String(length=20), nullable=False),
        sa.Column("sort_order", sa.Integer(), nullable=False),
        sa.Column("entity_ref", sa.String(length=40), nullable=True),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.String(length=27), nullable=False),
        sa.Column("updated_at", sa.String(length=27), nullable=False),
        sa.CheckConstraint(f"card_type IN ({CARD_TYPES})", name=op.f("ck_board_cards_card_type")),
        sa.CheckConstraint(
            f"workflow_status IN ({WORKFLOW_STATUSES})",
            name=op.f("ck_board_cards_workflow_status"),
        ),
        sa.CheckConstraint(
            "length(title) BETWEEN 1 AND 300", name=op.f("ck_board_cards_title_length")
        ),
        sa.ForeignKeyConstraint(
            ["project_id"],
            ["projects.id"],
            name=op.f("fk_board_cards_project_id_projects"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_board_cards")),
    )
    op.create_index(
        "ix_board_cards_project_status_order",
        "board_cards",
        ["project_id", "workflow_status", "sort_order"],
        unique=False,
    )

    op.create_table(
        "events",
        sa.Column("seq", sa.Integer(), nullable=False),
        sa.Column("event_id", sa.String(length=40), nullable=False),
        sa.Column("project_id", sa.String(length=40), nullable=False),
        sa.Column("event_type", sa.String(length=60), nullable=False),
        sa.Column("subject_id", sa.String(length=40), nullable=False),
        sa.Column("actor", sa.String(length=120), nullable=False),
        sa.Column("producer", sa.String(length=60), nullable=False),
        sa.Column("severity", sa.String(length=10), nullable=False),
        sa.Column("correlation_id", sa.String(length=64), nullable=False),
        sa.Column("schema_version", sa.Integer(), nullable=False),
        sa.Column("payload", sa.JSON(), nullable=False),
        sa.Column("timestamp_utc", sa.String(length=27), nullable=False),
        sa.CheckConstraint(f"severity IN ({SEVERITIES})", name=op.f("ck_events_severity")),
        sa.ForeignKeyConstraint(
            ["project_id"], ["projects.id"], name=op.f("fk_events_project_id_projects")
        ),
        sa.PrimaryKeyConstraint("seq", name=op.f("pk_events")),
        sa.UniqueConstraint("event_id", name=op.f("uq_events_event_id")),
        sqlite_autoincrement=True,
    )
    op.create_index("ix_events_project_seq", "events", ["project_id", "seq"], unique=False)
    op.create_index(op.f("ix_events_subject_id"), "events", ["subject_id"], unique=False)
    op.create_index(op.f("ix_events_correlation_id"), "events", ["correlation_id"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_events_correlation_id"), table_name="events")
    op.drop_index(op.f("ix_events_subject_id"), table_name="events")
    op.drop_index("ix_events_project_seq", table_name="events")
    op.drop_table("events")
    op.drop_index("ix_board_cards_project_status_order", table_name="board_cards")
    op.drop_table("board_cards")
    op.drop_index(op.f("ix_projects_created_at"), table_name="projects")
    op.drop_table("projects")
