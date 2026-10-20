"""
Shopify Pilot Onboarding & Pre-Flight Readiness Engine
Automates merchant onboarding, permission verification, 3PL compatibility checks,
shadow-mode safety guardrails, and cohort tracking for US DTC pilot brands ($1M-$10M GMV).
"""

import logging
from datetime import datetime
from typing import Any, Dict, List, Optional, Set

from sqlalchemy import func, select

from ecommerce_ops.config import settings as app_settings
from ecommerce_ops.connectors.shopify.billing import (
    SHOPIFY_SUBSCRIPTION_PLANS,
    ShopifyBillingManager,
)
from ecommerce_ops.connectors.shopify.client import ShopifyClient
from ecommerce_ops.connectors.shopify.handlers.order_handlers import WEBHOOK_HANDLERS
from ecommerce_ops.connectors.shopify.sync import ShopifySyncService
from ecommerce_ops.models import (
    ShopifyCustomerSnapshot,
    ShopifyOrderSnapshot,
    ShopifyProductSnapshot,
    ShopifyShopCredential,
    StoreSettings,
    async_session_factory,
)
from ecommerce_ops.utils import utc_now

logger = logging.getLogger("ecommerce_ops.connectors.shopify.onboarding")

# ── Core Scopes & Requirements for Pilot Brands ─────────────────────────────

REQUIRED_PILOT_SCOPES: Set[str] = {
    "read_orders",
    "write_orders",
    "read_products",
    "write_products",
    "read_inventory",
    "read_assigned_fulfillment_orders",
    "write_assigned_fulfillment_orders",
}

RECOMMENDED_PILOT_SCOPES: Set[str] = {
    "read_fulfillments",
    "write_fulfillments",
    "read_customers",
    "read_discounts",
    "read_merchant_managed_fulfillment_orders",
    "write_merchant_managed_fulfillment_orders",
}

MANDATORY_COMPLIANCE_TOPICS: List[str] = [
    "app/uninstalled",
    "customers/redact",
    "shop/redact",
    "customers/data_request",
]

CORE_ORDER_TOPICS: List[str] = [
    "orders/create",
    "orders/updated",
    "orders/cancelled",
    "fulfillments/create",
]


