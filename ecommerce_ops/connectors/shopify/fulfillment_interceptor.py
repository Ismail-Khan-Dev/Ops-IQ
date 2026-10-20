"""
Shopify 3PL Fulfillment Hold Interceptor
Prevents unauthorized 3PL warehouse picking and packing of fraudulent orders.

Traditional order tags (e.g. 'FRAUD_HOLD') are ignored by modern 3PL warehouse
management systems (ShipBob, Red Stag, Flexport, Whiplash). Modern 3PLs listen
directly to Shopify Fulfillment Orders.

This interceptor operates on Shopify's native Fulfillment Orders API:
  - GET  /admin/api/{version}/orders/{order_id}/fulfillment_orders.json
  - POST /admin/api/{version}/fulfillment_orders/{fulfillment_order_id}/hold.json
  - POST /admin/api/{version}/fulfillment_orders/{fulfillment_order_id}/release_hold.json

When an incoming order is identified as high risk (risk score >= threshold),
a fulfillment hold is placed immediately before warehouse pick tickets are printed.
"""

import logging
from typing import Any, Dict, List, Optional, Tuple

from ecommerce_ops.agents.fraud import FRAUD_RULES
from ecommerce_ops.config import settings as app_settings
from ecommerce_ops.connectors.shopify.client import ShopifyClient
from ecommerce_ops.models import ApprovalAction, async_session_factory
from ecommerce_ops.utils import utc_now

logger = logging.getLogger("ecommerce_ops.connectors.shopify.fulfillment_interceptor")


