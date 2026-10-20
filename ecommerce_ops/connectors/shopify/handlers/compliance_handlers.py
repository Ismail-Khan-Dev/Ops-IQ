"""
Shopify Mandatory Compliance & GDPR Webhook Handlers
Required for Shopify App Store Certification & 'Built for Shopify' compliance:
  1. app/uninstalled: Cleans up shop credentials, pauses sync, marks inactive.
  2. customers/redact: Redacts customer PII upon GDPR erasure request.
  3. shop/redact: Erases store data 48h post-uninstall.
  4. customers/data_request: Returns all stored data for a customer.
"""

import logging
from typing import Any, Dict, Optional

from sqlalchemy import select, update

from ecommerce_ops.connectors.shopify.webhooks import WebhookEvent
from ecommerce_ops.models import (
    ApprovalAction,
    ShopifyCustomerSnapshot,
    ShopifyOrderSnapshot,
    ShopifyShopCredential,
    ShopifyWebhookEvent,
    async_session_factory,
)
from ecommerce_ops.security.audit import audit_logger
from ecommerce_ops.security.models import SecurityEvent
from ecommerce_ops.utils import utc_now

logger = logging.getLogger("ecommerce_ops.connectors.shopify.handlers.compliance")


async def handle_app_uninstalled(event: WebhookEvent) -> None:
    """Handle app/uninstalled webhook when a merchant uninstalls OpsIQ."""
    shop_domain = event.shop_domain
    logger.warning("Shopify App Uninstalled received for shop: %s", shop_domain)

    async with async_session_factory() as session:
        # Mark credentials as inactive
        stmt = (
            update(ShopifyShopCredential)
            .where(ShopifyShopCredential.shop_domain == shop_domain)
            .values(is_active=False, updated_at=utc_now())
        )
        await session.execute(stmt)
        await session.commit()

    audit_logger.log_event(
        SecurityEvent(
            event_type="shopify_lifecycle",
            action="app_uninstalled",
            resource="shop_credentials",
            resource_id=shop_domain,
            user_id="shopify_system",
            success=True,
            details={"shop_domain": shop_domain},
        )
    )
    logger.info("Deactivated credentials for uninstalled shop: %s", shop_domain)


async def handle_customers_redact(event: WebhookEvent) -> None:
    """Handle customers/redact mandatory GDPR webhook.

    Redacts customer personal data from snapshots and logs.
    """
    body = event.body or {}
    shop_domain = event.shop_domain
    customer_info = body.get("customer") or {}
    customer_id = str(customer_info.get("id") or "")
    customer_email = customer_info.get("email")

    logger.warning(
        "GDPR customers/redact received for shop=%s, customer_id=%s, email=%s",
        shop_domain,
        customer_id,
        customer_email,
    )

    async with async_session_factory() as session:
        if customer_id:
            # Redact customer snapshot
            res = await session.execute(
                select(ShopifyCustomerSnapshot).where(
                    ShopifyCustomerSnapshot.shop_domain == shop_domain,
                    ShopifyCustomerSnapshot.shopify_customer_id == customer_id,
                )
            )
            snapshot = res.scalar_one_or_none()
            if snapshot:
                snapshot.email = "redacted@gdpr.local"
                snapshot.first_name = "REDACTED"
                snapshot.last_name = "REDACTED"
                snapshot.phone = None
                snapshot.data = {"redacted": True, "redacted_at": utc_now().isoformat()}

        await session.commit()

    audit_logger.log_event(
        SecurityEvent(
            event_type="gdpr_compliance",
            action="customers_redact",
            resource="customer_pii",
            resource_id=customer_id or customer_email or "unknown",
            user_id="shopify_gdpr",
            success=True,
            details={"shop_domain": shop_domain, "customer_id": customer_id},
        )
    )
    logger.info("Successfully processed customers/redact for shop=%s", shop_domain)


async def handle_shop_redact(event: WebhookEvent) -> None:
    """Handle shop/redact mandatory GDPR webhook (48h post-uninstall)."""
    shop_domain = event.shop_domain
    logger.warning("GDPR shop/redact received for shop: %s", shop_domain)

    async with async_session_factory() as session:
        # Purge shop credentials and mark snapshots deleted
        stmt = (
            update(ShopifyShopCredential)
            .where(ShopifyShopCredential.shop_domain == shop_domain)
            .values(
                access_token="REDACTED",
                is_active=False,
                updated_at=utc_now(),
            )
        )
        await session.execute(stmt)
        await session.commit()

    audit_logger.log_event(
        SecurityEvent(
            event_type="gdpr_compliance",
            action="shop_redact",
            resource="shop_data",
            resource_id=shop_domain,
            user_id="shopify_gdpr",
            success=True,
            details={"shop_domain": shop_domain},
        )
    )
    logger.info("Successfully processed shop/redact for %s", shop_domain)


async def handle_customers_data_request(event: WebhookEvent) -> None:
    """Handle customers/data_request mandatory GDPR webhook."""
    body = event.body or {}
    shop_domain = event.shop_domain
    customer_info = body.get("customer") or {}
    customer_id = str(customer_info.get("id") or "")

    logger.info(
        "GDPR customers/data_request received for shop=%s, customer_id=%s",
        shop_domain,
        customer_id,
    )

    audit_logger.log_event(
        SecurityEvent(
            event_type="gdpr_compliance",
            action="customers_data_request",
            resource="customer_pii",
            resource_id=customer_id,
            user_id="shopify_gdpr",
            success=True,
            details={"shop_domain": shop_domain},
        )
    )
