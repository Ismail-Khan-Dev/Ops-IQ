"""
Shopify Webhook Event Handlers
Handles real-time webhook events from Shopify.

Every verified webhook payload is persisted to the ``shopify_webhook_events``
table (durable inbox) with ``processed=False`` before any downstream
processing, giving at-least-once delivery and replayability. The row is only
flipped to ``processed=True`` after the downstream task has actually run.
Failures are logged, never raised, during ingestion; downstream task failures
are recorded on the row and re-raised so the queue can retry.
"""

import logging
import uuid
from typing import Any, Dict, Optional

from sqlalchemy import select

from ecommerce_ops.connectors.shopify.webhooks import WebhookEvent
from ecommerce_ops.models import (
    ShopifyWebhookEvent,
    StoreSettings,
    async_session_factory,
)
from ecommerce_ops.pipeline.runner import run_pipeline_task

logger = logging.getLogger("ecommerce_ops.connectors.shopify.handlers")

# Task names enqueued by the webhook handlers. Every one of these MUST have a
# registered queue handler, otherwise Redis-backed tasks would be failed
# immediately with "No handler for task".
SHOPIFY_TASK_NAMES = (
    "shopify.order_created",
    "shopify.order_updated",
    "shopify.order_fulfilled",
    "shopify.order_cancelled",
    "shopify.product_created",
    "shopify.product_updated",
    "shopify.product_deleted",
    "shopify.customer_created",
    "shopify.customer_updated",
    "shopify.inventory_low",
    "shopify.inventory_changed",
)


async def _persist_event(event: WebhookEvent, error: Optional[str] = None) -> Optional[int]:
    """Persist a verified webhook payload to the durable inbox.

    Returns the new inbox row id so downstream processing can flip the
    ``processed`` flag only after the work has actually completed.
    """
    try:
        payload = event.body if isinstance(event.body, dict) else {"data": event.body}
        async with async_session_factory() as session:
            row = ShopifyWebhookEvent(
                topic=event.topic,
                shop_domain=event.shop_domain,
                api_version=event.api_version,
                event_id=str(payload.get("id", "")) or None,
                processed=False,
                error=error,
                payload=payload,
            )
            session.add(row)
            await session.commit()
            await session.refresh(row)
        logger.info("Persisted webhook event topic=%s shop=%s", event.topic, event.shop_domain)
        return int(row.id)
    except Exception:
        logger.exception(
            "Failed to persist webhook event topic=%s shop=%s", event.topic, event.shop_domain
        )
        return None


async def _mark_processed(event_row_id: Optional[int], error: Optional[str] = None) -> None:
    """Flip the durable inbox row to processed only after downstream work."""
    if not event_row_id:
        return
    try:
        async with async_session_factory() as session:
            row = await session.get(ShopifyWebhookEvent, event_row_id)
            if row:
                row.processed = error is None
                row.error = error
                await session.commit()
    except Exception:
        logger.exception("Failed to update processed flag for webhook event %s", event_row_id)


async def _run_pipeline_for_event(run_id: str) -> None:
    """Run the agent pipeline so the event feeds the autonomous decision loop."""
    async with async_session_factory() as session:
        res = await session.execute(select(StoreSettings).where(StoreSettings.id == 1))
        db_settings = res.scalar_one_or_none()
        if not db_settings:
            db_settings = StoreSettings(
                id=1,
                shadow_mode=True,
                fraud_threshold=70,
                po_limit=1000.0,
                pricing_limit=5.0,
                reviews_rating_threshold=4,
            )
            session.add(db_settings)
            await session.commit()
    await run_pipeline_task(run_id, db_settings)


async def process_shopify_event(payload: Dict[str, Any]) -> None:
    """Queue handler for every ``shopify.*`` task name.

    Runs the actual downstream agent work, then flips the durable inbox row to
    ``processed``. On failure the row keeps ``processed=False`` (with the error)
    and the exception is re-raised so the queue marks the task failed and may
    retry it.
    """
    event_id = payload.get("webhook_event_id")
    topic = payload.get("webhook_topic", "unknown")
    shop_domain = payload.get("shop_domain", "unknown")
    error = None
    try:
        logger.info("Processing Shopify event topic=%s shop=%s", topic, shop_domain)
        await _run_pipeline_for_event(str(uuid.uuid4()))
    except Exception as e:
        error = str(e)
        logger.exception(
            "Shopify event topic=%s shop=%s processing failed: %s",
            topic,
            shop_domain,
            e,
        )
    finally:
        await _mark_processed(event_id, error=error)
    if error:
        raise RuntimeError(f"Shopify event {topic} failed to process: {error}")


