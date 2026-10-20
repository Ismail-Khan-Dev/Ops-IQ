"""Add persistent Shopify webhook events table

Revision ID: 0004
Revises: 0003
Create Date: 2026-08-16

Adds a durable inbox for Shopify webhook events so handlers can persist
every verified webhook payload instead of discarding it after dispatch.
Used by the order / product / customer / inventory handlers for at-least-once
processing and replayability.

Revision script for 0004_rbac_tables.py added via autogenerate-style
manual authoring. 0003_rbac_tables.py created 2026-08-15.
"""

from typing import Sequence, Union

import sqlalchemy as sa

from alembic import op

revision: str = "0004"
down_revision: Union[str, None] = "0003"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "shopify_webhook_events",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("topic", sa.String(), nullable=False),
        sa.Column("shop_domain", sa.String(), nullable=False),
        sa.Column("api_version", sa.String(), nullable=True),
        sa.Column("event_id", sa.String(), nullable=True),
        sa.Column("received_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.Column("processed", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("error", sa.String(), nullable=True),
        sa.Column("payload", sa.JSON(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_shopify_webhook_events_topic", "shopify_webhook_events", ["topic"])
    op.create_index("ix_shopify_webhook_events_shop_domain", "shopify_webhook_events", ["shop_domain"])
    op.create_index("ix_shopify_webhook_events_event_id", "shopify_webhook_events", ["event_id"])
    op.create_index("ix_shopify_webhook_events_received_at", "shopify_webhook_events", ["received_at"])
    op.create_index(
        "ix_shopify_webhook_events_topic_time", "shopify_webhook_events", ["topic", "received_at"]
    )
    op.create_index(
        "ix_shopify_webhook_events_shop_time", "shopify_webhook_events", ["shop_domain", "received_at"]
    )


def downgrade() -> None:
    op.drop_index("ix_shopify_webhook_events_shop_time", table_name="shopify_webhook_events")
    op.drop_index("ix_shopify_webhook_events_topic_time", table_name="shopify_webhook_events")
    op.drop_index("ix_shopify_webhook_events_received_at", table_name="shopify_webhook_events")
    op.drop_index("ix_shopify_webhook_events_event_id", table_name="shopify_webhook_events")
    op.drop_index("ix_shopify_webhook_events_shop_domain", table_name="shopify_webhook_events")
    op.drop_index("ix_shopify_webhook_events_topic", table_name="shopify_webhook_events")
    op.drop_table("shopify_webhook_events")
