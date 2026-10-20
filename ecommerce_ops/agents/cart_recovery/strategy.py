"""
Recovery Strategy Engine
Analyzes cart data and selects optimal recovery strategy.
"""

import logging
from typing import Any, ClassVar, Dict, List, Optional, Tuple

from ecommerce_ops.agents.cart_recovery.models import (
    AbandonedCart,
    CartRiskLevel,
    RecoveryStrategy,
)

logger = logging.getLogger("ecommerce_ops.agents.cart_recovery.strategy")


class StrategyConfig:
    """Configuration for recovery strategies."""

    # Discount thresholds by cart value
    DISCOUNT_THRESHOLDS: ClassVar[Dict[str, Dict[str, float]]] = {
        "low": {"min": 0, "max": 50, "percent": 5, "fixed": 2.0},
        "medium": {"min": 50, "max": 150, "percent": 10, "fixed": 5.0},
        "high": {"min": 150, "max": 500, "percent": 15, "fixed": 15.0},
        "vip": {"min": 500, "max": float("inf"), "percent": 20, "fixed": 50.0},
    }

    # Risk thresholds
    RISK_THRESHOLDS: ClassVar[Dict[CartRiskLevel, Dict[str, float]]] = {
        CartRiskLevel.LOW: {"max_hours": 2, "min_value": 0},
        CartRiskLevel.MEDIUM: {"max_hours": 24, "min_value": 25},
        CartRiskLevel.HIGH: {"max_hours": 72, "min_value": 100},
        CartRiskLevel.CRITICAL: {"max_hours": 168, "min_value": 200},
    }

    # Strategy effectiveness weights (can be tuned based on data)
    STRATEGY_WEIGHTS: ClassVar[Dict[RecoveryStrategy, float]] = {
        RecoveryStrategy.DISCOUNT_PERCENT: 0.35,
        RecoveryStrategy.DISCOUNT_FIXED: 0.25,
        RecoveryStrategy.FREE_SHIPPING: 0.20,
        RecoveryStrategy.URGENCY: 0.10,
        RecoveryStrategy.SOCIAL_PROOF: 0.05,
        RecoveryStrategy.PERSONAL_OUTREACH: 0.05,
    }


