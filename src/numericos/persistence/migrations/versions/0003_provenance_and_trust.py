"""Run provenance (code, inputs, environment) and explicit execution trust of a project.

Revision ID: 0003
Revises: 0002
Create Date: 2026-10-12
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0003"
down_revision = "0002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("projects") as batch:
        batch.add_column(sa.Column("execution_trusted_at", sa.String(length=27), nullable=True))
    with op.batch_alter_table("runs") as batch:
        batch.add_column(sa.Column("code", sa.JSON(), nullable=True))
        batch.add_column(sa.Column("code_sha", sa.String(length=40), nullable=True))
        batch.add_column(sa.Column("inputs", sa.JSON(), nullable=True))
        batch.add_column(sa.Column("environment", sa.JSON(), nullable=True))
        batch.add_column(sa.Column("reproduces_run_id", sa.String(length=40), nullable=True))
        batch.create_index(batch.f("ix_runs_code_sha"), ["code_sha"], unique=False)


def downgrade() -> None:
    with op.batch_alter_table("runs") as batch:
        batch.drop_index(batch.f("ix_runs_code_sha"))
        batch.drop_column("reproduces_run_id")
        batch.drop_column("environment")
        batch.drop_column("inputs")
        batch.drop_column("code_sha")
        batch.drop_column("code")
    with op.batch_alter_table("projects") as batch:
        batch.drop_column("execution_trusted_at")
