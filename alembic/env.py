"""Alembic environment configuration for async SQLAlchemy."""

import asyncio
import contextlib
import logging
from logging.config import fileConfig

from sqlalchemy import pool
from sqlalchemy.ext.asyncio import create_async_engine

from alembic import context
from ecommerce_ops.config import settings
from ecommerce_ops.models.db import Base

# Import audit model so Alembic registers it with Base.metadata.
with contextlib.suppress(ImportError):
    from ecommerce_ops.models.audit import AuditLog  # noqa: F401

# Import vector memory model — optional; only needed when pgvector is installed.
try:
    from ecommerce_ops.memory.vector.persistent_store import VectorMemory  # noqa: F401
except (ImportError, Exception) as exc:
    logging.getLogger("alembic.env").debug("VectorMemory import skipped: %s", exc)

config = context.config
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata


def run_migrations_offline() -> None:
    """Run migrations in 'offline' mode -- generate SQL script."""
    url = settings.DATABASE_URL
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()


def do_run_migrations(connection):
    context.configure(connection=connection, target_metadata=target_metadata)
    with context.begin_transaction():
        context.run_migrations()


async def run_async_migrations() -> None:
    """Run migrations in 'online' mode with async engine."""
    connectable = create_async_engine(settings.DATABASE_URL, poolclass=pool.NullPool)
    async with connectable.connect() as connection:
        await connection.run_sync(do_run_migrations)
    await connectable.dispose()


def run_migrations_online() -> None:
    """Run migrations in 'online' mode."""
    asyncio.run(run_async_migrations())


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
