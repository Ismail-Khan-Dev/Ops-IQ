from typing import Any, Dict, Optional

import structlog

from ecommerce_ops.agents._base import BaseAgent
from ecommerce_ops.config import settings
from ecommerce_ops.memory import cache
from ecommerce_ops.tools.registry import ToolRegistry

logger = structlog.get_logger(__name__)


class PricingAgent(BaseAgent):
    def __init__(self):
        super().__init__("PricingAgent")

    async def run(self, state: Dict[str, Any]) -> Dict[str, Any]:
        inventory = state.get("inventory_data", [])
        decisions = []

        for item in inventory:
            current_price = float(item.get("price", 0))
            sku = item.get("sku")

            competitor_price = await self._get_competitor_price(sku)

            floor = current_price * (1 - settings.GLOBAL_PRICE_CHANGE_LIMIT_PERCENT / 100)
            ceiling = current_price * (1 + settings.GLOBAL_PRICE_CHANGE_LIMIT_PERCENT / 100)

            if competitor_price is None:
                logger.info("Skipping %s: no competitor price available", sku)
                continue

            if competitor_price < current_price:
                new_price = max(competitor_price, floor)
                if new_price != current_price:
                    change_pct = abs(new_price - current_price) / current_price
                    conf = 0.85 if change_pct < 0.10 else 0.75
                    requires_approval = change_pct > 0.05

                    decision = self.create_decision(
                        action_type="UPDATE_PRICE",
                        reasoning=(
                            f"SKU {sku}: competitor ${competitor_price:.2f} vs current ${current_price:.2f}. "
                            f"Adjusting to ${new_price:.2f} (change: {change_pct * 100:.1f}%). "
                            f"Floor=${floor:.2f} Ceiling=${ceiling:.2f}."
                        ),
                        data={
                            "sku": sku,
                            "old_price": current_price,
                            "new_price": new_price,
                            "variant_id": item.get("variant_id"),
                            "change_percent": round(change_pct * 100, 1),
                        },
                        confidence=conf,
                        requires_approval=requires_approval,
                    )
                    decisions.append(decision)
                    await self.persist_decision(decision)

        state["decisions"] = state.get("decisions", []) + decisions
        return state

    async def _get_competitor_price(self, sku: str) -> Optional[float]:
        cache_key = f"competitor_price:{sku}"
        cached_price = await cache.get(cache_key)
        if cached_price is not None:
            logger.info("Cache hit for %s competitor price: %s", sku, cached_price)
            return float(cached_price)

        price = await ToolRegistry.run_tool("scrape_competitor_price", sku=sku)
        if price is not None:
            await cache.set(cache_key, price, ttl=3600)
            return price

        logger.warning("No competitor price available for %s", sku)
        return None
