"""Initial schema

Revision ID: 0001
Revises:
Create Date: 2026-05-25

"""

from typing import Sequence, Union

import sqlalchemy as sa

from alembic import op

revision: str = "0001"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "approval_actions",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("agent", sa.String(), nullable=False),
        sa.Column("action_type", sa.String(), nullable=False),
        sa.Column("status", sa.String(), nullable=False, server_default="pending"),
        sa.Column("risk_level", sa.String(), nullable=False, server_default="low"),
        sa.Column("confidence_score", sa.Float(), nullable=False, server_default="0.0"),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.Column("expires_at", sa.DateTime(), nullable=True),
        sa.Column("requires_hitl", sa.Boolean(), nullable=False, server_default="true"),
        sa.Column("shadow_mode", sa.Boolean(), nullable=False, server_default="true"),
        sa.Column("payload", sa.JSON(), nullable=False),
        sa.Column("evidence", sa.JSON(), nullable=False),
        sa.Column("impact", sa.JSON(), nullable=False),
        sa.Column("reviewed_by", sa.String(), nullable=True),
        sa.Column("reviewed_at", sa.DateTime(), nullable=True),
        sa.Column("rejection_reason", sa.String(), nullable=True),
        sa.Column("operator_notes", sa.String(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_approval_actions_status", "approval_actions", ["status"])
    op.create_index("ix_approval_actions_agent", "approval_actions", ["agent"])
    op.create_index("ix_approval_actions_risk_level", "approval_actions", ["risk_level"])

    op.create_table(
        "audit_entries",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("action_id", sa.String(), nullable=True),
        sa.Column("timestamp", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.Column("agent", sa.String(), nullable=False),
        sa.Column("action_type", sa.String(), nullable=False),
        sa.Column("decision", sa.String(), nullable=False),
        sa.Column("operator", sa.String(), nullable=True),
        sa.Column("confidence_score", sa.Float(), nullable=False, server_default="0.0"),
        sa.Column("financial_impact", sa.Float(), nullable=True),
        sa.Column("details", sa.JSON(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_audit_entries_agent", "audit_entries", ["agent"])
    op.create_index("ix_audit_entries_decision", "audit_entries", ["decision"])
    op.create_index("ix_audit_entries_timestamp", "audit_entries", ["timestamp"])

    op.create_table(
        "agent_status",
        sa.Column("agent_id", sa.String(), nullable=False),
        sa.Column("status", sa.String(), nullable=False, server_default="active"),
        sa.Column("streak", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("autonomy_level", sa.String(), nullable=False, server_default="shadow"),
        sa.Column("total_decisions", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("total_approvals", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("total_rejections", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("avg_confidence", sa.Float(), nullable=False, server_default="0.0"),
        sa.PrimaryKeyConstraint("agent_id"),
    )

    op.create_table(
        "store_settings",
        sa.Column("id", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("shadow_mode", sa.Boolean(), nullable=False, server_default="true"),
        sa.Column("fraud_threshold", sa.Integer(), nullable=False, server_default="70"),
        sa.Column("po_limit", sa.Float(), nullable=False, server_default="1000.0"),
        sa.Column("pricing_limit", sa.Float(), nullable=False, server_default="5.0"),
        sa.Column("reviews_rating_threshold", sa.Integer(), nullable=False, server_default="4"),
        sa.PrimaryKeyConstraint("id"),
    )


def downgrade() -> None:
    op.drop_table("store_settings")
    op.drop_table("agent_status")
    op.drop_table("audit_entries")
    op.drop_table("approval_actions")
