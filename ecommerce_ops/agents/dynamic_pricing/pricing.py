"""Rule-based Dynamic Pricing Agent.

Simple cost-plus pricing with competitor matching and inventory urgency.
Used as the fallback when the LLM agent is unavailable.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, Optional

from ecommerce_ops.agents._base import BaseAgent
from ecommerce_ops.config import settings
from ecommerce_ops.memory import cache
from ecommerce_ops.tools.registry import ToolRegistry

logger = logging.getLogger("ecommerce_ops.agents.dynamic_pricing")


class DynamicPricingAgent(BaseAgent):
    """Rule-based dynamic pricing agent with competitor matching."""

    def __init__(self) -> None:
        super().__init__("DynamicPricingAgent")
        self._min_margin = 0.10
        self._max_increase_pct = settings.GLOBAL_PRICE_CHANGE_LIMIT_PERCENT

    async def run(self, state: Dict[str, Any]) -> Dict[str, Any]:
        inventory = state.get("inventory_data", [])
        decisions = []

        for item in inventory:
            if not isinstance(item, dict):
                continue
            sku = item.get("sku")
            if not sku:
                continue

            current_price = float(item.get("price") or 0)
            cost = float(item.get("unit_cost") or item.get("cost") or 0)
            stock = int(item.get("stock") or 0)
            daily_sales = float(item.get("daily_sales") or 0)

            if current_price <= 0:
                continue

            competitor_price = await self._get_competitor_price(sku)

            new_price = self._calculate_price(
                current_price=current_price,
                cost=cost,
                stock=stock,
                daily_sales=daily_sales,
                competitor_price=competitor_price,
            )

            if new_price is None or abs(new_price - current_price) < 0.01:
                continue

            change_pct = abs(new_price - current_price) / current_price
            conf = 0.85 if change_pct < 0.10 else 0.70
            requires_approval = change_pct > 0.05

            strategy = self._pick_strategy(
                current_price, cost, stock, daily_sales, competitor_price
            )

            decision = self.create_decision(
                action_type="UPDATE_PRICE",
                reasoning=(
                    f"SKU {sku}: ${current_price:.2f} -> ${new_price:.2f} "
                    f"({change_pct * 100:+.1f}%). Strategy: {strategy}. "
                    f"Stock={stock}, Daily sales={daily_sales:.1f}."
                ),
                data={
                    "sku": sku,
                    "old_price": current_price,
                    "new_price": round(new_price, 2),
                    "variant_id": item.get("variant_id"),
                    "change_percent": round(change_pct * 100, 1),
                    "strategy": strategy,
                    "cost": cost,
                    "competitor_price": competitor_price,
                },
                confidence=conf,
                requires_approval=requires_approval,
            )
            decisions.append(decision)
            await self.persist_decision(decision)

        state["decisions"] = state.get("decisions", []) + decisions
        return state

    def _calculate_price(
        self,
        current_price: float,
        cost: float,
        stock: int,
        daily_sales: float,
        competitor_price: Optional[float],
    ) -> Optional[float]:
        """Calculate optimal price using multiple strategies."""
        floor = current_price * (1 - self._max_increase_pct / 100)
        ceiling = current_price * (1 + self._max_increase_pct / 100)

        # Absolute floor: never sell below cost + 10% margin
        if cost > 0:
            absolute_floor = cost * (1 + self._min_margin)
            floor = max(floor, absolute_floor)

        candidates = []

        # Strategy 1: Competitor matching
        if competitor_price is not None and competitor_price > 0:
            match_price = competitor_price * 0.98  # 2% below competitor
            match_price = max(floor, min(match_price, ceiling))
            candidates.append(("competitor_match", match_price))

        # Strategy 2: Cost-plus
        if cost > 0:
            cost_plus = cost * 1.30  # 30% margin
            cost_plus = max(floor, min(cost_plus, ceiling))
            candidates.append(("cost_plus", cost_plus))

        # Strategy 3: Inventory urgency
        if stock > 100 and daily_sales < 1:
            urgency_price = current_price * 0.90
            urgency_price = max(floor, urgency_price)
            candidates.append(("inventory_clear", urgency_price))
        elif stock > 50 and daily_sales < 2:
            urgency_price = current_price * 0.95
            urgency_price = max(floor, urgency_price)
            candidates.append(("demand_skim", urgency_price))

        if not candidates:
            return None

        # Pick best: prefer competitor_match > cost_plus > urgency
        priority = {"competitor_match": 0, "cost_plus": 1, "demand_skim": 2, "inventory_clear": 3}
        candidates.sort(key=lambda c: priority.get(c[0], 99))
        return candidates[0][1]

    def _pick_strategy(
        self,
        current_price: float,
        cost: float,
        stock: int,
        daily_sales: float,
        competitor_price: Optional[float],
    ) -> str:
        if competitor_price is not None and competitor_price < current_price:
            return "competitor_match"
        if stock > 100 and daily_sales < 1:
            return "inventory_clear"
        if stock > 50 and daily_sales < 2:
            return "demand_skim"
        return "cost_plus"

    async def _get_competitor_price(self, sku: str) -> Optional[float]:
        cache_key = f"competitor_price:{sku}"
        cached_price = await cache.get(cache_key)
        if cached_price is not None:
            return float(cached_price)

        price = await ToolRegistry.run_tool("scrape_competitor_price", sku=sku)
        if price is not None:
            await cache.set(cache_key, price, ttl=3600)
            return price
        return None
