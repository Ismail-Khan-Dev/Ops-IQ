"""Tests for Shopify webhook durable-inbox semantics (C2)."""

from unittest.mock import AsyncMock, patch

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from ecommerce_ops.connectors.shopify.handlers.order_handlers import (
    SHOPIFY_TASK_NAMES,
    WEBHOOK_HANDLERS,
    _persist_event,
    process_shopify_event,
)
from ecommerce_ops.connectors.shopify.webhooks import (
    ShopifyWebhookRouter,
    WebhookEvent,
    webhook_router,
)
from ecommerce_ops.models import ShopifyWebhookEvent
from ecommerce_ops.models.db import Base


@pytest_asyncio.fixture
async def db_factory():
    engine = create_async_engine("sqlite+aiosqlite://", echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)
    yield factory
    await engine.dispose()


def _event():
    return WebhookEvent(
        topic="orders/create",
        shop_domain="brand.myshopify.com",
        api_version="2024-01",
        body={"id": 9001, "total_price": "99.00", "currency": "USD"},
        headers={},
    )


def test_shopify_task_names_include_all_handlers():
    assert "shopify.order_created" in SHOPIFY_TASK_NAMES
    assert "shopify.inventory_low" in SHOPIFY_TASK_NAMES
    assert "shopify.inventory_changed" in SHOPIFY_TASK_NAMES
    assert len(SHOPIFY_TASK_NAMES) == 11


@pytest.mark.asyncio
async def test_persist_event_starts_unprocessed(db_factory):
    with patch(
        "ecommerce_ops.connectors.shopify.handlers.order_handlers.async_session_factory",
        db_factory,
    ):
        row_id = await _persist_event(_event())

    assert row_id is not None
    async with db_factory() as s:
        row = await s.get(ShopifyWebhookEvent, row_id)
    assert row is not None
    assert row.processed is False
    assert row.event_id == "9001"


@pytest.mark.asyncio
async def test_process_event_marks_processed_after_work(db_factory):
    with patch(
        "ecommerce_ops.connectors.shopify.handlers.order_handlers.async_session_factory",
        db_factory,
    ):
        row_id = await _persist_event(_event())
        with patch(
            "ecommerce_ops.connectors.shopify.handlers.order_handlers._run_pipeline_for_event",
            new_callable=AsyncMock,
        ) as mock_work:
            await process_shopify_event(
                {
                    "webhook_event_id": row_id,
                    "webhook_topic": "orders/create",
                    "shop_domain": "brand.myshopify.com",
                }
            )
        mock_work.assert_awaited_once()

    async with db_factory() as s:
        row = await s.get(ShopifyWebhookEvent, row_id)
    assert row.processed is True
    assert row.error is None


@pytest.mark.asyncio
async def test_process_event_failure_keeps_unprocessed_and_raises(db_factory):
    with patch(
        "ecommerce_ops.connectors.shopify.handlers.order_handlers.async_session_factory",
        db_factory,
    ):
        row_id = await _persist_event(_event())
        with (
            patch(
                "ecommerce_ops.connectors.shopify.handlers.order_handlers._run_pipeline_for_event",
                new_callable=AsyncMock,
                side_effect=RuntimeError("boom"),
            ),
            pytest.raises(RuntimeError, match="failed to process"),
        ):
            await process_shopify_event(
                {
                    "webhook_event_id": row_id,
                    "webhook_topic": "orders/create",
                    "shop_domain": "brand.myshopify.com",
                }
            )

    async with db_factory() as s:
        row = await s.get(ShopifyWebhookEvent, row_id)
    assert row.processed is False
    assert "boom" in (row.error or "")


def test_router_register_is_idempotent():
    """Registering the same handlers twice must not double-dispatch."""
    router = ShopifyWebhookRouter()
    router.register_many(WEBHOOK_HANDLERS)
    router.register_many(WEBHOOK_HANDLERS)
    assert len(router.get_supported_topics()) == len(WEBHOOK_HANDLERS)
    assert all(len(handlers) == 1 for handlers in router._handlers.values())


@pytest.mark.asyncio
async def test_app_startup_registers_webhook_handlers():
    """Every worker must serve webhooks from boot, not only after an OAuth
    callback (any worker that never ran a callback would otherwise drop
    webhooks with 'no handlers for topic')."""
    import ecommerce_ops.api.app as app_mod

    await app_mod._register_webhook_handlers()
    topics = webhook_router.get_supported_topics()
    assert set(WEBHOOK_HANDLERS).issubset(topics)

    await app_mod._register_webhook_handlers()  # idempotent — no duplicates
    assert len(webhook_router._handlers["orders/create"]) == 1
