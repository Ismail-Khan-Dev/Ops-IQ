"""
Abandoned Cart Recovery Agent
Analyzes abandoned carts and creates recovery campaigns.
"""

import logging
import time
from datetime import datetime
from typing import Any

from ecommerce_ops.agents._base import BaseAgent
from ecommerce_ops.agents.cart_recovery.discounts import DiscountCodeGenerator
from ecommerce_ops.agents.cart_recovery.models import (
    AbandonedCart,
    CartItem,
    CartRecoveryResult,
    CartStatus,
    CustomerProfile,
    RecoveryStrategy,
)
from ecommerce_ops.agents.cart_recovery.strategy import RecoveryStrategyEngine
from ecommerce_ops.graph.state import AgentDecision
from ecommerce_ops.utils import utc_now

logger = logging.getLogger("ecommerce_ops.agents.cart_recovery")


class AbandonedCartAgent(BaseAgent):
    """Agent that detects and recovers abandoned carts."""

    def __init__(self):
        super().__init__(agent_name="AbandonedCartAgent")
        self.strategy_engine = RecoveryStrategyEngine()
        self.discount_generator = DiscountCodeGenerator()

    async def run(self, state: dict[str, Any]) -> dict[str, Any]:
        """Run the abandoned cart analysis."""
        start_time = time.time()

        # Get abandoned carts from state
        abandoned_carts = state.get("abandoned_carts", [])
        if not abandoned_carts:
            logger.info("No abandoned carts to analyze")
            return {
                "decisions": [],
                "carts_analyzed": 0,
                "carts_recovered": 0,
                "potential_revenue": 0,
            }

        decisions = []
        recovery_results = []
        total_potential = 0.0
        carts_recovered = 0

        for cart_data in abandoned_carts:
            try:
                # Parse cart data
                cart = self._parse_cart(cart_data)

                # Analyze and create recovery decision
                decision = await self._analyze_cart(cart)
                if decision:
                    decisions.append(decision)
                    total_potential += cart.total_value

                    # Create recovery result
                    result = CartRecoveryResult(
                        cart_id=cart.id,
                        strategy_used=decision.action_data.get("strategy", RecoveryStrategy.NONE),
                        email_sent=False,
                        recovered=False,
                        revenue_recovered=0.0,
                    )
                    recovery_results.append(result)

            except Exception as e:
                logger.error("Failed to analyze cart %s: %s", cart_data.get("id", "unknown"), e)
                continue

        processing_time = (time.time() - start_time) * 1000

        # Store decisions in memory
        for decision in decisions:
            await self.persist_decision(decision)

        return {
            "decisions": decisions,
            "carts_analyzed": len(abandoned_carts),
            "carts_recovered": carts_recovered,
            "total_potential_revenue": round(total_potential, 2),
            "processing_time_ms": round(processing_time, 2),
            "recovery_results": [r.model_dump() for r in recovery_results],
        }

    async def _analyze_cart(self, cart: AbandonedCart) -> AgentDecision | None:
        """Analyze a single cart and create a recovery decision."""
        if not cart.is_recoverable:
            logger.debug("Cart %s is not recoverable (status: %s)", cart.id, cart.status)
            return None

        # Get strategy recommendation
        recommendation = self.strategy_engine.get_strategy_recommendation(cart)

        # Generate discount code
        code = None
        if recommendation["strategy"] in (
            RecoveryStrategy.DISCOUNT_PERCENT,
            RecoveryStrategy.DISCOUNT_FIXED,
            RecoveryStrategy.FREE_SHIPPING,
        ):
            code = self.discount_generator.generate_code(
                cart,
                recommendation["strategy"],
                recommendation["discount_value"],
            )

        # Get email context
        email_context = self.discount_generator.get_recovery_email_context(
            cart,
            code or "REC-CODE",
            recommendation["strategy"],
            recommendation["discount_value"],
        )

        # Determine if this needs human approval
        requires_approval = self._requires_approval(cart, recommendation)

        # Create decision
        action_data = {
            "cart_id": cart.id,
            "shop_domain": cart.shop_domain,
            "customer_email": cart.customer.email if cart.customer else None,
            "total_value": cart.total_value,
            "items_count": cart.items_count,
            "strategy": recommendation["strategy"].value,
            "risk_level": recommendation["risk_level"].value,
            "discount_code": code,
            "discount_value": recommendation["discount_value"],
            "recovery_probability": round(cart.recovery_probability, 3),
            "estimated_revenue": round(recommendation["estimated_revenue"], 2),
            "email_context": email_context,
            "reasoning": recommendation["reasoning"],
            "checkout_url": cart.checkout_url,
        }

        return self.create_decision(
            action_type="recover_cart",
            reasoning=f"Abandoned cart (${cart.total_value:.2f}) with {cart.items_count} items. "
            f"Strategy: {recommendation['strategy'].value}. "
            f"Recovery probability: {cart.recovery_probability:.1%}. "
            f"Estimated revenue: ${recommendation['estimated_revenue']:.2f}.",
            data=action_data,
            confidence=cart.recovery_probability,
            requires_approval=requires_approval,
        )

    def _parse_cart(self, cart_data: dict[str, Any]) -> AbandonedCart:
        """Parse raw cart data into AbandonedCart model."""
        # Parse items
        items = []
        for item_data in cart_data.get("items", []):
            items.append(
                CartItem(
                    product_id=item_data.get("product_id", 0),
                    variant_id=item_data.get("variant_id", 0),
                    title=item_data.get("title", "Unknown"),
                    sku=item_data.get("sku"),
                    quantity=item_data.get("quantity", 1),
                    price=item_data.get("price", 0.0),
                    total=item_data.get("total", 0.0),
                    image_url=item_data.get("image_url"),
                    product_type=item_data.get("product_type"),
                    vendor=item_data.get("vendor"),
                )
            )

        # Parse customer
        customer = None
        if cart_data.get("customer"):
            c = cart_data["customer"]
            customer = CustomerProfile(
                id=c.get("id"),
                email=c.get("email"),
                first_name=c.get("first_name"),
                last_name=c.get("last_name"),
                total_orders=c.get("total_orders", 0),
                total_spent=c.get("total_spent", 0.0),
                average_order_value=c.get("average_order_value", 0.0),
                last_order_date=c.get("last_order_date"),
                is_repeat_customer=c.get("is_repeat_customer", False),
                segment=c.get("segment", "new"),
                tags=c.get("tags", []),
            )

        # Parse timestamps
        created_at = cart_data.get("created_at")
        if isinstance(created_at, str):
            created_at = datetime.fromisoformat(created_at.replace("Z", "+00:00"))

        abandoned_at = cart_data.get("abandoned_at")
        if isinstance(abandoned_at, str):
            abandoned_at = datetime.fromisoformat(abandoned_at.replace("Z", "+00:00"))

        return AbandonedCart(
            id=cart_data.get("id", "unknown"),
            shop_domain=cart_data.get("shop_domain", "unknown"),
            checkout_token=cart_data.get("checkout_token"),
            customer=customer,
            items=items,
            total_value=cart_data.get("total_value", 0.0),
            currency=cart_data.get("currency", "USD"),
            items_count=cart_data.get("items_count", len(items)),
            status=CartStatus(cart_data.get("status", "abandoned")),
            created_at=created_at or utc_now(),
            abandoned_at=abandoned_at,
            checkout_url=cart_data.get("checkout_url"),
            metadata=cart_data.get("metadata", {}),
        )

    def _requires_approval(self, cart: AbandonedCart, recommendation: dict[str, Any]) -> bool:
        """Determine if recovery action needs human approval."""
        # High-value carts need approval
        if cart.total_value > 200:
            return True

        # VIP customers need approval
        if cart.customer and cart.customer.lifetime_value_tier == "vip":
            return True

        # Large discounts need approval
        if recommendation["discount_value"] > 20:
            return True

        # Low confidence needs approval
        return recommendation["recovery_probability"] < 0.3

    async def generate_recovery_report(self, results: list[dict[str, Any]]) -> dict[str, Any]:
        """Generate aggregate recovery report."""
        total_carts = len(results)
        total_value = sum(r.get("total_value", 0) for r in results)
        recovered = sum(1 for r in results if r.get("recovered"))
        revenue_recovered = sum(r.get("revenue_recovered", 0) for r in results)

        # Strategy breakdown
        strategies = {}
        for r in results:
            strategy = r.get("strategy_used", "unknown")
            if strategy not in strategies:
                strategies[strategy] = {"count": 0, "value": 0}
            strategies[strategy]["count"] += 1
            strategies[strategy]["value"] += r.get("total_value", 0)

        return {
            "period": "last_24_hours",
            "summary": {
                "total_abandoned": total_carts,
                "total_recovered": recovered,
                "recovery_rate": round(recovered / total_carts * 100, 1) if total_carts > 0 else 0,
                "total_value_abandoned": round(total_value, 2),
                "total_revenue_recovered": round(revenue_recovered, 2),
                "recovery_rate_value": round(revenue_recovered / total_value * 100, 1)
                if total_value > 0
                else 0,
            },
            "strategies": strategies,
        }