class FulfillmentHoldInterceptor:
    """Intercepter for Shopify 3PL fulfillment orders."""

    @staticmethod
    def assess_order_fraud_risk(
        order: Dict[str, Any], threshold: int = 70
    ) -> Tuple[int, List[str], bool]:
        """Assess fraud risk for an order in sub-millisecond execution time.

        Returns: (risk_score, risk_factors, should_hold)
        """
        order_id = str(order.get("id", ""))
        # Check explicit rules table first
        if order_id in FRAUD_RULES:
            rule = FRAUD_RULES[order_id]
            score = rule.get("score", 85)
            factors = list(rule.get("factors", []))
            return score, factors, score >= threshold

        base_score = 10
        factors: List[str] = []

        # Order total check
        total_price = 0.0
        try:
            total_price = float(order.get("total_price") or order.get("order_total") or 0.0)
        except (ValueError, TypeError):
            total_price = 0.0

        if total_price >= 1000.0:
            base_score += 35
            factors.append("high_order_value_over_1000")
        elif total_price >= 500.0:
            base_score += 20
            factors.append("moderate_order_value_over_500")

        # Address mismatch check
        shipping_addr = order.get("shipping_address") or {}
        billing_addr = order.get("billing_address") or {}

        if shipping_addr and billing_addr:
            s_country = (shipping_addr.get("country_code") or "").upper()
            b_country = (billing_addr.get("country_code") or "").upper()
            s_zip = (shipping_addr.get("zip") or "").strip().lower()
            b_zip = (billing_addr.get("zip") or "").strip().lower()

            if s_country and b_country and s_country != b_country:
                base_score += 40
                factors.append("international_billing_shipping_mismatch")
            elif s_zip and b_zip and s_zip != b_zip:
                base_score += 25
                factors.append("billing_shipping_postal_mismatch")

        # Line items bulk velocity check
        line_items = order.get("line_items") or []
        if len(line_items) > 8:
            base_score += 15
            factors.append("bulk_item_velocity")

        # Shopify native risk indicators (if populated in webhook)
        risk_level = str(order.get("risk_level", "")).lower()
        if risk_level == "high":
            base_score += 45
            factors.append("shopify_native_high_risk_flag")
        elif risk_level == "medium":
            base_score += 20
            factors.append("shopify_native_medium_risk_flag")

        score = min(max(base_score, 0), 100)
        should_hold = score >= threshold
        return score, factors, should_hold

    @classmethod
    async def intercept_order_for_3pl(
        cls,
        order: Dict[str, Any],
        shop_domain: Optional[str] = None,
        access_token: Optional[str] = None,
        threshold: int = 70,
        auto_hold: bool = True,
    ) -> Dict[str, Any]:
        """Evaluate order and apply instant 3PL fulfillment hold if risk breaches threshold."""
        order_id = str(order.get("id", ""))
        score, factors, should_hold = cls.assess_order_fraud_risk(order, threshold=threshold)

        result: Dict[str, Any] = {
            "order_id": order_id,
            "risk_score": score,
            "risk_factors": factors,
            "should_hold": should_hold,
            "intercepted": False,
            "held_fulfillments": [],
            "tag_applied": False,
        }

        if not should_hold or not auto_hold:
            return result

        if not shop_domain:
            shop_domain = app_settings.SHOPIFY_SHOP_DOMAIN
        if not access_token and app_settings.SHOPIFY_ACCESS_TOKEN:
            access_token = app_settings.SHOPIFY_ACCESS_TOKEN.get_secret_value()

        if not shop_domain or not access_token:
            logger.warning(
                "3PL Interceptor cannot execute live hold for order %s: Shopify not configured",
                order_id,
            )
            return result

        client = ShopifyClient(
            shop_domain=shop_domain,
            access_token=access_token,
            api_version=app_settings.SHOPIFY_API_VERSION,
        )

        try:
            # 1. Update order tags on Shopify
            existing_tags = ""
            try:
                order_resp = await client.get_order(order_id)
                existing_tags = order_resp.get("order", {}).get("tags", "")
            except Exception as e:
                logger.warning("Could not fetch tags for order %s: %s", order_id, e)

            tags_list = [t.strip() for t in existing_tags.split(",") if t.strip()]
            if "FRAUD_HOLD" not in tags_list:
                tags_list.append("FRAUD_HOLD")
            await client.update_order(order_id, {"tags": ", ".join(tags_list)})
            result["tag_applied"] = True

            # 2. Hold fulfillment orders via modern Shopify 3PL API
            notes = (
                f"OpsIQ Fast-Path 3PL Interceptor: High fraud risk score {score}/100. "
                f"Factors: {', '.join(factors)}"
            )
            held_res = await client.hold_order_fulfillments(
                order_id=order_id,
                reason="high_risk_of_fraud",
                reason_notes=notes,
            )
            result["held_fulfillments"] = held_res
            result["intercepted"] = len(held_res) > 0
            logger.info(
                "3PL Interceptor successfully held %d fulfillment orders for order %s",
                len(held_res),
                order_id,
            )
            return result
        finally:
            await client.close()

    @classmethod
    async def release_order_3pl_hold(
        cls,
        order_id: str,
        shop_domain: Optional[str] = None,
        access_token: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Release fulfillment hold on all fulfillment orders for an order and update tags."""
        if not shop_domain:
            shop_domain = app_settings.SHOPIFY_SHOP_DOMAIN
        if not access_token and app_settings.SHOPIFY_ACCESS_TOKEN:
            access_token = app_settings.SHOPIFY_ACCESS_TOKEN.get_secret_value()

        if not shop_domain or not access_token:
            return {"order_id": order_id, "success": False, "error": "Shopify not configured"}

        client = ShopifyClient(
            shop_domain=shop_domain,
            access_token=access_token,
            api_version=app_settings.SHOPIFY_API_VERSION,
        )

        try:
            # 1. Release fulfillment orders
            released = await client.release_order_fulfillments(order_id)

            # 2. Update tags: remove FRAUD_HOLD, add FRAUD_CLEARED
            existing_tags = ""
            try:
                order_resp = await client.get_order(order_id)
                existing_tags = order_resp.get("order", {}).get("tags", "")
            except Exception as e:
                logger.warning("Could not fetch tags for order %s: %s", order_id, e)

            tags_list = [
                t.strip()
                for t in existing_tags.split(",")
                if t.strip() and t.strip() != "FRAUD_HOLD"
            ]
            if "FRAUD_CLEARED" not in tags_list:
                tags_list.append("FRAUD_CLEARED")
            await client.update_order(order_id, {"tags": ", ".join(tags_list)})

            return {
                "order_id": order_id,
                "success": True,
                "released_fulfillments": released,
                "unblocked_count": len(released),
            }
        finally:
            await client.close()
