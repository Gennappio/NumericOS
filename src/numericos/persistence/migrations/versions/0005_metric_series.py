"""Scientific metrics of runs: one summary row per run and metric.

Revision ID: 0005
Revises: 0004
Create Date: 2026-10-12
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0005"
down_revision = "0004"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("runs") as batch:
        batch.add_column(sa.Column("metric_report", sa.JSON(), nullable=True))

    op.create_table(
        "metric_series",
        sa.Column("id", sa.String(length=40), nullable=False),
        sa.Column("project_id", sa.String(length=40), nullable=False),
        sa.Column("experiment_id", sa.String(length=40), nullable=False),
        sa.Column("run_id", sa.String(length=40), nullable=False),
        sa.Column("name", sa.String(length=100), nullable=False),
        sa.Column("unit", sa.String(length=60), nullable=False),
        sa.Column("source", sa.String(length=20), nullable=False),
        sa.Column("declared", sa.Boolean(), nullable=False),
        sa.Column("samples", sa.Integer(), nullable=False),
        sa.Column("non_finite", sa.Integer(), nullable=False),
        sa.Column("stored", sa.Integer(), nullable=False),
        sa.Column("first_value", sa.Float(), nullable=True),
        sa.Column("first_step", sa.Integer(), nullable=True),
        sa.Column("last_value", sa.Float(), nullable=True),
        sa.Column("last_non_finite", sa.String(length=4), nullable=True),
        sa.Column("last_step", sa.Integer(), nullable=True),
        sa.Column("last_time", sa.Float(), nullable=True),
        sa.Column("last_at", sa.Float(), nullable=True),
        sa.Column("min_value", sa.Float(), nullable=True),
        sa.Column("max_value", sa.Float(), nullable=True),
        sa.Column("updated_at", sa.String(length=27), nullable=False),
        sa.CheckConstraint(
            "source IN ('instrumentation', 'parser', 'supervisor')",
            name=op.f("ck_metric_series_source"),
        ),
        sa.ForeignKeyConstraint(
            ["experiment_id"],
            ["experiments.id"],
            name=op.f("fk_metric_series_experiment_id_experiments"),
        ),
        sa.ForeignKeyConstraint(
            ["project_id"], ["projects.id"], name=op.f("fk_metric_series_project_id_projects")
        ),
        sa.ForeignKeyConstraint(["run_id"], ["runs.id"], name=op.f("fk_metric_series_run_id_runs")),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_metric_series")),
        sa.UniqueConstraint("run_id", "name", name="uq_metric_series_run_name"),
    )
    op.create_index(
        "ix_metric_series_experiment_name", "metric_series", ["experiment_id", "name"], unique=False
    )


def downgrade() -> None:
    op.drop_index("ix_metric_series_experiment_name", table_name="metric_series")
    op.drop_table("metric_series")
    with op.batch_alter_table("runs") as batch:
        batch.drop_column("metric_report")
