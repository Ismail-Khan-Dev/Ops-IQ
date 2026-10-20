"""Add outbound_webhooks table (custom HTTPS endpoints)

Revision ID: 0014
Revises: 0013
Create Date: 2026-08-18

Backs the outbound notification integration layer: HTTPS endpoints that
receive signed event payloads (HITL requests, failures, graduations, daily
summaries). Each row stores the endpoint URL, an optional HMAC signing
secret, and the JSON list of event types to receive.
"""

from typing import Sequence, Union

import sqlalchemy as sa

from alembic import op

revision: str = "0014"
down_revision: Union[str, None] = "0013"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "outbound_webhooks",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("name", sa.String(), nullable=False),
        sa.Column("url", sa.String(), nullable=False),
        sa.Column("secret", sa.String(), nullable=True),
        sa.Column("events", sa.JSON(), nullable=False),
        sa.Column("enabled", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column(
            "created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()
        ),
        sa.Column(
            "updated_at", sa.DateTime(), nullable=False, server_default=sa.func.now()
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("name"),
    )
    op.create_index("ix_outbound_webhooks_name", "outbound_webhooks", ["name"])


def downgrade() -> None:
    op.drop_index("ix_outbound_webhooks_name", table_name="outbound_webhooks")
    op.drop_table("outbound_webhooks")
