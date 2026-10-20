"""Add Shopify synced-data snapshot tables (Phase 3 — sync persistence)

Revision ID: 0010
Revises: 0009
Create Date: 2026-08-18

The /shopify/sync endpoint pulls products, orders, and customers from
Shopify. These tables persist the actually-synced data (key columns plus
the full raw payload) so the endpoint's reported counts reflect real
writes instead of being silent no-ops.
"""

from typing import Sequence, Union

import sqlalchemy as sa

from alembic import op

revision: str = "0010"
down_revision: Union[str, None] = "0009"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "shopify_product_snapshots",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("shopify_product_id", sa.String(), nullable=False),
        sa.Column("shop_domain", sa.String(), nullable=False),
        sa.Column("title", sa.String(), nullable=True),
        sa.Column("sku", sa.String(), nullable=True),
        sa.Column("min_price", sa.Float(), nullable=False, server_default="0.0"),
        sa.Column("max_price", sa.Float(), nullable=False, server_default="0.0"),
        sa.Column("total_inventory", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("raw_data", sa.JSON(), nullable=False),
        sa.Column("synced_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("shop_domain", "shopify_product_id"),
    )
    op.create_index("ix_shopify_product_snapshots_shop_product", "shopify_product_snapshots", ["shop_domain", "shopify_product_id"])
    op.create_index("ix_shopify_product_snapshots_shopify_product_id", "shopify_product_snapshots", ["shopify_product_id"])
    op.create_index("ix_shopify_product_snapshots_sku", "shopify_product_snapshots", ["sku"])
    op.create_index("ix_shopify_product_snapshots_shop_domain", "shopify_product_snapshots", ["shop_domain"])

    op.create_table(
        "shopify_order_snapshots",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("shopify_order_id", sa.String(), nullable=False),
        sa.Column("shop_domain", sa.String(), nullable=False),
        sa.Column("order_number", sa.Integer(), nullable=True),
        sa.Column("total_price", sa.Float(), nullable=False, server_default="0.0"),
        sa.Column("currency", sa.String(), nullable=True),
        sa.Column("financial_status", sa.String(), nullable=True),
        sa.Column("fulfillment_status", sa.String(), nullable=True),
        sa.Column("raw_data", sa.JSON(), nullable=False),
        sa.Column("synced_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("shop_domain", "shopify_order_id"),
    )
    op.create_index("ix_shopify_order_snapshots_shop_order", "shopify_order_snapshots", ["shop_domain", "shopify_order_id"])
    op.create_index("ix_shopify_order_snapshots_shopify_order_id", "shopify_order_snapshots", ["shopify_order_id"])
    op.create_index("ix_shopify_order_snapshots_shop_domain", "shopify_order_snapshots", ["shop_domain"])

    op.create_table(
        "shopify_customer_snapshots",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("shopify_customer_id", sa.String(), nullable=False),
        sa.Column("shop_domain", sa.String(), nullable=False),
        sa.Column("email", sa.String(), nullable=True),
        sa.Column("first_name", sa.String(), nullable=True),
        sa.Column("last_name", sa.String(), nullable=True),
        sa.Column("orders_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("total_spent", sa.Float(), nullable=False, server_default="0.0"),
        sa.Column("raw_data", sa.JSON(), nullable=False),
        sa.Column("synced_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("shop_domain", "shopify_customer_id"),
    )
    op.create_index("ix_shopify_customer_snapshots_shop_customer", "shopify_customer_snapshots", ["shop_domain", "shopify_customer_id"])
    op.create_index("ix_shopify_customer_snapshots_shopify_customer_id", "shopify_customer_snapshots", ["shopify_customer_id"])
    op.create_index("ix_shopify_customer_snapshots_shop_domain", "shopify_customer_snapshots", ["shop_domain"])


def downgrade() -> None:
    op.drop_index("ix_shopify_customer_snapshots_shop_domain", table_name="shopify_customer_snapshots")
    op.drop_index("ix_shopify_customer_snapshots_shopify_customer_id", table_name="shopify_customer_snapshots")
    op.drop_index("ix_shopify_customer_snapshots_shop_customer", table_name="shopify_customer_snapshots")
    op.drop_table("shopify_customer_snapshots")

    op.drop_index("ix_shopify_order_snapshots_shop_domain", table_name="shopify_order_snapshots")
    op.drop_index("ix_shopify_order_snapshots_shopify_order_id", table_name="shopify_order_snapshots")
    op.drop_index("ix_shopify_order_snapshots_shop_order", table_name="shopify_order_snapshots")
    op.drop_table("shopify_order_snapshots")

    op.drop_index("ix_shopify_product_snapshots_shop_domain", table_name="shopify_product_snapshots")
    op.drop_index("ix_shopify_product_snapshots_sku", table_name="shopify_product_snapshots")
    op.drop_index("ix_shopify_product_snapshots_shopify_product_id", table_name="shopify_product_snapshots")
    op.drop_index("ix_shopify_product_snapshots_shop_product", table_name="shopify_product_snapshots")
    op.drop_table("shopify_product_snapshots")
