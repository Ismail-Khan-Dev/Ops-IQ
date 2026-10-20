"""Tests for Shopify sync persistence (Phase 3 — no-op -> real writes)."""

from unittest.mock import AsyncMock

import pytest

from ecommerce_ops.connectors.shopify.models import (
    OrderFinancialStatus,
    ShopifyCustomer,
    ShopifyOrder,
    ShopifyProduct,
    ShopifyVariant,
)
from ecommerce_ops.connectors.shopify.sync import ShopifySyncService
from ecommerce_ops.models import (
    ShopifyCustomerSnapshot,
    ShopifyOrderSnapshot,
    ShopifyProductSnapshot,
)


class _FakeClient:
    def __init__(self, shop_domain: str):
        self.shop_domain = shop_domain
        self.get_products = AsyncMock()
        self.get_orders = AsyncMock()
        self.get_customers = AsyncMock()


@pytest.mark.asyncio
async def test_sync_products_persists_rows(db_session):
    from sqlalchemy import func, select

    client = _FakeClient("test.myshopify.com")
    client.get_products.return_value = {
        "products": [
            {
                "id": 123,
                "title": "Blue Shirt",
                "variants": [
                    {"id": 1, "product_id": 123, "sku": "SKU1", "price": "10.00", "inventory_quantity": 5},
                    {"id": 2, "product_id": 123, "sku": "SKU2", "price": "20.00", "inventory_quantity": 3},
                ],
            }
        ]
    }
    service = ShopifySyncService(client)

    count = await service.sync_products(db_session, limit=10)
    await db_session.commit()

    assert count == 1
    result = await db_session.execute(select(func.count(ShopifyProductSnapshot.id)))
    assert result.scalar() == 1

    row = (await db_session.execute(select(ShopifyProductSnapshot))).scalar_one()
    assert row.shopify_product_id == "123"
    assert row.shop_domain == "test.myshopify.com"
    assert row.sku == "SKU1"
    assert row.min_price == 10.0
    assert row.max_price == 20.0
    assert row.total_inventory == 8
    assert row.raw_data["id"] == 123


@pytest.mark.asyncio
async def test_sync_orders_persists_rows(db_session):
    from sqlalchemy import func, select

    client = _FakeClient("test.myshopify.com")
    client.get_orders.return_value = {
        "orders": [
            {
                "id": 456,
                "order_number": 1001,
                "total_price": "50.00",
                "currency": "USD",
                "financial_status": "paid",
                "fulfillment_status": None,
            }
        ]
    }
    service = ShopifySyncService(client)

    count = await service.sync_orders(db_session, limit=10)
    await db_session.commit()

    assert count == 1
    result = await db_session.execute(select(func.count(ShopifyOrderSnapshot.id)))
    assert result.scalar() == 1

    row = (await db_session.execute(select(ShopifyOrderSnapshot))).scalar_one()
    assert row.shopify_order_id == "456"
    assert row.total_price == 50.0
    assert row.financial_status == "paid"


@pytest.mark.asyncio
async def test_sync_customers_persists_rows(db_session):
    from sqlalchemy import func, select

    client = _FakeClient("test.myshopify.com")
    client.get_customers.return_value = {
        "customers": [
            {
                "id": 789,
                "email": "cust@example.com",
                "first_name": "Jane",
                "last_name": "Doe",
                "orders_count": 3,
                "total_spent": "120.00",
            }
        ]
    }
    service = ShopifySyncService(client)

    count = await service.sync_customers(db_session, limit=10)
    await db_session.commit()

    assert count == 1
    result = await db_session.execute(select(func.count(ShopifyCustomerSnapshot.id)))
    assert result.scalar() == 1

    row = (await db_session.execute(select(ShopifyCustomerSnapshot))).scalar_one()
    assert row.shopify_customer_id == "789"
    assert row.email == "cust@example.com"
    assert row.total_spent == 120.0


@pytest.mark.asyncio
async def test_sync_upsert_is_idempotent(db_session):
    from sqlalchemy import func, select

    client = _FakeClient("test.myshopify.com")
    service = ShopifySyncService(client)

    client.get_products.return_value = {
        "products": [
            {
                "id": 123,
                "title": "Blue Shirt",
                "variants": [
                    {"id": 1, "product_id": 123, "sku": "SKU1", "price": "10.00", "inventory_quantity": 5},
                ],
            }
        ]
    }
    await service.sync_products(db_session, limit=10)
    # Re-sync the same product with updated inventory — should upsert, not duplicate
    client.get_products.return_value = {
        "products": [
            {
                "id": 123,
                "title": "Blue Shirt",
                "variants": [
                    {"id": 1, "product_id": 123, "sku": "SKU1", "price": "10.00", "inventory_quantity": 99},
                ],
            }
        ]
    }
    await service.sync_products(db_session, limit=10)
    await db_session.commit()

    result = await db_session.execute(select(func.count(ShopifyProductSnapshot.id)))
    assert result.scalar() == 1

    row = (await db_session.execute(select(ShopifyProductSnapshot))).scalar_one()
    assert row.total_inventory == 99
