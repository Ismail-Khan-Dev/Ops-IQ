"""
Discount Code Generator
Creates unique discount codes for cart recovery campaigns.
"""

import hashlib
import logging
import secrets
import string
from datetime import timedelta
from typing import Any

from ecommerce_ops.agents.cart_recovery.models import (
    AbandonedCart,
    RecoveryStrategy,
)
from ecommerce_ops.utils import utc_now

logger = logging.getLogger("ecommerce_ops.agents.cart_recovery.discounts")


class DiscountCodeGenerator:
    """Generates unique, trackable discount codes."""

    # Character sets for code generation
    UPPERCASE = string.ascii_uppercase
    DIGITS = string.digits

    def __init__(self, prefix: str = "REC", length: int = 8):
        self.prefix = prefix
        self.length = length
        self._used_codes: set = set()

    def generate_code(
        self,
        cart: AbandonedCart,
        strategy: RecoveryStrategy,
        discount_value: float,
    ) -> str:
        """Generate a unique discount code."""
        # Create base from cart and strategy
        base = self._create_base(cart, strategy)

        # Add random suffix
        suffix = self._random_suffix(self.length - len(base) - len(self.prefix) - 1)

        code = f"{self.prefix}-{base}-{suffix}".upper()

        # Ensure uniqueness
        attempts = 0
        while code in self._used_codes and attempts < 10:
            suffix = self._random_suffix(self.length - len(base) - len(self.prefix) - 1)
            code = f"{self.prefix}-{base}-{suffix}".upper()
            attempts += 1

        self._used_codes.add(code)
        logger.info("Generated discount code: %s for cart %s", code, cart.id)
        return code

    def generate_simple(self, length: int = 8) -> str:
        """Generate a simple random discount code."""
        chars = self.UPPERCASE + self.DIGITS
        code = "".join(secrets.choice(chars) for _ in range(length))
        full_code = f"{self.prefix}-{code}"
        self._used_codes.add(full_code)
        return full_code

    def get_discount_config(
        self,
        strategy: RecoveryStrategy,
        discount_value: float,
        code: str,
        cart: AbandonedCart,
    ) -> dict[str, Any]:
        """Get discount configuration for Shopify price rule."""
        now = utc_now()
        expires_at = now + timedelta(hours=24)

        config = {
            "price_rule": {
                "title": code,
                "target_type": "line_item",
                "target_selection": "all",
                "allocation_method": "across",
                "value_type": "percentage"
                if strategy == RecoveryStrategy.DISCOUNT_PERCENT
                else "fixed_amount",
            },
            "discount_code": {
                "code": code,
                "usage_limit": 1,
                "starts_at": now.isoformat(),
                "expires_at": expires_at.isoformat(),
            },
        }

        # Set value based on strategy
        if strategy == RecoveryStrategy.DISCOUNT_PERCENT:
            config["price_rule"]["value"] = f"-{discount_value}"
        elif strategy == RecoveryStrategy.DISCOUNT_FIXED:
            config["price_rule"]["value"] = f"-{discount_value:.2f}"
        elif strategy == RecoveryStrategy.FREE_SHIPPING:
            config["price_rule"]["target_type"] = "shipping_line"
            config["price_rule"]["value"] = "-100.0"
            config["price_rule"]["value_type"] = "percentage"

        return config

    def get_recovery_email_context(
        self,
        cart: AbandonedCart,
        code: str,
        strategy: RecoveryStrategy,
        discount_value: float,
    ) -> dict[str, Any]:
        """Get context for recovery email template."""
        customer_name = "there"
        if cart.customer and cart.customer.first_name:
            customer_name = cart.customer.first_name

        items_summary = ", ".join([f"{item.title} (x{item.quantity})" for item in cart.items[:3]])
        if len(cart.items) > 3:
            items_summary += f" and {len(cart.items) - 3} more"

        context = {
            "customer_name": customer_name,
            "cart_items": items_summary,
            "cart_value": f"${cart.total_value:.2f}",
            "discount_code": code,
            "discount_value": f"{discount_value}"
            if strategy == RecoveryStrategy.DISCOUNT_PERCENT
            else f"${discount_value:.2f}",
            "strategy": strategy.value,
            "checkout_url": cart.checkout_url or "",
            "cta_text": self._get_cta_text(strategy),
            "urgency_hours": 24,
            "currency": cart.currency,
        }

        # Add strategy-specific context
        if strategy == RecoveryStrategy.FREE_SHIPPING:
            context["discount_text"] = "FREE SHIPPING"
            context["cta_text"] = "Claim Free Shipping"
        elif strategy == RecoveryStrategy.DISCOUNT_PERCENT:
            context["discount_text"] = f"{discount_value}% OFF"
            context["cta_text"] = f"Get {discount_value}% Off Now"
        elif strategy == RecoveryStrategy.DISCOUNT_FIXED:
            context["discount_text"] = f"${discount_value:.2f} OFF"
            context["cta_text"] = f"Save ${discount_value:.2f} Today"
        elif strategy == RecoveryStrategy.SOCIAL_PROOF:
            context["discount_text"] = "Don't Miss Out!"
            context["cta_text"] = "Complete Your Order"
        elif strategy == RecoveryStrategy.URGENCY:
            context["discount_text"] = "Limited Time Offer"
            context["cta_text"] = "Buy Before It's Gone"
        else:
            context["discount_text"] = "We Saved Your Cart"
            context["cta_text"] = "Complete Purchase"

        return context

    def _create_base(self, cart: AbandonedCart, strategy: RecoveryStrategy) -> str:
        """Create a deterministic base code from cart data."""
        # Use cart ID hash for uniqueness
        cart_hash = hashlib.md5(cart.id.encode()).hexdigest()[:6]

        # Add strategy prefix
        strategy_map = {
            RecoveryStrategy.DISCOUNT_PERCENT: "PCT",
            RecoveryStrategy.DISCOUNT_FIXED: "FIX",
            RecoveryStrategy.FREE_SHIPPING: "SHIP",
            RecoveryStrategy.URGENCY: "URG",
            RecoveryStrategy.SOCIAL_PROOF: "SOC",
            RecoveryStrategy.PERSONAL_OUTREACH: "VIP",
            RecoveryStrategy.BUNDLE_OFFER: "BND",
            RecoveryStrategy.NONE: "REC",
        }

        strategy_code = strategy_map.get(strategy, "REC")
        return f"{strategy_code}{cart_hash[:4]}"

    def _random_suffix(self, length: int) -> str:
        """Generate random alphanumeric suffix."""
        chars = self.UPPERCASE + self.DIGITS
        return "".join(secrets.choice(chars) for _ in range(length))

    def _get_cta_text(self, strategy: RecoveryStrategy) -> str:
        """Get CTA text based on strategy."""
        cta_map = {
            RecoveryStrategy.DISCOUNT_PERCENT: "Get Your Discount",
            RecoveryStrategy.DISCOUNT_FIXED: "Claim Your Savings",
            RecoveryStrategy.FREE_SHIPPING: "Get Free Shipping",
            RecoveryStrategy.URGENCY: "Complete Order Now",
            RecoveryStrategy.SOCIAL_PROOF: "Join Thousands of Happy Customers",
            RecoveryStrategy.PERSONAL_OUTREACH: "We're Here to Help",
            RecoveryStrategy.BUNDLE_OFFER: "See Your Bundle Deal",
            RecoveryStrategy.NONE: "Complete Purchase",
        }
        return cta_map.get(strategy, "Complete Purchase")