async def _enqueue_agent_work(
    event: WebhookEvent,
    task_name: str,
    payload: Dict[str, Any],
    event_row_id: Optional[int] = None,
) -> None:
    """Best-effort enqueue of downstream agent work.

    Uses the Redis-backed queue when available (cross-worker). Falls back to
    the in-memory queue with the real processing handler so the event is not
    silently dropped. Failures are logged, never raised, so a queue outage does
    not take down webhook ingestion.
    """
    try:
        from ecommerce_ops.api.app import redis_task_queue, task_queue

        enqueue_payload = {
            **payload,
            "shop_domain": event.shop_domain,
            "webhook_topic": event.topic,
            "webhook_event_id": event_row_id,
        }
        if redis_task_queue is not None:
            from ecommerce_ops.infra.redis_task_queue import TaskPriority

            await redis_task_queue.enqueue(task_name, enqueue_payload, priority=TaskPriority.NORMAL)
            logger.info("Enqueued %s via Redis queue for shop=%s", task_name, event.shop_domain)
        else:
            await task_queue.enqueue(task_name, process_shopify_event, payload=enqueue_payload)
            logger.info("Enqueued %s via in-memory queue for shop=%s", task_name, event.shop_domain)
    except Exception:
        logger.exception("Failed to enqueue %s for shop=%s", task_name, event.shop_domain)


async def _handle(
    event: WebhookEvent, task_name: str, payload: Dict[str, Any], error: Optional[str] = None
) -> None:
    """Common pipeline: persist then enqueue."""
    event_row_id = await _persist_event(event, error=error)
    await _enqueue_agent_work(event, task_name, payload, event_row_id)


async def handle_order_created(event: WebhookEvent) -> None:
    """Handle new order webhook."""
    order = event.body
    order_id = order.get("id")
    total_price = order.get("total_price", "0.00")
    currency = order.get("currency", "USD")
    customer_email = order.get("email")

    logger.info(
        "New order received: %s ($%s %s) from %s",
        order_id,
        total_price,
        currency,
        customer_email,
    )

    await _handle(
        event,
        task_name="shopify.order_created",
        payload={
            "order_id": order_id,
            "total_price": total_price,
            "currency": currency,
            "customer_email": customer_email,
            "financial_status": order.get("financial_status"),
        },
    )


async def handle_order_updated(event: WebhookEvent) -> None:
    """Handle order update webhook."""
    order = event.body
    order_id = order.get("id")
    financial_status = order.get("financial_status")
    fulfillment_status = order.get("fulfillment_status")

    logger.info(
        "Order %s updated: financial=%s, fulfillment=%s",
        order_id,
        financial_status,
        fulfillment_status,
    )

    await _handle(
        event,
        task_name="shopify.order_updated",
        payload={
            "order_id": order_id,
            "financial_status": financial_status,
            "fulfillment_status": fulfillment_status,
        },
    )


async def handle_order_fulfilled(event: WebhookEvent) -> None:
    """Handle order fulfilled webhook."""
    order = event.body
    order_id = order.get("id")
    fulfillments = order.get("fulfillments", [])

    for fulfillment in fulfillments:
        tracking_number = fulfillment.get("tracking_number")
        tracking_company = fulfillment.get("tracking_company")
        logger.info(
            "Order %s fulfilled: %s via %s",
            order_id,
            tracking_number,
            tracking_company,
        )

    await _handle(
        event,
        task_name="shopify.order_fulfilled",
        payload={
            "order_id": order_id,
            "fulfillments": fulfillments,
        },
    )


