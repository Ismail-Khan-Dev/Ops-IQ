"""Add outbox_messages table for transactional action dispatch (C5)

Revision ID: 0007
Revises: 0006
Create Date: 2026-08-18

Transactional outbox guarantees at-least-once delivery of pipeline actions
to Shopify.  Before a live API call the action row is written with status
``pending``; on success it moves to ``sent``.  A background poller retries
stuck ``pending`` rows.  Idempotency is enforced downstream by the
``pipeline_runs`` table (C4).
"""

from typing import Sequence, Union

import sqlalchemy as sa

from alembic import op

revision: str = "0007"
down_revision: Union[str, None] = "0006"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "outbox_messages",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("action_id", sa.String(), nullable=False),
        sa.Column("status", sa.String(), nullable=False, server_default="pending"),
        sa.Column("payload", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.Column("sent_at", sa.DateTime(), nullable=True),
        sa.Column("error", sa.String(), nullable=True),
        sa.Column("retry_count", sa.Integer(), nullable=False, server_default="0"),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(["action_id"], ["approval_actions.id"]),
    )
    op.create_index("ix_outbox_messages_action_id", "outbox_messages", ["action_id"])
    op.create_index("ix_outbox_messages_status", "outbox_messages", ["status"])
    op.create_index("ix_outbox_messages_created_at", "outbox_messages", ["created_at"])


def downgrade() -> None:
    op.drop_index("ix_outbox_messages_created_at", table_name="outbox_messages")
    op.drop_index("ix_outbox_messages_status", table_name="outbox_messages")
    op.drop_index("ix_outbox_messages_action_id", table_name="outbox_messages")
    op.drop_table("outbox_messages")
