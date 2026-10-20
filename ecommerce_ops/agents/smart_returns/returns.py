"""Rule-based Smart Returns Agent.

Predicts return risk using heuristic rules on order/product data.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List

from ecommerce_ops.agents._base import BaseAgent

logger = logging.getLogger("ecommerce_ops.agents.smart_returns")


class SmartReturnsAgent(BaseAgent):
    def __init__(self) -> None:
        super().__init__("SmartReturnsAgent")

    async def run(self, state: Dict[str, Any]) -> Dict[str, Any]:
        orders = state.get("pending_orders", [])
        decisions: List[Dict[str, Any]] = []

        for order in orders:
            if not isinstance(order, dict):
                continue
            order_id = order.get("order_id")
            if not order_id:
                continue

            analysis = self._analyze_return_risk(order)
            if analysis["return_risk"] < 0.3:
                continue

            decision = self.create_decision(
                action_type="FLAG_RETURN_RISK",
                reasoning=(
                    f"Order {order_id}: return_risk={analysis['return_risk']:.2f} "
                    f"({analysis['risk_level']}). Actions: {analysis['preventive_actions']}"
                ),
                data={
                    "order_id": order_id,
                    "return_risk": analysis["return_risk"],
                    "risk_level": analysis["risk_level"],
                    "preventive_actions": analysis["preventive_actions"],
                    "recommended_insurance": analysis["recommended_insurance"],
                },
                confidence=analysis["confidence"],
                requires_approval=analysis["return_risk"] > 0.5,
            )
            decisions.append(decision)
            await self.persist_decision(decision)

        state["decisions"] = state.get("decisions", []) + decisions
        return state

    def _analyze_return_risk(self, order: Dict[str, Any]) -> Dict[str, Any]:
        risk = 0.2
        categories = [c.lower() for c in order.get("categories", [])]

        if any(c in ("apparel", "clothing", "shoes", "fashion") for c in categories):
            risk += 0.3
        if int(order.get("previous_returns", 0)) > 2:
            risk += 0.2
        if float(order.get("order_total", 0)) > 200:
            risk += 0.1
        if not order.get("is_repeat_customer", False):
            risk += 0.05
        if order.get("is_gift", False):
            risk += 0.05

        risk = min(risk, 1.0)
        level = "low" if risk < 0.3 else "medium" if risk < 0.7 else "high"

        actions = []
        if risk > 0.5:
            actions.append("send_size_guide")
        if risk > 0.7:
            actions.append("require_signature")
            actions.append("offer_return_insurance")

        return {
            "return_risk": round(risk, 2),
            "risk_level": level,
            "confidence": 0.6,
            "preventive_actions": actions or ["standard_processing"],
            "recommended_insurance": risk > 0.7,
        }
