"""What a turn of the agent left in the repository, and what was moved out of it.

Revision ID: 0010
Revises: 0009
Create Date: 2026-10-13
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0010"
down_revision = "0009"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("messages") as batch:
        batch.add_column(sa.Column("files_created", sa.JSON(), nullable=False, server_default="[]"))
        batch.add_column(sa.Column("files_moved", sa.JSON(), nullable=False, server_default="[]"))
    with op.batch_alter_table("messages") as batch:
        batch.alter_column("files_created", server_default=None)
        batch.alter_column("files_moved", server_default=None)


def downgrade() -> None:
    with op.batch_alter_table("messages") as batch:
        batch.drop_column("files_moved")
        batch.drop_column("files_created")
