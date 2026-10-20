from typing import Any, Dict, List

import structlog

from ecommerce_ops.agents._base import BaseAgent

logger = structlog.get_logger(__name__)


class InventoryAgent(BaseAgent):
    def __init__(self):
        super().__init__("InventoryAgent")

    async def run(self, state: Dict[str, Any]) -> Dict[str, Any]:
        inventory = state.get("inventory_data", [])
        decisions = []
        memory = await self.load_memory_context(state)

        for item in inventory:
            sku = item.get("sku")
            current_stock = item.get("stock", 0)
            daily_velocity = self._calculate_velocity(sku, state.get("active_orders", []))

            if daily_velocity <= 0:
                continue

            days_left = current_stock / daily_velocity
            if days_left < 14:
                qty_to_order = int(daily_velocity * 30)
                conf = 0.9 if days_left < 7 else 0.7
                if days_left < 3:
                    conf = 0.95

                decision = self.create_decision(
                    action_type="DRAFT_PO",
                    reasoning=(
                        f"SKU {sku} has {current_stock} units left, "
                        f"daily velocity {daily_velocity:.2f}, "
                        f"predicted stockout in {days_left:.1f} days. "
                        f"Proposing order of {qty_to_order} units (30-day supply)."
                        + (f" Memory: {memory}" if memory else "")
                    ),
                    data={
                        "sku": sku,
                        "quantity_to_order": qty_to_order,
                        "supplier_id": "DEFAULT",
                        "predicted_stockout_days": days_left,
                    },
                    confidence=conf,
                )
                decisions.append(decision)
                await self.persist_decision(decision)

        state["decisions"] = state.get("decisions", []) + decisions
        return state

    def _calculate_velocity(self, sku: str, orders: List[Dict]) -> float:
        total_qty = 0
        window_days = 30
        if not orders:
            return 0.0
        for order in orders:
            for line_item in order.get("line_items", []):
                if line_item.get("sku") == sku:
                    total_qty += line_item.get("quantity", 0)
        return total_qty / window_days
