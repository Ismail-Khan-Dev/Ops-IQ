"""
Shopify Data Sync Service
Synchronizes data between Shopify and our database.
"""

import logging
import time
from datetime import datetime
from typing import Any, Dict, List, Optional

from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.ext.asyncio import AsyncSession

from ecommerce_ops.connectors.shopify.client import ShopifyClient
from ecommerce_ops.connectors.shopify.models import (
    ShopifyCustomer,
    ShopifyOrder,
    ShopifyProduct,
)
from ecommerce_ops.models import (
    ShopifyCustomerSnapshot,
    ShopifyOrderSnapshot,
    ShopifyProductSnapshot,
)
from ecommerce_ops.utils import utc_now

logger = logging.getLogger("ecommerce_ops.connectors.shopify.sync")


def _dialect_insert(table):
    """Dialect-aware insert supporting ON CONFLICT DO UPDATE.

    The generic ``sqlalchemy.insert`` does not expose ``on_conflict_do_update``;
    only the PostgreSQL and SQLite dialect constructs do.  Index elements must
    be passed as ``index_elements`` (not ``indexes``).
    """
    from ecommerce_ops.models.db import is_sqlite

    return sqlite_insert(table) if is_sqlite else pg_insert(table)


logger = logging.getLogger("ecommerce_ops.connectors.shopify.sync")


class ShopifySyncResult:
    """Result of a sync operation."""

    def __init__(self):
        self.products_synced = 0
        self.orders_synced = 0
        self.customers_synced = 0
        self.errors: List[str] = []
        self.started_at = time.time()
        self.completed_at: Optional[float] = None

    @property
    def duration_seconds(self) -> float:
        if self.completed_at:
            return self.completed_at - self.started_at
        return time.time() - self.started_at

    def to_dict(self) -> Dict[str, Any]:
        return {
            "products_synced": self.products_synced,
            "orders_synced": self.orders_synced,
            "customers_synced": self.customers_synced,
            "errors": self.errors,
            "duration_seconds": round(self.duration_seconds, 2),
        }


