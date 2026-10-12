"""Run lifecycle under a supervisor: process identity, outcome, workers and artifacts.

Revision ID: 0004
Revises: 0003
Create Date: 2026-10-12
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0004"
down_revision = "0003"
branch_labels = None
depends_on = None

OLD_CLASSES = "'code_error', 'resource_limit', 'numerical_instability', 'infrastructure', 'unknown'"
NEW_CLASSES = (
    "'code_error', 'resource_limit', 'numerical_instability', 'data_problem', "
    "'infrastructure', 'unknown'"
)


def run_columns() -> list[sa.Column[object]]:
    return [
        sa.Column("correlation_id", sa.String(length=64), nullable=True),
        sa.Column("worker_id", sa.String(length=40), nullable=True),
        sa.Column("monitor_pid", sa.Integer(), nullable=True),
        sa.Column("monitor_started_at", sa.Float(), nullable=True),
        sa.Column("pid", sa.Integer(), nullable=True),
        sa.Column("process_started_at", sa.Float(), nullable=True),
        sa.Column("started_at", sa.String(length=27), nullable=True),
        sa.Column("finished_at", sa.String(length=27), nullable=True),
        sa.Column("heartbeat_at", sa.String(length=27), nullable=True),
        sa.Column("cancel_requested_at", sa.String(length=27), nullable=True),
        sa.Column("cancel_reason", sa.String(length=300), nullable=True),
        sa.Column("exit_code", sa.Integer(), nullable=True),
        sa.Column("exit_signal", sa.String(length=20), nullable=True),
        sa.Column("wall_seconds", sa.Float(), nullable=True),
        sa.Column("outcome", sa.JSON(), nullable=True),
        sa.Column("resources", sa.JSON(), nullable=True),
        sa.Column("ingest", sa.JSON(), nullable=True),
    ]


def upgrade() -> None:
    with op.batch_alter_table("runs") as batch:
        for column in run_columns():
            batch.add_column(column)
        batch.drop_constraint(batch.f("ck_runs_failure_class"), type_="check")
        batch.create_check_constraint(
            batch.f("ck_runs_failure_class"),
            f"failure_class IS NULL OR failure_class IN ({NEW_CLASSES})",
        )
        batch.create_index(batch.f("ix_runs_worker_id"), ["worker_id"], unique=False)

    op.create_table(
        "workers",
        sa.Column("id", sa.String(length=40), nullable=False),
        sa.Column("pid", sa.Integer(), nullable=False),
        sa.Column("hostname", sa.String(length=255), nullable=False),
        sa.Column("version", sa.String(length=40), nullable=False),
        sa.Column("max_parallel_runs", sa.Integer(), nullable=False),
        sa.Column("started_at", sa.String(length=27), nullable=False),
        sa.Column("heartbeat_at", sa.String(length=27), nullable=False),
        sa.Column("stopped_at", sa.String(length=27), nullable=True),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_workers")),
    )

    op.create_table(
        "artifacts",
        sa.Column("id", sa.String(length=40), nullable=False),
        sa.Column("project_id", sa.String(length=40), nullable=False),
        sa.Column("run_id", sa.String(length=40), nullable=False),
        sa.Column("kind", sa.String(length=40), nullable=False),
        sa.Column("name", sa.String(length=1000), nullable=False),
        sa.Column("media_type", sa.String(length=100), nullable=False),
        sa.Column("size_bytes", sa.Integer(), nullable=False),
        sa.Column("sha256", sa.String(length=64), nullable=True),
        sa.Column("created_at", sa.String(length=27), nullable=False),
        sa.ForeignKeyConstraint(
            ["project_id"], ["projects.id"], name=op.f("fk_artifacts_project_id_projects")
        ),
        sa.ForeignKeyConstraint(["run_id"], ["runs.id"], name=op.f("fk_artifacts_run_id_runs")),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_artifacts")),
        sa.UniqueConstraint("run_id", "name", name="uq_artifacts_run_name"),
    )


def downgrade() -> None:
    op.drop_table("artifacts")
    op.drop_table("workers")
    with op.batch_alter_table("runs") as batch:
        batch.drop_index(batch.f("ix_runs_worker_id"))
        batch.drop_constraint(batch.f("ck_runs_failure_class"), type_="check")
        batch.create_check_constraint(
            batch.f("ck_runs_failure_class"),
            f"failure_class IS NULL OR failure_class IN ({OLD_CLASSES})",
        )
        for column in reversed(run_columns()):
            batch.drop_column(column.name)
