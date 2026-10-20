"""Add key_hash_fast column for O(1) API key lookup (C10)

Revision ID: 0008
Revises: 0007
Create Date: 2026-08-18

Adds a sha256 ``key_hash_fast`` column to ``rbac_api_keys`` so that
``validate_api_key`` can do a single-row lookup via the unique index
instead of scanning every active row and running PBKDF2 on each.

Existing rows are backfilled in a single UPDATE; new and rotated keys
write both hashes atomically.
"""

from typing import Sequence, Union

import sqlalchemy as sa

from alembic import op

revision: str = "0008"
down_revision: Union[str, None] = "0007"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "rbac_api_keys",
        sa.Column("key_hash_fast", sa.String(), nullable=True),
    )
    op.create_index(
        "ix_rbac_api_keys_key_hash_fast",
        "rbac_api_keys",
        ["key_hash_fast"],
        unique=True,
    )


def downgrade() -> None:
    op.drop_index("ix_rbac_api_keys_key_hash_fast", table_name="rbac_api_keys")
    op.drop_column("rbac_api_keys", "key_hash_fast")