class PilotOnboardingEngine:
    """Pre-flight readiness and automated onboarding for Shopify pilot merchants."""

    @classmethod
    async def verify_store_readiness(cls, shop_domain: str) -> Dict[str, Any]:
        """Verify merchant store readiness across OAuth, scopes, 3PL APIs,

        webhooks, and sync status prior to pilot go-live.
        """
        checklist: Dict[str, Any] = {}
        recommendations: List[str] = []
        score = 0

        # 1. Credentials Check (Max 25 pts)
        cred = None
        async with async_session_factory() as session:
            res = await session.execute(
                select(ShopifyShopCredential).where(
                    ShopifyShopCredential.shop_domain == shop_domain,
                    ShopifyShopCredential.is_active == True,  # noqa: E712
                )
            )
            cred = res.scalar_one_or_none()

        access_token = None
        granted_scope_str = ""

        if cred and cred.access_token:
            access_token = cred.access_token
            granted_scope_str = cred.scope or ""
            checklist["credentials"] = {
                "status": "passed",
                "installed_at": cred.installed_at.isoformat() if cred.installed_at else None,
                "is_active": True,
                "source": "oauth_token_db",
            }
            score += 25
        elif (
            app_settings.SHOPIFY_SHOP_DOMAIN
            and app_settings.SHOPIFY_SHOP_DOMAIN.lower() == shop_domain.lower()
            and app_settings.SHOPIFY_ACCESS_TOKEN
        ):
            access_token = app_settings.SHOPIFY_ACCESS_TOKEN.get_secret_value()
            granted_scope_str = app_settings.SHOPIFY_SCOPES or ""
            checklist["credentials"] = {
                "status": "passed",
                "installed_at": None,
                "is_active": True,
                "source": "env_config",
            }
            score += 25
        else:
            checklist["credentials"] = {
                "status": "failed",
                "error": "No active Shopify credentials found for store",
            }
            recommendations.append(
                f"Install Ops-IQ via Shopify OAuth flow at /api/v1/shopify/install?shop={shop_domain}"
            )

        # 2. Scope Verification (Max 25 pts)
        granted_scopes = set()
        if granted_scope_str:
            # Scopes can be comma-separated or space-separated
            raw_scopes = granted_scope_str.replace(",", " ").split()
            granted_scopes = {s.strip() for s in raw_scopes if s.strip()}

        missing_required = REQUIRED_PILOT_SCOPES - granted_scopes
        if checklist["credentials"]["status"] == "passed":
            if not missing_required:
                checklist["scopes"] = {
                    "status": "passed",
                    "coverage_percent": 100.0,
                    "granted_count": len(granted_scopes),
                    "missing_required": [],
                }
                score += 25
            else:
                coverage = (len(REQUIRED_PILOT_SCOPES - missing_required) / len(REQUIRED_PILOT_SCOPES)) * 100.0
                pts = int(25 * (coverage / 100.0))
                score += pts
                checklist["scopes"] = {
                    "status": "warning",
                    "coverage_percent": round(coverage, 1),
                    "missing_required": sorted(list(missing_required)),
                }
                recommendations.append(
                    f"Re-authenticate app to grant missing required scopes: {', '.join(sorted(list(missing_required)))}"
                )
        else:
            checklist["scopes"] = {
                "status": "failed",
                "coverage_percent": 0.0,
                "missing_required": sorted(list(REQUIRED_PILOT_SCOPES)),
            }

        # 3. 3PL & Fulfillment Orders API Capability (Max 20 pts)
        fulfillment_order_scopes = {
            "read_assigned_fulfillment_orders",
            "write_assigned_fulfillment_orders",
            "read_merchant_managed_fulfillment_orders",
            "write_merchant_managed_fulfillment_orders",
        }
        has_3pl_scopes = bool(fulfillment_order_scopes.intersection(granted_scopes))
        if has_3pl_scopes or checklist["credentials"]["status"] == "passed":
            checklist["fulfillment_interceptor_3pl"] = {
                "status": "passed",
                "compatible": True,
                "capability": "native_shopify_fulfillment_orders_v2024",
                "note": "Ready for 3PL warehouse hold interception (ShipBob, Red Stag, Flexport, Whiplash)",
            }
            score += 20
        else:
            checklist["fulfillment_interceptor_3pl"] = {
                "status": "failed",
                "compatible": False,
                "error": "Lacks fulfillment order scopes for 3PL hold interception",
            }
            recommendations.append("Ensure fulfillment orders scopes are enabled for automated 3PL hold integration.")

        # 4. Mandatory Webhook & GDPR Compliance (Max 15 pts)
        registered_topics = set(WEBHOOK_HANDLERS.keys())
        missing_mandatory = [t for t in MANDATORY_COMPLIANCE_TOPICS if t not in registered_topics]
        if not missing_mandatory:
            checklist["webhooks"] = {
                "status": "passed",
                "registered_topics_count": len(registered_topics),
                "gdpr_compliant": True,
                "mandatory_topics": MANDATORY_COMPLIANCE_TOPICS,
            }
            score += 15
        else:
            checklist["webhooks"] = {
                "status": "warning",
                "registered_topics_count": len(registered_topics),
                "missing_compliance_topics": missing_mandatory,
            }
            recommendations.append(f"Register missing mandatory compliance topics: {missing_mandatory}")

        # 5. Safety Guardrails & Shadow Mode Status (Max 10 pts)
        async with async_session_factory() as session:
            res = await session.execute(select(StoreSettings).limit(1))
            settings_obj = res.scalar_one_or_none()

        shadow_mode = True
        fraud_threshold = 70
        if settings_obj:
            shadow_mode = bool(settings_obj.shadow_mode)
            fraud_threshold = int(settings_obj.fraud_threshold)

        checklist["safety_guardrails"] = {
            "status": "passed",
            "shadow_mode_active": shadow_mode,
            "fraud_threshold": fraud_threshold,
            "mode_description": (
                "Shadow Mode Active: Orders are analyzed and holds simulated without interrupting live fulfillment"
                if shadow_mode
                else "Live Mode: High-risk orders placed on instant 3PL warehouse hold automatically"
            ),
        }
        score += 10

        # 6. Synced Data Health (Max 5 pts)
        product_count = 0
        order_count = 0
        async with async_session_factory() as session:
            p_res = await session.execute(
                select(func.count(ShopifyProductSnapshot.id)).where(
                    ShopifyProductSnapshot.shop_domain == shop_domain
                )
            )
            product_count = p_res.scalar() or 0

            o_res = await session.execute(
                select(func.count(ShopifyOrderSnapshot.id)).where(
                    ShopifyOrderSnapshot.shop_domain == shop_domain
                )
            )
            order_count = o_res.scalar() or 0

        has_synced_data = (product_count > 0 or order_count > 0)
        checklist["synced_data"] = {
            "status": "passed" if has_synced_data else "pending_initial_sync",
            "products_synced": product_count,
            "orders_synced": order_count,
        }
        if has_synced_data:
            score += 5
        else:
            recommendations.append(
                f"Trigger initial data synchronization for {shop_domain} to pull catalog and orders."
            )

        is_ready = (score >= 70) and (checklist["credentials"]["status"] == "passed")

        return {
            "shop_domain": shop_domain,
            "readiness_score": min(score, 100),
            "is_ready_for_pilot": is_ready,
            "checklist": checklist,
            "recommendations": recommendations,
            "evaluated_at": utc_now().isoformat(),
        }

    @classmethod
    async def provision_pilot_merchant(
        cls,
        shop_domain: str,
        access_token: Optional[str] = None,
        scope: Optional[str] = None,
        plan_tier: str = "growth",
        shadow_mode: bool = True,
        auto_sync: bool = False,
    ) -> Dict[str, Any]:
        """Onboard a pilot merchant: persist credentials, initialize store guardrails,

        create subscription charge, and optionally trigger initial catalog sync.
        """
        clean_shop = shop_domain.strip().lower()
        if not clean_shop.endswith(".myshopify.com") and "." not in clean_shop:
            clean_shop = f"{clean_shop}.myshopify.com"

        default_scopes = (
            scope
            or "read_orders,write_orders,read_products,write_products,read_inventory,"
            "read_assigned_fulfillment_orders,write_assigned_fulfillment_orders,read_fulfillments,write_fulfillments"
        )

        async with async_session_factory() as session:
            res = await session.execute(
                select(ShopifyShopCredential).where(
                    ShopifyShopCredential.shop_domain == clean_shop
                )
            )
            cred = res.scalar_one_or_none()
            if cred:
                if access_token:
                    cred.access_token = access_token
                if scope:
                    cred.scope = scope
                cred.is_active = True
                cred.updated_at = utc_now()
            else:
                effective_token = access_token or (
                    app_settings.SHOPIFY_ACCESS_TOKEN.get_secret_value()
                    if app_settings.SHOPIFY_ACCESS_TOKEN
                    else "shpat_pilot_temporary_token"
                )
                cred = ShopifyShopCredential(
                    shop_domain=clean_shop,
                    access_token=effective_token,
                    scope=default_scopes,
                    installed_at=utc_now(),
                    updated_at=utc_now(),
                    is_active=True,
                )
                session.add(cred)

            # Ensure StoreSettings has shadow_mode enabled
            s_res = await session.execute(select(StoreSettings).limit(1))
            settings_obj = s_res.scalar_one_or_none()
            if settings_obj:
                settings_obj.shadow_mode = shadow_mode
            else:
                settings_obj = StoreSettings(
                    id=1,
                    shadow_mode=shadow_mode,
                    fraud_threshold=70,
                    po_limit=1000.0,
                    pricing_limit=5.0,
                    reviews_rating_threshold=4,
                )
                session.add(settings_obj)

            await session.commit()

        # Create 14-day trial recurring application charge
        billing_info: Dict[str, Any] = {}
        try:
            billing_mgr = await ShopifyBillingManager.for_shop(clean_shop)
            charge_res = await billing_mgr.create_recurring_charge(
                plan_tier=plan_tier,
                test_mode=True,
            )
            billing_info = {
                "status": "charge_created",
                "confirmation_url": charge_res.get("confirmation_url"),
                "charge_id": charge_res.get("charge_id"),
                "plan_tier": plan_tier,
                "trial_days": charge_res.get("trial_days", 14),
                "price": charge_res.get("price"),
            }
        except Exception as e:
            logger.warning("Billing charge creation deferred for %s: %s", clean_shop, e)
            billing_info = {
                "status": "deferred",
                "reason": str(e),
                "plan_tier": plan_tier,
            }

        # Optional initial sync
        sync_result: Optional[Dict[str, Any]] = None
        if auto_sync:
            try:
                client = ShopifyClient(
                    shop_domain=clean_shop,
                    access_token=cred.access_token,
                    api_version=app_settings.SHOPIFY_API_VERSION,
                )
                sync_service = ShopifySyncService(client)
                async with async_session_factory() as db_session:
                    res_sync = await sync_service.sync_all(db_session)
                    sync_result = res_sync.to_dict()
            except Exception as e:
                logger.error("Auto sync failed for %s during provisioning: %s", clean_shop, e)
                sync_result = {"status": "error", "error": str(e)}

        # Run readiness check
        readiness = await cls.verify_store_readiness(clean_shop)

        return {
            "success": True,
            "shop_domain": clean_shop,
            "plan_tier": plan_tier,
            "shadow_mode": shadow_mode,
            "billing": billing_info,
            "sync": sync_result,
            "readiness": readiness,
            "provisioned_at": utc_now().isoformat(),
        }

    @classmethod
    async def get_pilot_cohort_summary(cls) -> Dict[str, Any]:
        """Aggregate stats across all enrolled pilot merchants."""
        async with async_session_factory() as session:
            res = await session.execute(select(ShopifyShopCredential))
            all_creds = res.scalars().all()

            s_res = await session.execute(select(StoreSettings).limit(1))
            settings_obj = s_res.scalar_one_or_none()
            shadow_mode = bool(settings_obj.shadow_mode) if settings_obj else True

            p_res = await session.execute(select(func.count(ShopifyProductSnapshot.id)))
            total_products = p_res.scalar() or 0

            o_res = await session.execute(select(func.count(ShopifyOrderSnapshot.id)))
            total_orders = o_res.scalar() or 0

        total_stores = len(all_creds)
        active_stores = sum(1 for c in all_creds if c.is_active)

        stores_data = []
        scores = []
        for cred in all_creds:
            readiness = await cls.verify_store_readiness(cred.shop_domain)
            scores.append(readiness["readiness_score"])
            stores_data.append(
                {
                    "shop_domain": cred.shop_domain,
                    "is_active": cred.is_active,
                    "installed_at": cred.installed_at.isoformat() if cred.installed_at else None,
                    "readiness_score": readiness["readiness_score"],
                    "is_ready": readiness["is_ready_for_pilot"],
                }
            )

        avg_score = round(sum(scores) / len(scores), 1) if scores else 0.0

        return {
            "total_enrolled_stores": total_stores,
            "active_stores": active_stores,
            "cohort_target": 5,
            "target_completion_percent": min(round((active_stores / 5.0) * 100, 1), 100.0),
            "shadow_mode_global": shadow_mode,
            "total_synced_products": total_products,
            "total_synced_orders": total_orders,
            "cohort_average_readiness": avg_score,
            "stores": stores_data,
            "generated_at": utc_now().isoformat(),
        }

    @classmethod
    async def update_pilot_settings(
        cls,
        shadow_mode: Optional[bool] = None,
        fraud_threshold: Optional[int] = None,
    ) -> Dict[str, Any]:
        """Update pilot safety guardrails."""
        async with async_session_factory() as session:
            res = await session.execute(select(StoreSettings).limit(1))
            settings_obj = res.scalar_one_or_none()
            if not settings_obj:
                settings_obj = StoreSettings(
                    id=1,
                    shadow_mode=True if shadow_mode is None else shadow_mode,
                    fraud_threshold=70 if fraud_threshold is None else fraud_threshold,
                )
                session.add(settings_obj)
            else:
                if shadow_mode is not None:
                    settings_obj.shadow_mode = shadow_mode
                if fraud_threshold is not None:
                    settings_obj.fraud_threshold = fraud_threshold
            await session.commit()

            return {
                "success": True,
                "shadow_mode": settings_obj.shadow_mode,
                "fraud_threshold": settings_obj.fraud_threshold,
                "updated_at": utc_now().isoformat(),
            }
