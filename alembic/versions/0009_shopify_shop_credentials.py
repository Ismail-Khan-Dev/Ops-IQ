"""Add shopify_shop_credentials table for persisted OAuth tokens (C9)

Revision ID: 0009
Revises: 0008
Create Date: 2026-08-18

After a merchant completes the OAuth install flow, the access token is
written to this table so it survives server restarts.  ``shop_domain``
is the unique lookup key.
"""

from typing import Sequence, Union

import sqlalchemy as sa

from alembic import op

revision: str = "0009"
down_revision: Union[str, None] = "0008"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "shopify_shop_credentials",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("shop_domain", sa.String(), nullable=False),
        sa.Column("access_token", sa.String(), nullable=False),
        sa.Column("scope", sa.String(), nullable=True),
        sa.Column("installed_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default="true"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("shop_domain"),
    )
    op.create_index(
        "ix_shopify_shop_credentials_shop_domain",
        "shopify_shop_credentials",
        ["shop_domain"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_shopify_shop_credentials_shop_domain",
        table_name="shopify_shop_credentials",
    )
    op.drop_table("shopify_shop_credentials")
