"""Add pipeline_runs idempotency table (C4)

Revision ID: 0006
Revises: 0005
Create Date: 2026-08-18

Deduplicates concurrent pipeline runs by enforcing a unique constraint on
``run_id``.  ``INSERT … ON CONFLICT DO NOTHING`` in ``run_pipeline_task``
guarantees at-most-once execution; the row status tracks lifecycle
(pending → running → completed | failed).
"""

from typing import Sequence, Union

import sqlalchemy as sa

from alembic import op

revision: str = "0006"
down_revision: Union[str, None] = "0005"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "pipeline_runs",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("run_id", sa.String(), nullable=False),
        sa.Column("status", sa.String(), nullable=False, server_default="pending"),
        sa.Column("data_source", sa.String(), nullable=True),
        sa.Column("decisions_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("actions_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("evaluation_avg_score", sa.Float(), nullable=True),
        sa.Column("evaluation_pass_rate", sa.Float(), nullable=True),
        sa.Column("error", sa.String(), nullable=True),
        sa.Column("started_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.Column("finished_at", sa.DateTime(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("run_id"),
    )
    op.create_index("ix_pipeline_runs_run_id", "pipeline_runs", ["run_id"])
    op.create_index("ix_pipeline_runs_status", "pipeline_runs", ["status"])
    op.create_index("ix_pipeline_runs_started_at", "pipeline_runs", ["started_at"])


def downgrade() -> None:
    op.drop_index("ix_pipeline_runs_started_at", table_name="pipeline_runs")
    op.drop_index("ix_pipeline_runs_status", table_name="pipeline_runs")
    op.drop_index("ix_pipeline_runs_run_id", table_name="pipeline_runs")
    op.drop_table("pipeline_runs")
