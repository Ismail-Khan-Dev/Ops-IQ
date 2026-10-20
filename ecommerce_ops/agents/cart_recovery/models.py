"""
Abandoned Cart Data Models
Pydantic models for cart recovery analytics and strategy.
"""

from datetime import datetime
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, Field

from ecommerce_ops.utils import utc_now


class CartStatus(StrEnum):
    ABANDONED = "abandoned"
    RECOVERY_PENDING = "recovery_pending"
    RECOVERY_SENT = "recovery_sent"
    RECOVERED = "recovered"
    EXPIRED = "expired"
    LOST = "lost"


class RecoveryStrategy(StrEnum):
    NONE = "none"
    DISCOUNT_PERCENT = "discount_percent"
    DISCOUNT_FIXED = "discount_fixed"
    FREE_SHIPPING = "free_shipping"
    BUNDLE_OFFER = "bundle_offer"
    URGENCY = "urgency"
    SOCIAL_PROOF = "social_proof"
    PERSONAL_OUTREACH = "personal_outreach"


class CartRiskLevel(StrEnum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class CartItem(BaseModel):
    product_id: int
    variant_id: int
    title: str
    sku: str | None = None
    quantity: int = 1
    price: float = 0.0
    total: float = 0.0
    image_url: str | None = None
    product_type: str | None = None
    vendor: str | None = None

    class Config:
        extra = "allow"


class CustomerProfile(BaseModel):
    id: int | None = None
    email: str | None = None
    first_name: str | None = None
    last_name: str | None = None
    total_orders: int = 0
    total_spent: float = 0.0
    average_order_value: float = 0.0
    last_order_date: datetime | None = None
    is_repeat_customer: bool = False
    segment: str = "new"
    tags: list[str] = Field(default_factory=list)

    @property
    def lifetime_value_tier(self) -> str:
        if self.total_spent > 500:
            return "vip"
        elif self.total_spent > 200:
            return "high"
        elif self.total_spent > 50:
            return "medium"
        return "low"


class AbandonedCart(BaseModel):
    id: str
    shop_domain: str
    checkout_token: str | None = None
    customer: CustomerProfile | None = None
    items: list[CartItem] = Field(default_factory=list)
    total_value: float = 0.0
    currency: str = "USD"
    items_count: int = 0
    status: CartStatus = CartStatus.ABANDONED
    risk_level: CartRiskLevel = CartRiskLevel.MEDIUM
    recovery_strategy: RecoveryStrategy = RecoveryStrategy.NONE
    recovery_discount_value: float = 0.0
    recovery_email_sent: bool = False
    recovery_email_opened: bool = False
    recovery_link_clicked: bool = False
    recovery_completed: bool = False
    created_at: datetime = Field(default_factory=utc_now)
    abandoned_at: datetime | None = None
    recovered_at: datetime | None = None
    expires_at: datetime | None = None
    checkout_url: str | None = None
    recovery_url: str | None = None
    notes: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)

    class Config:
        extra = "allow"

    @property
    def time_abandoned_hours(self) -> float | None:
        if self.abandoned_at:
            delta = utc_now() - self.abandoned_at
            return delta.total_seconds() / 3600
        return None

    @property
    def is_recoverable(self) -> bool:
        return self.status in (
            CartStatus.ABANDONED,
            CartStatus.RECOVERY_PENDING,
            CartStatus.RECOVERY_SENT,
        )

    @property
    def recovery_probability(self) -> float:
        """Estimate recovery probability based on cart and customer data."""
        score = 0.0

        # Cart value factor (higher value = more motivation to recover)
        if self.total_value > 100:
            score += 0.3
        elif self.total_value > 50:
            score += 0.2
        elif self.total_value > 20:
            score += 0.1

        # Customer factor
        if self.customer:
            if self.customer.is_repeat_customer:
                score += 0.25
            if self.customer.total_orders > 5:
                score += 0.15
            if self.customer.average_order_value > self.total_value * 0.5:
                score += 0.1

        # Items factor
        if self.items_count > 3:
            score += 0.1
        elif self.items_count > 1:
            score += 0.05

        # Time factor (fresher = better)
        hours = self.time_abandoned_hours
        if hours and hours < 1:
            score += 0.2
        elif hours and hours < 24:
            score += 0.1
        elif hours and hours > 72:
            score -= 0.1

        return min(max(score, 0.0), 1.0)


class RecoveryEmailTemplate(BaseModel):
    strategy: RecoveryStrategy
    subject: str
    preview_text: str
    body_template: str
    cta_text: str = "Complete Your Order"
    discount_code: str | None = None
    discount_value: float | None = None
    urgency_hours: int = 24


class CartRecoveryResult(BaseModel):
    cart_id: str
    strategy_used: RecoveryStrategy
    discount_code: str | None = None
    discount_value: float = 0.0
    email_sent: bool = False
    email_opened: bool = False
    link_clicked: bool = False
    recovered: bool = False
    revenue_recovered: float = 0.0
    processing_time_ms: float = 0.0
    error: str | None = None


class CartAnalytics(BaseModel):
    total_abandoned: int = 0
    total_recovered: int = 0
    recovery_rate: float = 0.0
    total_revenue_lost: float = 0.0
    total_revenue_recovered: float = 0.0
    average_cart_value: float = 0.0
    average_recovery_time_hours: float = 0.0
    top_recovery_strategy: RecoveryStrategy | None = None
    strategy_breakdown: dict[str, dict[str, Any]] = Field(default_factory=dict)
    hourly_distribution: list[dict[str, Any]] = Field(default_factory=list)
    risk_distribution: dict[str, int] = Field(default_factory=dict)
