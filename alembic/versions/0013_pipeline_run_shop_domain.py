"""Add shop_domain column to pipeline_runs (multi-store support)

Revision ID: 0013
Revises: 0012
Create Date: 2026-08-18

Lets a single pipeline run be scoped to a specific installed Shopify store
rather than always the env-configured default store. NULL keeps the legacy
behavior (default store / mock data).
"""

from typing import Sequence, Union

import sqlalchemy as sa

from alembic import op

revision: str = "0013"
down_revision: Union[str, None] = "0012"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("pipeline_runs", sa.Column("shop_domain", sa.String(), nullable=True))
    op.create_index("ix_pipeline_runs_shop_domain", "pipeline_runs", ["shop_domain"])


def downgrade() -> None:
    op.drop_index("ix_pipeline_runs_shop_domain", table_name="pipeline_runs")
    op.drop_column("pipeline_runs", "shop_domain")
