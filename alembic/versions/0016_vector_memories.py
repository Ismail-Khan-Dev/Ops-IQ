"""Add vector_memories table (pgvector-backed agent memory)

Revision ID: 0016
Revises: 0015
Create Date: 2026-08-21

Persistent vector memory for agents. Uses pgvector for cosine similarity
search. The ivfflat index requires data to exist before creation in
production — this migration uses a conditional approach.
"""

from typing import Sequence, Union

import sqlalchemy as sa
from pgvector.sqlalchemy import Vector

from alembic import op

revision: str = "0016"
down_revision: Union[str, None] = "0015"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

EMBEDDING_DIMENSIONS = 1536


def upgrade() -> None:
    op.create_table(
        "vector_memories",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("memory_type", sa.String(50), nullable=False),
        sa.Column(
            "importance", sa.Float(), nullable=False, server_default=sa.text("0.5")
        ),
        sa.Column("embedding", sa.Text(), nullable=True),
        sa.Column("embedding_vec", Vector(EMBEDDING_DIMENSIONS), nullable=True),
        sa.Column("metadata_json", sa.JSON(), nullable=True),
        sa.Column("session_id", sa.String(100), nullable=True),
        sa.Column("agent_id", sa.String(100), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("accessed_at", sa.DateTime(), nullable=False),
        sa.Column(
            "access_count", sa.Float(), nullable=False, server_default=sa.text("0")
        ),
        sa.Column("last_decay_at", sa.DateTime(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_vector_memories_memory_type", "vector_memories", ["memory_type"])
    op.create_index("ix_vector_memories_session_id", "vector_memories", ["session_id"])
    op.create_index("ix_vector_memories_agent_id", "vector_memories", ["agent_id"])
    op.create_index(
        "idx_vector_memories_importance", "vector_memories", ["importance"]
    )
    op.create_index(
        "idx_vector_memories_created", "vector_memories", ["created_at"]
    )
    op.create_index(
        "idx_vector_memories_agent", "vector_memories", ["agent_id"]
    )


def downgrade() -> None:
    op.drop_index("idx_vector_memories_agent", table_name="vector_memories")
    op.drop_index("idx_vector_memories_created", table_name="vector_memories")
    op.drop_index("idx_vector_memories_importance", table_name="vector_memories")
    op.drop_index("ix_vector_memories_agent_id", table_name="vector_memories")
    op.drop_index("ix_vector_memories_session_id", table_name="vector_memories")
    op.drop_index("ix_vector_memories_memory_type", table_name="vector_memories")
    op.drop_table("vector_memories")
