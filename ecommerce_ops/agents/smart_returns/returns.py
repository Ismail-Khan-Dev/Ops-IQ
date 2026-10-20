"""Rule-based Smart Returns Agent.

Predicts return risk using heuristic rules on order/product data.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List

from ecommerce_ops.agents._base import BaseAgent
from ecommerce_ops.analytics.margin_preservation import MarginPreservationCalculator

logger = logging.getLogger("ecommerce_ops.agents.smart_returns")


class SmartReturnsAgent(BaseAgent):
    def __init__(self) -> None:
        super().__init__("SmartReturnsAgent")
        self.margin_calc = MarginPreservationCalculator()

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

            unit_econ = self.margin_calc.evaluate_return_unit_economics(
                item_price=float(order.get("order_total") or order.get("item_price") or 50.0),
                category=str(
                    order.get("category")
                    or (order.get("categories", ["apparel"])[0] if order.get("categories") else "apparel")
                ),
                return_reason=str(order.get("return_reason") or "sizing_fit"),
                customer_is_vip=bool(order.get("is_repeat_customer", False)),
            )

            actions = list(analysis["preventive_actions"])
            if unit_econ["strategy"] == "keep_it_credit":
                actions.insert(0, "offer_keep_it_store_credit")
            elif unit_econ["strategy"] == "instant_exchange":
                actions.insert(0, "offer_instant_variant_exchange")

            decision = self.create_decision(
                action_type="FLAG_RETURN_RISK",
                reasoning=(
                    f"Return Strategy [{unit_econ['strategy'].upper()}]: Return risk={analysis['return_risk']:.2f} "
                    f"({analysis['risk_level']}). {unit_econ['recommendation_reason']} "
                    f"Preserves ${unit_econ['preserved_margin']:.2f} net margin."
                ),
                data={
                    "order_id": order_id,
                    "customer_email": order.get("customer_email") or order.get("email"),
                    "return_risk": analysis["return_risk"],
                    "risk_level": analysis["risk_level"],
                    "strategy": unit_econ["strategy"],
                    "preserved_margin": unit_econ["preserved_margin"],
                    "reverse_costs_saved": unit_econ["avoided_reverse_costs"],
                    "total_physical_return_cost": unit_econ["total_physical_return_cost"],
                    "preventive_actions": actions,
                    "recommended_insurance": analysis["recommended_insurance"],
                },
                confidence=max(analysis["confidence"], 0.75),
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
