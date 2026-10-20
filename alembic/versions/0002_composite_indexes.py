"""Add composite indexes for query performance and action_type index

Revision ID: 0002
Revises: 0001
Create Date: 2026-06-26
"""
from typing import Sequence, Union

from alembic import op

revision: str = "0002"
down_revision: Union[str, None] = "0001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Composite indexes for approval_actions queries
    op.create_index(
        "ix_approval_actions_agent_status",
        "approval_actions",
        ["agent", "status"],
    )
    op.create_index(
        "ix_approval_actions_agent_risk_status",
        "approval_actions",
        ["agent", "risk_level", "status"],
    )
    op.create_index(
        "ix_approval_actions_created_at",
        "approval_actions",
        ["created_at"],
    )

    # Composite indexes for audit_entries
    op.create_index(
        "ix_audit_entries_agent_decision",
        "audit_entries",
        ["agent", "decision"],
    )
    op.create_index(
        "ix_audit_entries_agent_action_type",
        "audit_entries",
        ["agent", "action_type"],
    )
    op.create_index(
        "ix_audit_entries_action_type",
        "audit_entries",
        ["action_type"],
    )

    # Agent status index for dashboard queries
    op.create_index(
        "ix_agent_status_autonomy_level",
        "agent_status",
        ["autonomy_level"],
    )


def downgrade() -> None:
    op.drop_index("ix_agent_status_autonomy_level")
    op.drop_index("ix_audit_entries_action_type")
    op.drop_index("ix_audit_entries_agent_action_type")
    op.drop_index("ix_audit_entries_agent_decision")
    op.drop_index("ix_approval_actions_created_at")
    op.drop_index("ix_approval_actions_agent_risk_status")
    op.drop_index("ix_approval_actions_agent_status")