async def handle_order_cancelled(event: WebhookEvent) -> None:
    """Handle order cancelled webhook."""
    order = event.body
    order_id = order.get("id")
    cancel_reason = order.get("cancel_reason", "unknown")

    logger.info("Order %s cancelled: %s", order_id, cancel_reason)

    await _handle(
        event,
        task_name="shopify.order_cancelled",
        payload={
            "order_id": order_id,
            "cancel_reason": cancel_reason,
        },
    )


async def handle_product_created(event: WebhookEvent) -> None:
    """Handle new product webhook."""
    product = event.body
    product_id = product.get("id")
    title = product.get("title")
    product_type = product.get("product_type")
    vendor = product.get("vendor")

    logger.info("New product: %s (%s) by %s [%s]", title, product_id, vendor, product_type)

    await _handle(
        event,
        task_name="shopify.product_created",
        payload={
            "product_id": product_id,
            "title": title,
            "product_type": product_type,
            "vendor": vendor,
            "price": product.get("variants", [{}])[0].get("price")
            if product.get("variants")
            else None,
        },
    )


async def handle_product_updated(event: WebhookEvent) -> None:
    """Handle product update webhook."""
    product = event.body
    product_id = product.get("id")
    title = product.get("title")

    logger.info("Product updated: %s (%s)", title, product_id)

    await _handle(
        event,
        task_name="shopify.product_updated",
        payload={
            "product_id": product_id,
            "title": title,
            "price": product.get("variants", [{}])[0].get("price")
            if product.get("variants")
            else None,
        },
    )


async def handle_product_deleted(event: WebhookEvent) -> None:
    """Handle product deletion webhook."""
    product = event.body
    product_id = product.get("id")

    logger.info("Product deleted: %s", product_id)

    await _handle(
        event,
        task_name="shopify.product_deleted",
        payload={"product_id": product_id},
    )


async def handle_customer_created(event: WebhookEvent) -> None:
    """Handle new customer webhook."""
    customer = event.body
    customer_id = customer.get("id")
    email = customer.get("email")
    first_name = customer.get("first_name", "")
    last_name = customer.get("last_name", "")

    logger.info("New customer: %s %s (%s) [%s]", first_name, last_name, email, customer_id)

    await _handle(
        event,
        task_name="shopify.customer_created",
        payload={
            "customer_id": customer_id,
            "email": email,
            "first_name": first_name,
            "last_name": last_name,
        },
    )


async def handle_customer_updated(event: WebhookEvent) -> None:
    """Handle customer update webhook."""
    customer = event.body
    customer_id = customer.get("id")

    logger.info("Customer updated: %s", customer_id)

    await _handle(
        event,
        task_name="shopify.customer_updated",
        payload={"customer_id": customer_id},
    )


async def handle_inventory_level_low(event: WebhookEvent) -> None:
    """Handle low inventory webhook."""
    inventory = event.body
    inventory_item_id = inventory.get("inventory_item_id")
    location_id = inventory.get("location_id")
    available = inventory.get("available", 0)

    logger.warning(
        "Low inventory: item=%s location=%s available=%d",
        inventory_item_id,
        location_id,
        available,
    )

    await _handle(
        event,
        task_name="shopify.inventory_low",
        payload={
            "inventory_item_id": inventory_item_id,
            "location_id": location_id,
            "available": available,
        },
    )


async def handle_inventory_levels_changed(event: WebhookEvent) -> None:
    """Handle inventory level change webhook."""
    inventory = event.body
    inventory_item_id = inventory.get("inventory_item_id")
    available = inventory.get("available", 0)

    logger.info("Inventory changed: item=%s available=%d", inventory_item_id, available)

    await _handle(
        event,
        task_name="shopify.inventory_changed",
        payload={
            "inventory_item_id": inventory_item_id,
            "available": available,
        },
    )


# Handler registry for easy registration
WEBHOOK_HANDLERS = {
    "orders/create": handle_order_created,
    "orders/updated": handle_order_updated,
    "orders/fulfilled": handle_order_fulfilled,
    "orders/cancelled": handle_order_cancelled,
    "products/create": handle_product_created,
    "products/update": handle_product_updated,
    "products/delete": handle_product_deleted,
    "customers/create": handle_customer_created,
    "customers/update": handle_customer_updated,
    "inventory_levels/low": handle_inventory_level_low,
    "inventory_levels/change": handle_inventory_levels_changed,
}