class RecoveryStrategyEngine:
    """Selects optimal recovery strategy based on cart and customer data."""

    def __init__(self, config: Optional[StrategyConfig] = None):
        self.config = config or StrategyConfig()

    def assess_risk(self, cart: AbandonedCart) -> CartRiskLevel:
        """Assess cart risk level based on value and time abandoned."""
        hours = cart.time_abandoned_hours or 0
        value = cart.total_value

        if hours < 2 and value < 50:
            return CartRiskLevel.LOW
        elif hours < 24 and value < 150:
            return CartRiskLevel.MEDIUM
        elif hours < 72 or value >= 150:
            return CartRiskLevel.HIGH
        else:
            return CartRiskLevel.CRITICAL

    def calculate_discount(
        self, cart: AbandonedCart, strategy: RecoveryStrategy
    ) -> Tuple[float, str]:
        """Calculate optimal discount value and code prefix."""
        value = cart.total_value

        # Determine tier
        tier = "low"
        for tier_name, threshold in self.config.DISCOUNT_THRESHOLDS.items():
            if threshold["min"] <= value < threshold["max"]:
                tier = tier_name
                break

        # Adjust for customer segment
        if cart.customer:
            if cart.customer.is_repeat_customer:
                # Loyal customers get slightly better deals
                tier = self._upgrade_tier(tier)
            if cart.customer.segment == "vip":
                tier = "vip"

        discount_config = self.config.DISCOUNT_THRESHOLDS[tier]

        if strategy == RecoveryStrategy.DISCOUNT_PERCENT:
            return discount_config["percent"], f"{discount_config['percent']}OFF"
        elif strategy == RecoveryStrategy.DISCOUNT_FIXED:
            return discount_config["fixed"], f"${discount_config['fixed']:.0f}OFF"
        elif strategy == RecoveryStrategy.FREE_SHIPPING:
            return 0.0, "FREESHIP"
        else:
            return 0.0, "RECOVER"

    def select_strategy(self, cart: AbandonedCart) -> RecoveryStrategy:
        """Select optimal recovery strategy based on cart analysis."""
        # If cart value is too low, don't offer discount
        if cart.total_value < 10:
            logger.debug("Cart value too low for discount: $%.2f", cart.total_value)
            return RecoveryStrategy.SOCIAL_PROOF

        # Customer-based strategy
        if cart.customer:
            if cart.customer.is_repeat_customer and cart.customer.total_orders > 10:
                return RecoveryStrategy.PERSONAL_OUTREACH

            if cart.customer.lifetime_value_tier == "vip":
                return RecoveryStrategy.DISCOUNT_PERCENT

        # Value-based strategy
        if cart.total_value > 200:
            return RecoveryStrategy.DISCOUNT_PERCENT
        elif cart.total_value > 100:
            return RecoveryStrategy.FREE_SHIPPING
        elif cart.total_value > 50:
            return RecoveryStrategy.DISCOUNT_FIXED
        else:
            return RecoveryStrategy.DISCOUNT_PERCENT

    def get_strategy_recommendation(self, cart: AbandonedCart) -> Dict[str, Any]:
        """Get full strategy recommendation with reasoning."""
        risk_level = self.assess_risk(cart)
        strategy = self.select_strategy(cart)
        discount_value, code_prefix = self.calculate_discount(cart, strategy)

        # Build reasoning
        reasoning = []
        reasoning.append(f"Cart value: ${cart.total_value:.2f}")
        reasoning.append(f"Items: {cart.items_count}")
        reasoning.append(
            f"Time abandoned: {cart.time_abandoned_hours:.1f}h"
            if cart.time_abandoned_hours
            else "Unknown time"
        )

        if cart.customer:
            reasoning.append(f"Customer: {cart.customer.segment} tier")
            reasoning.append(f"LTV tier: {cart.customer.lifetime_value_tier}")
            reasoning.append(f"Repeat customer: {cart.customer.is_repeat_customer}")

        reasoning.append(f"Risk level: {risk_level.value}")
        reasoning.append(f"Strategy: {strategy.value}")
        if discount_value > 0:
            reasoning.append(f"Discount: {discount_value}")

        return {
            "strategy": strategy,
            "risk_level": risk_level,
            "discount_value": discount_value,
            "code_prefix": code_prefix,
            "recovery_probability": cart.recovery_probability,
            "reasoning": reasoning,
            "estimated_revenue": cart.total_value * cart.recovery_probability,
        }

    def _upgrade_tier(self, current_tier: str) -> str:
        """Upgrade discount tier for loyal customers."""
        tier_order = ["low", "medium", "high", "vip"]
        try:
            idx = tier_order.index(current_tier)
            return tier_order[min(idx + 1, len(tier_order) - 1)]
        except ValueError:
            return current_tier

    def batch_analyze(self, carts: List[AbandonedCart]) -> Dict[str, Any]:
        """Analyze multiple carts and provide aggregate insights."""
        if not carts:
            return {"total": 0, "strategies": {}, "total_potential_revenue": 0}

        strategies = {}
        total_potential = 0.0
        risk_distribution = dict.fromkeys(CartRiskLevel, 0)

        for cart in carts:
            recommendation = self.get_strategy_recommendation(cart)
            strategy = recommendation["strategy"]

            if strategy.value not in strategies:
                strategies[strategy.value] = {"count": 0, "total_value": 0}
            strategies[strategy.value]["count"] += 1
            strategies[strategy.value]["total_value"] += cart.total_value

            total_potential += recommendation["estimated_revenue"]
            risk_distribution[recommendation["risk_level"]] += 1

        return {
            "total": len(carts),
            "strategies": strategies,
            "total_potential_revenue": round(total_potential, 2),
            "risk_distribution": {k.value: v for k, v in risk_distribution.items()},
            "average_cart_value": round(sum(c.total_value for c in carts) / len(carts), 2),
        }
