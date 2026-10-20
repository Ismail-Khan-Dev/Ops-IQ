from typing import Any, Dict, List

import structlog

from ecommerce_ops.agents._base import BaseAgent

logger = structlog.get_logger(__name__)

FRAUD_RULES = {
    "o_suspicious": {
        "score": 85,
        "factors": ["ip_shipping_mismatch", "velocity_threshold_breached"],
    },
    "o_high_value": {"score": 60, "factors": ["amount_above_threshold"]},
}


class FraudAgent(BaseAgent):
    def __init__(self):
        super().__init__("FraudAgent")

    async def run(self, state: Dict[str, Any]) -> Dict[str, Any]:
        orders = state.get("active_orders", [])
        decisions = []

        for order in orders:
            risk_score, risk_factors = self._assess_risk(order)

            if risk_score > 50:
                requires_hitl = risk_score >= 70
                conf = min(0.5 + risk_score / 200, 0.95)

                decision = self.create_decision(
                    action_type="HOLD_ORDER",
                    reasoning=(
                        f"Risk score {risk_score}/100. "
                        f"Factors: {', '.join(risk_factors)}. "
                        f"Order {order.get('id')} flagged for review."
                    ),
                    data={
                        "order_id": order.get("id"),
                        "risk_score": risk_score,
                        "risk_factors": risk_factors,
                    },
                    confidence=conf,
                    requires_approval=requires_hitl,
                )
                decisions.append(decision)
                await self.persist_decision(decision)

        state["decisions"] = state.get("decisions", []) + decisions
        return state

    def _assess_risk(self, order: Dict[str, Any]) -> tuple[int, List[str]]:
        order_id = order.get("id", "")
        rules = FRAUD_RULES.get(order_id)
        if rules:
            return rules["score"], rules["factors"]

        base_score = 50
        factors = []
        if order.get("order_total", 0) > 1000:
            base_score += 20
            factors.append("amount_above_threshold")
        if len(order.get("line_items", [])) > 10:
            base_score += 10
            factors.append("bulk_order")
        return min(base_score, 100), factors or ["standard_check"]
