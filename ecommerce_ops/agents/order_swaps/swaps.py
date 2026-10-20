"""Rule-based Order Swaps Agent.

Finds product substitutions for out-of-stock items using category + price matching.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List

from ecommerce_ops.agents._base import BaseAgent
from ecommerce_ops.analytics.margin_preservation import MarginPreservationCalculator

logger = logging.getLogger("ecommerce_ops.agents.order_swaps")


class OrderSwapsAgent(BaseAgent):
    def __init__(self) -> None:
        super().__init__("OrderSwapsAgent")
        self.margin_calc = MarginPreservationCalculator()

    async def run(self, state: Dict[str, Any]) -> Dict[str, Any]:
        items = state.get("out_of_stock_items", [])
        decisions: List[Dict[str, Any]] = []

        for item in items:
            if not isinstance(item, dict):
                continue
            sku = item.get("original_sku")
            if not sku:
                continue

            swap = self._find_best_swap(item)
            if swap is None:
                continue

            orig_price = float(item.get("original_price") or 0)
            swap_price = float(swap.get("price") or 0)
            price_diff = swap_price - orig_price

            unit_econ = self.margin_calc.evaluate_order_swap_unit_economics(
                original_price=orig_price,
                swap_price=swap_price,
                original_cogs=float(item.get("original_cogs") or 0),
                swap_cogs=float(swap.get("cogs") or 0),
            )

            decision = self.create_decision(
                action_type="SWAP_ITEM",
                reasoning=(
                    f"OOS Substitution: Swap {sku} -> {swap.get('sku', '?')} "
                    f"({swap.get('name', '?')} @ ${swap_price:.2f}). "
                    f"Preserves ${unit_econ['preserved_gmv']:.2f} GMV and "
                    f"${unit_econ['preserved_net_margin']:.2f} net profit (delta: {unit_econ['margin_delta']:+.2f})."
                ),
                data={
                    "order_id": item.get("order_id", ""),
                    "customer_email": item.get("customer_email", ""),
                    "original_sku": sku,
                    "original_name": item.get("original_name", ""),
                    "swap_sku": swap.get("sku", ""),
                    "swap_name": swap.get("name", ""),
                    "original_price": orig_price,
                    "swap_price": swap_price,
                    "price_difference": round(price_diff, 2),
                    "preserved_gmv": unit_econ["preserved_gmv"],
                    "preserved_margin": unit_econ["preserved_net_margin"],
                    "margin_delta": unit_econ["margin_delta"],
                    "confidence": 0.85,
                },
                confidence=0.85,
                requires_approval=True,
            )
            decisions.append(decision)
            await self.persist_decision(decision)

        state["decisions"] = state.get("decisions", []) + decisions
        return state

    def _find_best_swap(self, item: Dict[str, Any]) -> Dict[str, Any] | None:
        original_price = float(item.get("original_price") or 0)
        original_category = item.get("category", "")
        swaps = item.get("available_swaps", [])

        best = None
        best_score = -1.0
        for s in swaps:
            if s.get("stock", 0) <= 0:
                continue
            if original_category and s.get("category", "") != original_category:
                continue
            price = float(s.get("price") or 0)
            if original_price > 0:
                ratio = price / original_price
                if ratio > 1.30 or ratio < 0.70:
                    continue
            rating = float(s.get("rating") or 0)
            score = rating + (1.0 - abs(price - original_price) / max(original_price, 1))
            if score > best_score:
                best_score = score
                best = s
        return best
