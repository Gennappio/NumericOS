"""Hypotheses, experiments and runs; events can be correlated with a run.

Revision ID: 0002
Revises: 0001
Create Date: 2026-10-12
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None

EPISTEMIC = "'proposed', 'supported', 'contradicted', 'inconclusive'"
RUN_STATUSES = (
    "'queued', 'starting', 'running', 'succeeded', 'failed', 'cancelled', 'timed_out', 'lost'"
)
FAILURE_CLASSES = (
    "'code_error', 'resource_limit', 'numerical_instability', 'infrastructure', 'unknown'"
)


def upgrade() -> None:
    op.create_table(
        "hypotheses",
        sa.Column("id", sa.String(length=40), nullable=False),
        sa.Column("project_id", sa.String(length=40), nullable=False),
        sa.Column("title", sa.String(length=300), nullable=False),
        sa.Column("claim", sa.Text(), nullable=False),
        sa.Column("rationale", sa.Text(), nullable=False),
        sa.Column("prediction", sa.Text(), nullable=False),
        sa.Column("falsification", sa.JSON(), nullable=False),
        sa.Column("assumptions", sa.JSON(), nullable=False),
        sa.Column("epistemic_status", sa.String(length=20), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.String(length=27), nullable=False),
        sa.Column("updated_at", sa.String(length=27), nullable=False),
        sa.CheckConstraint(
            f"epistemic_status IN ({EPISTEMIC})", name=op.f("ck_hypotheses_epistemic_status")
        ),
        sa.CheckConstraint(
            "length(title) BETWEEN 1 AND 300", name=op.f("ck_hypotheses_title_length")
        ),
        sa.ForeignKeyConstraint(
            ["project_id"],
            ["projects.id"],
            name=op.f("fk_hypotheses_project_id_projects"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_hypotheses")),
    )
    op.create_index(
        "ix_hypotheses_project_created", "hypotheses", ["project_id", "created_at"], unique=False
    )

    op.create_table(
        "experiments",
        sa.Column("id", sa.String(length=40), nullable=False),
        sa.Column("project_id", sa.String(length=40), nullable=False),
        sa.Column("hypothesis_id", sa.String(length=40), nullable=True),
        sa.Column("name", sa.String(length=300), nullable=False),
        sa.Column("protocol", sa.JSON(), nullable=False),
        sa.Column("protocol_digest", sa.String(length=64), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.String(length=27), nullable=False),
        sa.Column("updated_at", sa.String(length=27), nullable=False),
        sa.CheckConstraint(
            "length(name) BETWEEN 1 AND 300", name=op.f("ck_experiments_name_length")
        ),
        sa.ForeignKeyConstraint(
            ["hypothesis_id"],
            ["hypotheses.id"],
            name=op.f("fk_experiments_hypothesis_id_hypotheses"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["project_id"],
            ["projects.id"],
            name=op.f("fk_experiments_project_id_projects"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_experiments")),
    )
    op.create_index(
        op.f("ix_experiments_hypothesis_id"), "experiments", ["hypothesis_id"], unique=False
    )
    op.create_index(
        "ix_experiments_project_created", "experiments", ["project_id", "created_at"], unique=False
    )

    op.create_table(
        "runs",
        sa.Column("id", sa.String(length=40), nullable=False),
        sa.Column("project_id", sa.String(length=40), nullable=False),
        sa.Column("experiment_id", sa.String(length=40), nullable=False),
        sa.Column("label", sa.String(length=200), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("status_reason", sa.String(length=300), nullable=True),
        sa.Column("failure_class", sa.String(length=30), nullable=True),
        sa.Column("parameters", sa.JSON(), nullable=False),
        sa.Column("seed", sa.Integer(), nullable=True),
        sa.Column("argv", sa.JSON(), nullable=False),
        sa.Column("protocol_digest", sa.String(length=64), nullable=False),
        sa.Column("idempotency_key", sa.String(length=128), nullable=True),
        sa.Column("request_digest", sa.String(length=64), nullable=True),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.String(length=27), nullable=False),
        sa.Column("updated_at", sa.String(length=27), nullable=False),
        sa.CheckConstraint(f"status IN ({RUN_STATUSES})", name=op.f("ck_runs_status")),
        sa.CheckConstraint(
            f"failure_class IS NULL OR failure_class IN ({FAILURE_CLASSES})",
            name=op.f("ck_runs_failure_class"),
        ),
        sa.ForeignKeyConstraint(
            ["experiment_id"],
            ["experiments.id"],
            name=op.f("fk_runs_experiment_id_experiments"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["project_id"],
            ["projects.id"],
            name=op.f("fk_runs_project_id_projects"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_runs")),
        sa.UniqueConstraint(
            "experiment_id", "idempotency_key", name="uq_runs_experiment_idempotency_key"
        ),
    )
    op.create_index(
        "ix_runs_experiment_created", "runs", ["experiment_id", "created_at"], unique=False
    )
    op.create_index("ix_runs_status", "runs", ["status"], unique=False)

    with op.batch_alter_table("events") as batch:
        batch.add_column(sa.Column("run_id", sa.String(length=40), nullable=True))
        batch.create_index(batch.f("ix_events_run_id"), ["run_id"], unique=False)


def downgrade() -> None:
    with op.batch_alter_table("events") as batch:
        batch.drop_index(batch.f("ix_events_run_id"))
        batch.drop_column("run_id")
    op.drop_index("ix_runs_status", table_name="runs")
    op.drop_index("ix_runs_experiment_created", table_name="runs")
    op.drop_table("runs")
    op.drop_index("ix_experiments_project_created", table_name="experiments")
    op.drop_index(op.f("ix_experiments_hypothesis_id"), table_name="experiments")
    op.drop_table("experiments")
    op.drop_index("ix_hypotheses_project_created", table_name="hypotheses")
    op.drop_table("hypotheses")
