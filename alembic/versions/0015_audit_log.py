"""Add audit_log table (immutable compliance audit trail)

Revision ID: 0015
Revises: 0014
Create Date: 2026-08-21

Append-only compliance table. All columns are NOT NULL with safe defaults
so historical data can be backfilled without breaking the schema.
"""

from typing import Sequence, Union

import sqlalchemy as sa

from alembic import op

revision: str = "0015"
down_revision: Union[str, None] = "0014"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "audit_log",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("timestamp", sa.DateTime(), nullable=False),
        sa.Column("actor", sa.String(), nullable=False),
        sa.Column("actor_role", sa.String(), nullable=False, server_default="unknown"),
        sa.Column("action", sa.String(), nullable=False),
        sa.Column("resource_type", sa.String(), nullable=False),
        sa.Column("resource_id", sa.String(), nullable=False, server_default=""),
        sa.Column("outcome", sa.String(), nullable=False, server_default="success"),
        sa.Column("risk_level", sa.String(), nullable=False, server_default="low"),
        sa.Column(
            "confidence_score", sa.Float(), nullable=False, server_default=sa.text("0.0")
        ),
        sa.Column("details", sa.Text(), nullable=False, server_default="{}"),
        sa.Column("ip_address", sa.String(), nullable=False, server_default=""),
        sa.Column("user_agent", sa.String(), nullable=False, server_default=""),
        sa.Column("session_id", sa.String(), nullable=False, server_default=""),
        sa.Column("request_id", sa.String(), nullable=False, server_default=""),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_audit_log_timestamp", "audit_log", ["timestamp"])
    op.create_index("ix_audit_log_actor", "audit_log", ["actor"])
    op.create_index("ix_audit_log_action", "audit_log", ["action"])
    op.create_index("ix_audit_log_resource_type", "audit_log", ["resource_type"])


def downgrade() -> None:
    op.drop_index("ix_audit_log_resource_type", table_name="audit_log")
    op.drop_index("ix_audit_log_action", table_name="audit_log")
    op.drop_index("ix_audit_log_actor", table_name="audit_log")
    op.drop_index("ix_audit_log_timestamp", table_name="audit_log")
    op.drop_table("audit_log")
