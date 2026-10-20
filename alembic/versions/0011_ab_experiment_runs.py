"""Add ab_experiment_runs table for shadow-mode A/B testing (week 8)

Revision ID: 0011
Revises: 0010
Create Date: 2026-08-18

Records shadow-mode A/B comparisons between the production agent decision
(variant A) and a configured baseline strategy (variant B).  Nothing is
executed in shadow mode; the table captures which strategy would have scored
higher and the divergence between them so better baselines can be promoted
without touching live traffic.
"""

from typing import Sequence, Union

import sqlalchemy as sa

from alembic import op

revision: str = "0011"
down_revision: Union[str, None] = "0010"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "ab_experiment_runs",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("run_id", sa.String(), nullable=False),
        sa.Column("agent_name", sa.String(), nullable=False),
        sa.Column("action_type", sa.String(), nullable=False),
        sa.Column("variant_a_score", sa.Float(), nullable=False),
        sa.Column("variant_b_score", sa.Float(), nullable=False),
        sa.Column("divergence", sa.Float(), nullable=False),
        sa.Column("winner", sa.String(), nullable=False),
        sa.Column("baseline_params", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_ab_experiment_runs_agent_name", "ab_experiment_runs", ["agent_name"])
    op.create_index("ix_ab_experiment_runs_run_id", "ab_experiment_runs", ["run_id"])
    op.create_index("ix_ab_experiment_runs_winner", "ab_experiment_runs", ["winner"])
    op.create_index(
        "ix_ab_experiment_runs_agent_created", "ab_experiment_runs", ["agent_name", "created_at"]
    )


def downgrade() -> None:
    op.drop_index(
        "ix_ab_experiment_runs_agent_created", table_name="ab_experiment_runs"
    )
    op.drop_index("ix_ab_experiment_runs_winner", table_name="ab_experiment_runs")
    op.drop_index("ix_ab_experiment_runs_run_id", table_name="ab_experiment_runs")
    op.drop_index("ix_ab_experiment_runs_agent_name", table_name="ab_experiment_runs")
    op.drop_table("ab_experiment_runs")