class ShopifySyncService:
    """Synchronizes Shopify data to local database."""

    def __init__(self, client: ShopifyClient):
        self.client = client
        self.shop_domain = getattr(client, "shop_domain", "") or ""

    async def sync_products(
        self,
        session: AsyncSession,
        since_id: Optional[int] = None,
        limit: int = 250,
    ) -> int:
        """Sync products from Shopify."""
        count = 0
        page_info = None

        while True:
            response = await self.client.get_products(limit=limit, page_info=page_info)
            products_data = response.get("products", [])

            if not products_data:
                break

            for product_data in products_data:
                try:
                    product = ShopifyProduct(**product_data)
                    await self._upsert_product(session, product)
                    count += 1
                except Exception as e:
                    logger.error("Failed to sync product %s: %s", product_data.get("id"), e)

            # Check for next page
            page_info = response.get("page_info")
            if not page_info:
                break

        await session.commit()
        logger.info("Synced %d products from Shopify", count)
        return count

    async def sync_orders(
        self,
        session: AsyncSession,
        status: str = "any",
        since_date: Optional[datetime] = None,
        limit: int = 250,
    ) -> int:
        """Sync orders from Shopify."""
        count = 0
        page_info = None

        while True:
            kwargs: Dict[str, Any] = {"status": status, "limit": limit}
            if page_info:
                kwargs["page_info"] = page_info
                kwargs.pop("limit", None)
            if since_date:
                kwargs["created_at_min"] = since_date.isoformat()

            response = await self.client.get_orders(**kwargs)
            orders_data = response.get("orders", [])

            if not orders_data:
                break

            for order_data in orders_data:
                try:
                    order = ShopifyOrder(**order_data)
                    await self._upsert_order(session, order)
                    count += 1
                except Exception as e:
                    logger.error("Failed to sync order %s: %s", order_data.get("id"), e)

            page_info = response.get("page_info")
            if not page_info:
                break

        await session.commit()
        logger.info("Synced %d orders from Shopify", count)
        return count

    async def sync_customers(
        self,
        session: AsyncSession,
        limit: int = 250,
    ) -> int:
        """Sync customers from Shopify."""
        count = 0
        page_info = None

        while True:
            response = await self.client.get_customers(limit=limit, page_info=page_info)
            customers_data = response.get("customers", [])

            if not customers_data:
                break

            for customer_data in customers_data:
                try:
                    customer = ShopifyCustomer(**customer_data)
                    await self._upsert_customer(session, customer)
                    count += 1
                except Exception as e:
                    logger.error("Failed to sync customer %s: %s", customer_data.get("id"), e)

            page_info = response.get("page_info")
            if not page_info:
                break

        await session.commit()
        logger.info("Synced %d customers from Shopify", count)
        return count

    async def full_sync(self, session: AsyncSession) -> ShopifySyncResult:
        """Run full data sync (products, orders, customers)."""
        result = ShopifySyncResult()

        try:
            result.products_synced = await self.sync_products(session)
        except Exception as e:
            result.errors.append(f"Product sync failed: {e}")
            logger.error("Product sync failed: %s", e)

        try:
            result.orders_synced = await self.sync_orders(session)
        except Exception as e:
            result.errors.append(f"Order sync failed: {e}")
            logger.error("Order sync failed: %s", e)

        try:
            result.customers_synced = await self.sync_customers(session)
        except Exception as e:
            result.errors.append(f"Customer sync failed: {e}")
            logger.error("Customer sync failed: %s", e)

        result.completed_at = time.time()
        logger.info("Full sync completed: %s", result.to_dict())
        return result

    async def _upsert_product(self, session: AsyncSession, product: ShopifyProduct) -> None:
        """Insert or update product snapshot in database (real persistence)."""
        primary_sku = product.variants[0].sku if product.variants else None
        values = {
            "shopify_product_id": str(product.id),
            "shop_domain": self.shop_domain,
            "title": product.title,
            "sku": primary_sku,
            "min_price": float(product.min_price),
            "max_price": float(product.max_price),
            "total_inventory": int(product.total_inventory),
            "raw_data": product.model_dump(),
            "synced_at": utc_now(),
        }
        stmt = _dialect_insert(ShopifyProductSnapshot).values(**values)
        stmt = stmt.on_conflict_do_update(
            index_elements=["shop_domain", "shopify_product_id"],
            set_={
                "title": stmt.excluded.title,
                "sku": stmt.excluded.sku,
                "min_price": stmt.excluded.min_price,
                "max_price": stmt.excluded.max_price,
                "total_inventory": stmt.excluded.total_inventory,
                "raw_data": stmt.excluded.raw_data,
                "synced_at": stmt.excluded.synced_at,
            },
        )
        await session.execute(stmt)

    async def _upsert_order(self, session: AsyncSession, order: ShopifyOrder) -> None:
        """Insert or update order snapshot in database (real persistence)."""
        try:
            total_price = float(order.total_price)
        except (ValueError, TypeError):
            total_price = 0.0
        values = {
            "shopify_order_id": str(order.id),
            "shop_domain": self.shop_domain,
            "order_number": order.order_number,
            "total_price": total_price,
            "currency": order.currency,
            "financial_status": order.financial_status.value if order.financial_status else None,
            "fulfillment_status": order.fulfillment_status.value
            if order.fulfillment_status
            else None,
            "raw_data": order.model_dump(),
            "synced_at": utc_now(),
        }
        stmt = _dialect_insert(ShopifyOrderSnapshot).values(**values)
        stmt = stmt.on_conflict_do_update(
            index_elements=["shop_domain", "shopify_order_id"],
            set_={
                "order_number": stmt.excluded.order_number,
                "total_price": stmt.excluded.total_price,
                "currency": stmt.excluded.currency,
                "financial_status": stmt.excluded.financial_status,
                "fulfillment_status": stmt.excluded.fulfillment_status,
                "raw_data": stmt.excluded.raw_data,
                "synced_at": stmt.excluded.synced_at,
            },
        )
        await session.execute(stmt)

    async def _upsert_customer(self, session: AsyncSession, customer: ShopifyCustomer) -> None:
        """Insert or update customer snapshot in database (real persistence)."""
        try:
            total_spent = float(customer.total_spent)
        except (ValueError, TypeError):
            total_spent = 0.0
        values = {
            "shopify_customer_id": str(customer.id),
            "shop_domain": self.shop_domain,
            "email": customer.email,
            "first_name": customer.first_name,
            "last_name": customer.last_name,
            "orders_count": int(customer.orders_count),
            "total_spent": total_spent,
            "raw_data": customer.model_dump(),
            "synced_at": utc_now(),
        }
        stmt = _dialect_insert(ShopifyCustomerSnapshot).values(**values)
        stmt = stmt.on_conflict_do_update(
            index_elements=["shop_domain", "shopify_customer_id"],
            set_={
                "email": stmt.excluded.email,
                "first_name": stmt.excluded.first_name,
                "last_name": stmt.excluded.last_name,
                "orders_count": stmt.excluded.orders_count,
                "total_spent": stmt.excluded.total_spent,
                "raw_data": stmt.excluded.raw_data,
                "synced_at": stmt.excluded.synced_at,
            },
        )
        await session.execute(stmt)
