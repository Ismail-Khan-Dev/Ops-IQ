"""Add pgvector column and index to vector_memories

Revision ID: 0005
Revises: 0004
Create Date: 2026-08-16

Enables production-grade similarity search for the RAG memory store:

- PostgreSQL: creates the ``vector`` extension (if missing), ensures the
  ``vector_memories`` table exists, adds a real ``embedding_vec vector(1536)``
  column, backfills it from the legacy JSON ``embedding`` text column, and
  creates an IVFFlat index for Approximate Nearest Neighbor search.
- SQLite (test/throwaway DBs): mirrors ``embedding_vec`` as TEXT so the ORM
  model and schema stay in sync without requiring the extension.

The migration is defensive: it inspects the live schema and only creates the
table / column / index when missing, so it is safe to run against existing
deployments regardless of how ``vector_memories`` was previously provisioned.
"""

from __future__ import annotations

import contextlib
from typing import Sequence, Union

import sqlalchemy as sa

from alembic import op

revision: str = "0005"
down_revision: Union[str, None] = "0004"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_EMBEDDING_DIM = 1536
_VECTOR_INDEX = "ix_vector_memories_embedding_vec"
_LEGACY_INDEXES = [
    "idx_vector_memories_importance",
    "idx_vector_memories_created",
    "idx_vector_memories_agent",
]


def _is_postgres() -> bool:
    return op.get_bind().dialect.name == "postgresql"


def _table_names() -> set[str]:
    inspector = sa.inspect(op.get_bind())
    return set(inspector.get_table_names())


def _column_names(table: str) -> set[str]:
    inspector = sa.inspect(op.get_bind())
    return {c["name"] for c in inspector.get_columns(table)}


def _index_names(table: str) -> set[str]:
    inspector = sa.inspect(op.get_bind())
    return {i["name"] for i in inspector.get_indexes(table)}


def _create_table_from_model(table_name: str) -> None:
    """Create the table using ORM metadata so DDL matches the model per dialect."""
    import ecommerce_ops.memory.vector.persistent_store as vector_store

    table = sa.Table(table_name, vector_store.VectorMemory.metadata)
    table.create(bind=op.get_bind(), checkfirst=True)


def upgrade() -> None:
    if _is_postgres():
        op.execute("CREATE EXTENSION IF NOT EXISTS vector")

    tables = _table_names()

    if "vector_memories" not in tables:
        _create_table_from_model("vector_memories")
        return

    columns = _column_names("vector_memories")

    if "embedding_vec" not in columns:
        if _is_postgres():
            op.execute(
                sa.text(
                    f"ALTER TABLE vector_memories ADD COLUMN embedding_vec VECTOR({_EMBEDDING_DIM})"
                )
            )
            op.execute(
                sa.text(
                    "UPDATE vector_memories SET embedding_vec = embedding::vector "
                    "WHERE embedding IS NOT NULL"
                )
            )
        else:
            op.add_column(
                "vector_memories",
                sa.Column("embedding_vec", sa.Text(), nullable=True),
            )

    if _is_postgres():
        if _VECTOR_INDEX not in _index_names("vector_memories"):
            op.execute(
                sa.text(
                    f"CREATE INDEX {_VECTOR_INDEX} ON vector_memories "
                    "USING ivfflat (embedding_vec vector_cosine_ops)"
                )
            )
    else:
        if _VECTOR_INDEX not in _index_names("vector_memories"):
            op.create_index(_VECTOR_INDEX, "vector_memories", ["embedding_vec"])


def downgrade() -> None:
    if "vector_memories" not in _table_names():
        return
    if _VECTOR_INDEX in _index_names("vector_memories"):
        if _is_postgres():
            op.execute(sa.text(f"DROP INDEX {_VECTOR_INDEX}"))
        else:
            op.drop_index(_VECTOR_INDEX, table_name="vector_memories")
    if "embedding_vec" in _column_names("vector_memories"):
        op.drop_column("vector_memories", "embedding_vec")
    for idx in _LEGACY_INDEXES:
        if idx in _index_names("vector_memories"):
            with contextlib.suppress(Exception):
                op.drop_index(idx, table_name="vector_memories")
    if "vector_memories" in _table_names():
        op.drop_table("vector_memories")
