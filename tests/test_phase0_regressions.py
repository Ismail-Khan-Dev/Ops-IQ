"""Phase 0 regression tests.

Pins the Critical-tier fixes from the production-readiness audit:

- C1: ``app._pipeline_task_handler`` must not crash. It previously used
  ``async with get_db_session()`` on an async *generator*, which raises
  ``TypeError: 'async_generator' object does not support the asynchronous
  context manager protocol`` — killing every Redis-queued pipeline task.
- C2: ``seed_data_if_empty`` must never inject mock ApprovalAction/AuditEntry
  rows in a production environment.
- C3: ``run_pipeline_task`` must fail closed (raise) in production when
  Shopify data is unavailable instead of silently falling back to mock
  inventory/orders that drive real decisions.
"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from ecommerce_ops.config import Environment

# ── C1: Redis pipeline handler must not crash on session open ──────────────


class FakeSession:
    """Async-context manager session returning a StoreSettings-less query."""

    def __init__(self):
        self._result = MagicMock()
        self._result.scalar_one_or_none.return_value = None

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False

    async def execute(self, *args, **kwargs):
        return self._result

    def add(self, obj):
        pass

    async def commit(self):
        pass


@pytest.mark.asyncio
async def test_pipeline_task_handler_uses_async_session_factory():
    """C1: handler must open the session via async_session_factory.

    The historical bug (`async with get_db_session()`) crashed every queued
    task. The handler must now succeed and forward the run_id downstream.
    """
    import ecommerce_ops.api.app as app_mod

    fake_factory = MagicMock(return_value=FakeSession())
    runner = AsyncMock()

    with (
        patch.object(app_mod, "async_session_factory", fake_factory),
        patch.object(app_mod, "run_pipeline_task", runner),
    ):
        await app_mod._pipeline_task_handler({"run_id": "run-ph0-1"})

    runner.assert_awaited_once()
    call_run_id, _settings = runner.await_args.args
    assert call_run_id == "run-ph0-1"


# ── C2: mock seeding must be skipped in production ─────────────────────────


@pytest.mark.asyncio
async def test_seed_data_if_empty_skips_in_production():
    """C2: prod must not get 8 mock actions + 4 fake audit entries."""
    import ecommerce_ops.models.seed as seed_mod

    factory = MagicMock(return_value=FakeSession())

    with (
        patch.object(seed_mod.settings, "ENV", Environment.PRODUCTION),
        patch.object(seed_mod, "async_session_factory", factory),
    ):
        await seed_mod.seed_data_if_empty()

    factory.assert_not_called()


@pytest.mark.asyncio
async def test_seed_data_if_empty_runs_outside_production():
    """C2: seeding still runs for development/testing environments."""
    import ecommerce_ops.models.seed as seed_mod

    factory = MagicMock(return_value=FakeSession())

    with (
        patch.object(seed_mod.settings, "ENV", Environment.DEVELOPMENT),
        patch.object(seed_mod, "async_session_factory", factory),
    ):
        await seed_mod.seed_data_if_empty()

    factory.assert_called_once()


# ── C3: fail closed when Shopify data is unavailable in production ─────────


@pytest.mark.asyncio
async def test_pipeline_fails_closed_when_shopify_unavailable_in_production():
    """C3: production must never run the mock-data fallback path."""
    import ecommerce_ops.pipeline.runner as runner_mod

    db_settings = MagicMock()
    db_settings.shadow_mode = False
    db_settings.po_limit = 1000.0
    db_settings.pricing_limit = 5.0
    db_settings.reviews_rating_threshold = 4

    with (
        patch.object(runner_mod.app_settings, "ENV", Environment.PRODUCTION),
        patch.object(runner_mod, "fetch_shopify_data", AsyncMock(return_value=None)),
        patch.object(runner_mod, "_try_register_pipeline_run", AsyncMock(return_value=MagicMock())),
        pytest.raises(RuntimeError, match="fail-open to mock data is disabled"),
    ):
        await runner_mod.run_pipeline_task("run-ph0-2", db_settings)


@pytest.mark.asyncio
async def test_pipeline_uses_mock_outside_production():
    """C3: development/testing still gets the mock-data fallback."""
    import ecommerce_ops.pipeline.runner as runner_mod

    db_settings = MagicMock()
    db_settings.shadow_mode = True
    db_settings.po_limit = 1000.0
    db_settings.pricing_limit = 5.0
    db_settings.reviews_rating_threshold = 4

    session = AsyncMock()
    execute_result = MagicMock()
    execute_result.scalar_one.return_value = db_settings
    session.execute.return_value = execute_result
    session.commit = AsyncMock()
    session.add = MagicMock()
    session_mgr = MagicMock()
    session_mgr.__aenter__ = AsyncMock(return_value=session)
    session_mgr.__aexit__ = AsyncMock(return_value=False)

    supervisor = MagicMock()
    supervisor.return_value.run = AsyncMock(return_value={"decisions": [], "hitl_queue": []})

    with (
        patch.object(runner_mod.app_settings, "ENV", Environment.DEVELOPMENT),
        patch.object(runner_mod, "fetch_shopify_data", AsyncMock(return_value=None)),
        patch.object(runner_mod, "_try_register_pipeline_run", AsyncMock(return_value=MagicMock())),
        patch.object(runner_mod, "async_session_factory", MagicMock(return_value=session_mgr)),
        patch.object(runner_mod, "Supervisor", supervisor),
        patch.object(runner_mod, "langfuse_client", MagicMock()),
        patch.object(runner_mod.ws_manager, "broadcast", AsyncMock()),
        patch.object(runner_mod, "notify_hitl_request", AsyncMock()),
        patch.object(runner_mod, "notify_pipeline_failed", AsyncMock()),
    ):
        await runner_mod.run_pipeline_task("run-ph0-3", db_settings)
