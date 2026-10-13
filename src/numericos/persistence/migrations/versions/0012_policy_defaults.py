"""The default of a project's policy: the model and effort of the tasks that do not choose.

Revision ID: 0012
Revises: 0011
Create Date: 2026-10-13
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0012"
down_revision = "0011"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # A policy saved before this had no default: its tasks that chose nothing keep running on
    # what the provider uses by itself.
    with op.batch_alter_table("agent_policies") as batch:
        batch.add_column(sa.Column("defaults", sa.JSON(), nullable=False, server_default="{}"))
    with op.batch_alter_table("agent_policies") as batch:
        batch.alter_column("defaults", server_default=None)


def downgrade() -> None:
    with op.batch_alter_table("agent_policies") as batch:
        batch.drop_column("defaults")
