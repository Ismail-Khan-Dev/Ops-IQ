"""Rule-based Order Swaps Agent.

Finds product substitutions for out-of-stock items using category + price matching.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List

from ecommerce_ops.agents._base import BaseAgent

logger = logging.getLogger("ecommerce_ops.agents.order_swaps")


class OrderSwapsAgent(BaseAgent):
    def __init__(self) -> None:
        super().__init__("OrderSwapsAgent")

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

            price_diff = float(swap.get("price") or 0) - float(item.get("original_price") or 0)
            decision = self.create_decision(
                action_type="SWAP_ITEM",
                reasoning=(
                    f"Swap {sku} -> {swap.get('sku', '?')}: "
                    f"{swap.get('name', '?')} (${swap.get('price', 0):.2f}). "
                    f"Price diff: ${price_diff:+.2f}"
                ),
                data={
                    "order_id": item.get("order_id", ""),
                    "original_sku": sku,
                    "original_name": item.get("original_name", ""),
                    "swap_sku": swap.get("sku", ""),
                    "swap_name": swap.get("name", ""),
                    "swap_price": float(swap.get("price") or 0),
                    "price_difference": round(price_diff, 2),
                    "confidence": 0.7,
                },
                confidence=0.7,
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
