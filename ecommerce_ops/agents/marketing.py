from typing import Any, Dict

import structlog

from ecommerce_ops.agents._base import BaseAgent

logger = structlog.get_logger(__name__)


class MarketingAgent(BaseAgent):
    def __init__(self):
        super().__init__("MarketingAgent")

    async def run(self, state: Dict[str, Any]) -> Dict[str, Any]:
        inventory = state.get("inventory_data", [])
        decisions = []

        for item in inventory:
            stock = item.get("stock", 0)
            sku = item.get("sku")

            if 0 < stock < 20:
                urgency = "critical" if stock < 5 else "moderate"
                conf = 0.85 if urgency == "critical" else 0.75

                decision = self.create_decision(
                    action_type="DRAFT_MARKETING_CAMPAIGN",
                    reasoning=(
                        f"SKU {sku} has low stock ({stock} units, {urgency}). "
                        f"Proposing 'Last Chance' campaign via Email channel."
                    ),
                    data={
                        "sku": sku,
                        "channel": "Email",
                        "urgency": urgency,
                        "draft_copy": (
                            f"Hurry! Only {stock} left of {sku}. Get yours before they are gone!"
                        ),
                    },
                    confidence=conf,
                    requires_approval=True,
                )
                decisions.append(decision)
                await self.persist_decision(decision)

        state["decisions"] = state.get("decisions", []) + decisions
        return state
