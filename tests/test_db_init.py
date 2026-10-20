"""Schema-creation policy tests: ORM create_all must never run on
Alembic-managed (PostgreSQL) databases to avoid schema drift."""

import pytest

from ecommerce_ops.models import db as dbmod


def _patch_managed(monkeypatch, is_sqlite: bool) -> None:
    monkeypatch.delenv("AUTO_CREATE_SCHEMA", raising=False)
    monkeypatch.setattr(dbmod, "is_sqlite", is_sqlite)


def test_auto_create_schema_skipped_for_postgres(monkeypatch):
    _patch_managed(monkeypatch, is_sqlite=False)
    assert dbmod._auto_create_schema() is False


def test_auto_create_schema_allowed_for_sqlite(monkeypatch):
    _patch_managed(monkeypatch, is_sqlite=True)
    assert dbmod._auto_create_schema() is True


def test_auto_create_schema_explicitly_forced(monkeypatch):
    monkeypatch.setattr(dbmod, "is_sqlite", False)
    monkeypatch.setenv("AUTO_CREATE_SCHEMA", "true")
    assert dbmod._auto_create_schema() is True


@pytest.mark.asyncio
async def test_init_db_skips_create_all_for_managed_db(monkeypatch):
    """On a non-SQLite (Alembic-managed) database, init_db must not run
    Base.metadata.create_all — seeding still happens against existing tables."""
    _patch_managed(monkeypatch, is_sqlite=False)

    captured = {"called": False}

    def spy_create_all(bind, *args, **kwargs):
        captured["called"] = True

    monkeypatch.setattr(dbmod.Base.metadata, "create_all", spy_create_all)

    await dbmod.init_db()

    assert captured["called"] is False


@pytest.mark.asyncio
async def test_init_db_runs_create_all_for_unmanaged_db(monkeypatch):
    """On SQLite (no Alembic baseline) init_db keeps auto-creating tables."""
    _patch_managed(monkeypatch, is_sqlite=True)

    captured = {"called": False}

    def spy_create_all(bind, *args, **kwargs):
        captured["called"] = True

    monkeypatch.setattr(dbmod.Base.metadata, "create_all", spy_create_all)

    await dbmod.init_db()

    assert captured["called"] is True
