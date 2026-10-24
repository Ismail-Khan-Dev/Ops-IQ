"""
Shopify Recurring Application Charges (Billing API)
Handles merchant SaaS subscription creation, 14-day free trial,
and charge activation required for Shopify App Store monetization.
"""

import logging
from typing import Any, Dict, Optional

from ecommerce_ops.config import Environment
from ecommerce_ops.config import settings as app_settings
from ecommerce_ops.connectors.shopify.client import ShopifyClient
from ecommerce_ops.models import ShopifyShopCredential, async_session_factory
from ecommerce_ops.utils import utc_now

logger = logging.getLogger("ecommerce_ops.connectors.shopify.billing")

TIER_PLANS = {
    "starter": {
        "name": "OpsIQ Starter Plan",
        "price": 499.00,
        "max_gmv": 1_500_000,
        "trial_days": 14,
        "features": ["Autonomous Fraud Interception", "Dynamic Pricing Agent", "Email Support"],
    },
    "growth": {
        "name": "OpsIQ Growth Plan",
        "price": 999.00,
        "max_gmv": 5_000_000,
        "trial_days": 14,
        "features": [
            "3PL Fulfillment Hold Interceptor",
            "Slack Interactive HITL Bot",
            "Klaviyo & Gorgias Event Bridges",
            "Order Swaps & Returns Engine",
            "Priority Slack Support",
        ],
    },
    "enterprise": {
        "name": "OpsIQ Enterprise Plan",
        "price": 1999.00,
        "max_gmv": 15_000_000,
        "trial_days": 14,
        "features": [
            "All 10 Domain Agents",
            "Custom ERP / 3PL Integrations",
            "Dedicated Slack Channel & SLA",
            "Custom Return Matrix Tuning",
        ],
    },
}

SHOPIFY_SUBSCRIPTION_PLANS = TIER_PLANS


class ShopifyBillingManager:
    """Manages recurring application charges for Shopify merchants."""

    def __init__(self, shop_domain: str, access_token: str):
        self.shop_domain = shop_domain
        self.access_token = access_token
        self.client = ShopifyClient(
            shop_domain=shop_domain,
            access_token=access_token,
            api_version=app_settings.SHOPIFY_API_VERSION,
        )

    @classmethod
    async def for_shop(cls, shop_domain: str) -> "ShopifyBillingManager":
        """Resolve credentials for shop and return billing manager instance."""
        async with async_session_factory() as session:
            from sqlalchemy import select

            res = await session.execute(
                select(ShopifyShopCredential).where(
                    ShopifyShopCredential.shop_domain == shop_domain,
                    ShopifyShopCredential.is_active == True,
                )
            )
            cred = res.scalar_one_or_none()

        if cred and cred.access_token:
            return cls(shop_domain=shop_domain, access_token=cred.access_token)

        if app_settings.SHOPIFY_ACCESS_TOKEN:
            return cls(
                shop_domain=shop_domain,
                access_token=app_settings.SHOPIFY_ACCESS_TOKEN.get_secret_value(),
            )

        raise ValueError(f"No active credentials found for shop {shop_domain}")

    async def create_recurring_charge(
        self,
        plan_tier: str = "growth",
        return_url: Optional[str] = None,
        test_mode: Optional[bool] = None,
    ) -> Dict[str, Any]:
        """Create a recurring application charge in Shopify and return confirmation URL."""
        plan = TIER_PLANS.get(plan_tier.lower(), TIER_PLANS["growth"])
        if test_mode is None:
            test_mode = app_settings.ENV != Environment.PRODUCTION

        if not return_url:
            return_url = f"https://{self.shop_domain}/admin/apps"

        payload = {
            "recurring_application_charge": {
                "name": plan["name"],
                "price": plan["price"],
                "return_url": return_url,
                "trial_days": plan["trial_days"],
                "test": test_mode,
            }
        }

        try:
            resp = await self.client._post_with_retry(
                "/recurring_application_charges.json", json=payload
            )
            charge = resp.get("recurring_application_charge", {})
            logger.info(
                "Created %s subscription charge (%s) for %s",
                plan["name"],
                charge.get("id"),
                self.shop_domain,
            )
            return {
                "charge_id": charge.get("id"),
                "status": charge.get("status", "pending"),
                "confirmation_url": charge.get("confirmation_url"),
                "plan": plan["name"],
                "price": plan["price"],
                "trial_days": plan["trial_days"],
            }
        finally:
            await self.client.close()

    async def activate_charge(self, charge_id: int | str) -> Dict[str, Any]:
        """Activate charge once merchant returns from approval URL."""
        try:
            resp = await self.client._post_with_retry(
                f"/recurring_application_charges/{charge_id}/activate.json", json={}
            )
            charge = resp.get("recurring_application_charge", {})
            status = charge.get("status")
            logger.info("Activated charge %s for %s: %s", charge_id, self.shop_domain, status)
            return {
                "charge_id": charge_id,
                "status": status,
                "activated": status == "active",
            }
        finally:
            await self.client.close()

    async def get_active_subscription(self) -> Dict[str, Any]:
        """Query current recurring application charges to verify active billing status."""
        try:
            resp = await self.client._get_with_retry("/recurring_application_charges.json")
            charges = resp.get("recurring_application_charges", [])
            active = next((c for c in charges if c.get("status") == "active"), None)
            if active:
                return {
                    "has_active_subscription": True,
                    "plan_name": active.get("name"),
                    "price": active.get("price"),
                    "billing_on": active.get("billing_on"),
                    "status": "active",
                }
            return {
                "has_active_subscription": False,
                "status": "no_active_charge",
                "charges_count": len(charges),
            }
        finally:
            await self.client.close()
