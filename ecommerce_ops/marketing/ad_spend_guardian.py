"""
Ad-Spend Bleed Stopper & Meta Inventory Synchronizer.
Continuously audits Shopify inventory stock levels against running Meta / TikTok ad sets.
Immediately pauses ad sets driving traffic to sold-out SKUs and auto-unpauses upon restocking.
"""

import logging
from datetime import datetime
from typing import Any, Dict, List, Optional, Set

from ecommerce_ops.config import settings as app_settings
from ecommerce_ops.connectors.meta import MetaAdsClient
from ecommerce_ops.utils import utc_now

logger = logging.getLogger("ecommerce_ops.marketing.ad_spend_guardian")

# In-memory registry tracking paused ad sets and avoidance savings
# adset_id -> { "adset_name": str, "sku": str, "daily_budget": float, "paused_at": datetime }
_PAUSED_ADSETS: Dict[str, Dict[str, Any]] = {}


class AdSpendGuardian:
    """Synchronizes real-time product stock levels with paid ad platforms (Meta/Google)."""

    def __init__(self, meta_client: Optional[MetaAdsClient] = None):
        self.meta_client = meta_client or MetaAdsClient()

    def _matches_adset_to_sku(self, adset_name: str, sku: str, title: Optional[str] = None) -> bool:
        """Determines if an ad set is promoting a specific SKU or product title."""
        name_lower = adset_name.lower()
        if sku and sku.lower() in name_lower:
            return True
        if title:
            # Check core keywords (e.g., 'linen shirt')
            keywords = [w.strip().lower() for w in title.split() if len(w.strip()) > 3]
            if keywords and all(k in name_lower for k in keywords[:2]):
                return True
        return False

    async def sync_inventory_to_ads(
        self,
        inventory_items: List[Dict[str, Any]],
        oos_threshold: int = 0,
        auto_execute: bool = True,
    ) -> Dict[str, Any]:
        """Audits inventory items against Meta ad sets.

        Pauses ads for sold-out items and unpauses for restocked items.
        """
        adsets = await self.meta_client.get_adsets()

        paused_actions: List[Dict[str, Any]] = []
        unpaused_actions: List[Dict[str, Any]] = []
        daily_spend_saved = 0.0

        # Build quick map of SKU stock levels
        # sku -> { "qty": int, "title": str }
        stock_map: Dict[str, Dict[str, Any]] = {}
        for item in inventory_items:
            sku = str(item.get("sku", "")).strip()
            qty = int(item.get("inventory_quantity", 0))
            title = str(item.get("title", ""))
            if sku:
                stock_map[sku] = {"qty": qty, "title": title}

        for adset in adsets:
            adset_id = str(adset.get("id"))
            adset_name = str(adset.get("name", ""))
            current_status = str(adset.get("status", "")).upper()
            raw_budget = float(adset.get("daily_budget") or 0.0)
            daily_budget_usd = raw_budget / 100.0 if raw_budget > 100 else raw_budget

            # Check matching against any SKU
            for sku, stock_info in stock_map.items():
                is_match = self._matches_adset_to_sku(adset_name, sku, stock_info["title"])
                if not is_match:
                    continue

                qty = stock_info["qty"]

                # Case 1: Out of stock, but ad set is still ACTIVE -> PAUSE IT
                if qty <= oos_threshold and current_status == "ACTIVE":
                    if auto_execute:
                        await self.meta_client.pause_adset(adset_id)

                    _PAUSED_ADSETS[adset_id] = {
                        "adset_name": adset_name,
                        "sku": sku,
                        "daily_budget": daily_budget_usd,
                        "paused_at": utc_now(),
                    }
                    daily_spend_saved += daily_budget_usd
                    paused_actions.append({
                        "adset_id": adset_id,
                        "adset_name": adset_name,
                        "sku": sku,
                        "inventory_qty": qty,
                        "daily_budget_usd": daily_budget_usd,
                        "action": "PAUSED",
                        "reason": f"Inventory depleted to {qty} units (Threshold: {oos_threshold})",
                    })
                    logger.warning(
                        "🛑 [Ad-Spend Guardian] Paused ad set '%s' ($%.2f/day) due to SKU %s stockout",
                        adset_name,
                        daily_budget_usd,
                        sku,
                    )

                # Case 2: Restocked, but ad set is currently PAUSED by OpsIQ -> UNPAUSE IT
                elif qty > oos_threshold and adset_id in _PAUSED_ADSETS:
                    if auto_execute:
                        await self.meta_client.unpause_adset(adset_id)

                    paused_meta = _PAUSED_ADSETS.pop(adset_id, {})
                    unpaused_actions.append({
                        "adset_id": adset_id,
                        "adset_name": adset_name,
                        "sku": sku,
                        "inventory_qty": qty,
                        "daily_budget_usd": daily_budget_usd,
                        "action": "UNPAUSED",
                        "reason": f"Inventory restocked to {qty} units",
                    })
                    logger.info(
                        "✅ [Ad-Spend Guardian] Reactivated ad set '%s' following restock of %s",
                        adset_name,
                        sku,
                    )

        return {
            "timestamp": utc_now().isoformat(),
            "adsets_audited_count": len(adsets),
            "adsets_paused": paused_actions,
            "adsets_unpaused": unpaused_actions,
            "daily_ad_spend_saved_usd": round(daily_spend_saved, 2),
            "currently_paused_total": len(_PAUSED_ADSETS),
        }

    def get_ad_spend_saved_summary(self) -> Dict[str, Any]:
        """Calculates current running ad budget preserved from active pauses."""
        total_daily_avoided = 0.0
        active_pauses = []

        now = utc_now()
        cumulative_saved = 0.0

        for adset_id, data in _PAUSED_ADSETS.items():
            daily = data.get("daily_budget", 0.0)
            paused_at = data.get("paused_at", now)
            duration_days = max((now - paused_at).total_seconds() / 86400.0, 0.1)

            total_daily_avoided += daily
            cumul = daily * duration_days
            cumulative_saved += cumul

            active_pauses.append({
                "adset_id": adset_id,
                "adset_name": data.get("adset_name"),
                "sku": data.get("sku"),
                "daily_budget_usd": daily,
                "paused_at": paused_at.isoformat() if isinstance(paused_at, datetime) else str(paused_at),
                "saved_spend_usd": round(cumul, 2),
            })

        annual_projected_savings = total_daily_avoided * 365.0

        return {
            "currently_paused_adsets_count": len(_PAUSED_ADSETS),
            "daily_ad_spend_preserved_usd": round(total_daily_avoided, 2),
            "cumulative_ad_spend_saved_usd": round(cumulative_saved, 2),
            "annual_projected_ad_spend_preserved_usd": round(annual_projected_savings, 2),
            "paused_adsets": active_pauses,
        }
