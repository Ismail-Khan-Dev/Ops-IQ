"""Add server_credentials table for full credential rotation (week 9)

Revision ID: 0012
Revises: 0011
Create Date: 2026-08-18

Leads into the rotation ledger that backs zero-downtime server API-key
rotation: active keys authenticate, rotated (previous) keys are accepted only
within their grace window, and revoked keys are cut over immediately.
"""

from typing import Sequence, Union

import sqlalchemy as sa

from alembic import op

revision: str = "0012"
down_revision: Union[str, None] = "0011"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "server_credentials",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("key_hash", sa.String(), nullable=False),
        sa.Column("key_prefix", sa.String(), nullable=False),
        sa.Column("status", sa.String(), nullable=False, server_default="active"),
        sa.Column("valid_until", sa.DateTime(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.Column("rotated_at", sa.DateTime(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("key_hash"),
    )
    op.create_index("ix_server_credentials_key_hash", "server_credentials", ["key_hash"])
    op.create_index("ix_server_credentials_status", "server_credentials", ["status"])
    op.create_index(
        "ix_server_credentials_status_valid_until",
        "server_credentials",
        ["status", "valid_until"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_server_credentials_status_valid_until", table_name="server_credentials"
    )
    op.drop_index("ix_server_credentials_status", table_name="server_credentials")
    op.drop_index("ix_server_credentials_key_hash", table_name="server_credentials")
    op.drop_table("server_credentials")
