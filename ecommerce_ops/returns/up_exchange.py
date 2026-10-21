"""
Post-Purchase Up-Exchange AI Negotiation Engine.
Transforms profit-draining return and refund requests into retained revenue and upsells
by leveraging warehouse deadstock and dynamic tier-upgrade incentives.
"""

import logging
from typing import Any, Dict, List, Optional

logger = logging.getLogger("ecommerce_ops.returns.up_exchange")

# Default high-margin companion deadstock catalog (can be overridden by live inventory snapshots)
DEFAULT_SWEETENER_CATALOG: List[Dict[str, Any]] = [
    {
        "sku": "ACC-CSH-SCRF",
        "title": "Signature Cashmere Wool Scarf",
        "retail_price": 45.0,
        "cogs": 6.50,
        "category": "apparel",
    },
    {
        "sku": "ACC-LTHR-WAL",
        "title": "Minimalist Full-Grain Leather Cardholder",
        "retail_price": 38.0,
        "cogs": 5.00,
        "category": "apparel",
    },
    {
        "sku": "BEAUTY-HYDR-SRM",
        "title": "Hyaluronic Acid Glow Serum (30ml)",
        "retail_price": 42.0,
        "cogs": 4.80,
        "category": "beauty",
    },
]


class UpExchangeEngine:
    """Negotiates returns by generating high-converting Keep-It Sweeteners and Tier-Up Exchanges."""

    @classmethod
    def generate_up_exchange_offers(
        cls,
        item_price: float,
        title: str = "Purchased Item",
        category: str = "apparel",
        return_reason: str = "sizing_fit",
        sweetener_catalog: Optional[List[Dict[str, Any]]] = None,
    ) -> Dict[str, Any]:
        """Generates 2 win-win exchange offers before issuing a cash refund.

        Offer 1: Keep original item + get high-margin companion sweetener for a nominal fee.
        Offer 2: Tier-Up exchange to a premium product with an upgrade discount.
        """
        catalog = sweetener_catalog or DEFAULT_SWEETENER_CATALOG

        # Match companion sweetener by category
        matching_sweeteners = [it for it in catalog if it.get("category", "").lower() == category.lower()]
        sweetener = matching_sweeteners[0] if matching_sweeteners else catalog[0]

        # Standard reverse logistics loss avoided
        reverse_logistics_cost = 14.50

        # ── Offer 1: Keep-It + Companion Sweetener Bundle ────────────────────
        sweetener_retail = float(sweetener.get("retail_price", 40.0))
        sweetener_cogs = float(sweetener.get("cogs", 6.0))
        bundle_fee = 15.0  # Customer pays only $15 to keep original + get $40+ item

        # Merchant net gain compared to issuing a full cash refund:
        # Cash refund would lose item_price ($80) + reverse shipping ($14.50) = -$94.50
        # Under Offer 1: Merchant keeps original item price ($80) + receives $15 fee - $6 COGS = +$89
        net_saved_vs_refund_offer1 = round(item_price + bundle_fee - sweetener_cogs, 2)

        offer_keep_it_bundle = {
            "strategy": "KEEP_IT_SWEETENER_BUNDLE",
            "title": f"Keep your {title} + Get {sweetener['title']} for only ${bundle_fee:.0f}!",
            "description": (
                f"Love your order? Keep your {title} with zero return hassle, and add our bestselling "
                f"{sweetener['title']} (regularly ${sweetener_retail:.0f}) for just ${bundle_fee:.0f} extra."
            ),
            "customer_pays": bundle_fee,
            "sweetener_retail_value": sweetener_retail,
            "merchant_preserved_margin_usd": net_saved_vs_refund_offer1,
            "action_code": f"SWEETENER-{sweetener['sku']}",
        }

        # ── Offer 2: Tier-Up Upgrade Exchange ────────────────────────────────
        upgrade_msrp = round(item_price * 1.45, 2)  # 45% higher tier product
        regular_diff = round(upgrade_msrp - item_price, 2)
        discounted_upgrade_diff = round(regular_diff * 0.60, 2)  # 40% discount on difference

        offer_tier_up = {
            "strategy": "TIER_UP_UPGRADE_EXCHANGE",
            "title": f"Exchange for Premium Edition for only ${discounted_upgrade_diff:.2f} extra",
            "description": (
                f"Upgrade your {title} to our Premium Edition (${upgrade_msrp:.2f} value). "
                f"Instead of the standard ${regular_diff:.2f} difference, pay only ${discounted_upgrade_diff:.2f} "
                f"and we cover all shipping!"
            ),
            "customer_pays": discounted_upgrade_diff,
            "upgrade_msrp": upgrade_msrp,
            "savings_for_customer": round(regular_diff - discounted_upgrade_diff, 2),
            "merchant_preserved_margin_usd": round(item_price + discounted_upgrade_diff, 2),
            "action_code": "TIER_UP_EXCHANGE",
        }

        return {
            "original_item": {
                "title": title,
                "price": item_price,
                "category": category,
                "return_reason": return_reason,
            },
            "avoided_reverse_logistics_cost_usd": reverse_logistics_cost,
            "cash_refund_prevented_usd": item_price,
            "offers": [offer_keep_it_bundle, offer_tier_up],
            "recommendation_summary": (
                f"Propose Offer 1 ({offer_keep_it_bundle['strategy']}) first to capture ${bundle_fee:.0f} "
                f"new cash flow while saving ${reverse_logistics_cost:.2f} in reverse shipping."
            ),
        }
