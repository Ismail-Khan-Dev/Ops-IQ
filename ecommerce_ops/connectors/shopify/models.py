"""
Shopify Pydantic Models
Type-safe models for Shopify API data.
"""

from datetime import datetime
from enum import StrEnum
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field

# ── Enums ──────────────────────────────────────────────────


class OrderFinancialStatus(StrEnum):
    PENDING = "pending"
    AUTHORIZED = "authorized"
    PAID = "paid"
    PARTIALLY_PAID = "partially_paid"
    REFUNDED = "refunded"
    VOIDED = "voided"
    PARTIALLY_REFUNDED = "partially_refunded"
    AWAITING_PAYMENT = "awaiting_payment"
    UNPAID = "unpaid"


class OrderFulfillmentStatus(StrEnum):
    UNFULFILLED = "unfulfilled"
    PARTIAL = "partial"
    FULFILLED = "fulfilled"
    RESTOCKED = "restocked"
    DELIVERED = "delivered"
    IN_TRANSIT = "in_transit"


class ProductStatus(StrEnum):
    ACTIVE = "active"
    ARCHIVED = "archived"
    DRAFT = "draft"


class InventoryLevel(StrEnum):
    IN_STOCK = "in_stock"
    LOW_STOCK = "low_stock"
    OUT_OF_STOCK = "out_of_stock"


# ── Address ────────────────────────────────────────────────


class ShopifyAddress(BaseModel):
    address1: Optional[str] = None
    address2: Optional[str] = None
    city: Optional[str] = None
    province: Optional[str] = None
    province_code: Optional[str] = None
    country: Optional[str] = None
    country_code: Optional[str] = None
    zip: Optional[str] = None
    phone: Optional[str] = None
    name: Optional[str] = None
    company: Optional[str] = None


# ── Money ──────────────────────────────────────────────────


class Money(BaseModel):
    amount: str = "0.00"
    currency_code: str = "USD"

    @property
    def value(self) -> float:
        return float(self.amount)


# ── Product ────────────────────────────────────────────────


class ShopifyVariant(BaseModel):
    id: int
    product_id: int
    title: Optional[str] = None
    price: str = "0.00"
    sku: Optional[str] = None
    inventory_quantity: int = 0
    weight: Optional[float] = None
    weight_unit: Optional[str] = None
    option1: Optional[str] = None
    option2: Optional[str] = None
    option3: Optional[str] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

    class Config:
        extra = "allow"


class ShopifyImage(BaseModel):
    id: int
    src: str
    alt: Optional[str] = None
    width: Optional[int] = None
    height: Optional[int] = None
    position: int = 0

    class Config:
        extra = "allow"


class ShopifyProduct(BaseModel):
    id: int
    title: str
    body_html: Optional[str] = None
    vendor: Optional[str] = None
    product_type: Optional[str] = None
    status: ProductStatus = ProductStatus.ACTIVE
    tags: Optional[List[str]] = None
    variants: List[ShopifyVariant] = Field(default_factory=list)
    images: List[ShopifyImage] = Field(default_factory=list)
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None
    handle: Optional[str] = None
    variants_count: int = 0

    class Config:
        extra = "allow"

    @property
    def total_inventory(self) -> int:
        return sum(v.inventory_quantity for v in self.variants)

    @property
    def min_price(self) -> float:
        if not self.variants:
            return 0.0
        return min(float(v.price) for v in self.variants)

    @property
    def max_price(self) -> float:
        if not self.variants:
            return 0.0
        return max(float(v.price) for v in self.variants)


# ── Order ──────────────────────────────────────────────────


class ShopifyLineItem(BaseModel):
    id: int
    title: Optional[str] = None
    quantity: int = 1
    price: str = "0.00"
    sku: Optional[str] = None
    variant_id: Optional[int] = None
    product_id: Optional[int] = None
    fulfillment_status: Optional[str] = None
    requires_shipping: bool = True
    taxable: bool = True

    class Config:
        extra = "allow"


class ShopifyOrder(BaseModel):
    id: int
    order_number: int
    name: Optional[str] = None
    email: Optional[str] = None
    total_price: str = "0.00"
    subtotal_price: str = "0.00"
    total_tax: str = "0.00"
    total_discounts: str = "0.00"
    currency: str = "USD"
    financial_status: OrderFinancialStatus = OrderFinancialStatus.PENDING
    fulfillment_status: Optional[OrderFulfillmentStatus] = None
    line_items: List[ShopifyLineItem] = Field(default_factory=list)
    shipping_address: Optional[ShopifyAddress] = None
    billing_address: Optional[ShopifyAddress] = None
    customer: Optional[Dict[str, Any]] = None
    customer_id: Optional[int] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None
    processed_at: Optional[datetime] = None
    cancelled_at: Optional[datetime] = None
    cancel_reason: Optional[str] = None
    note: Optional[str] = None
    tags: Optional[str] = None

    class Config:
        extra = "allow"

    @property
    def items_count(self) -> int:
        return sum(item.quantity for item in self.line_items)

    @property
    def is_paid(self) -> bool:
        return self.financial_status in (
            OrderFinancialStatus.PAID,
            OrderFinancialStatus.AUTHORIZED,
        )

    @property
    def is_fulfilled(self) -> bool:
        return self.fulfillment_status in (
            OrderFulfillmentStatus.FULFILLED,
            OrderFulfillmentStatus.DELIVERED,
        )


# ── Customer ───────────────────────────────────────────────


class ShopifyCustomer(BaseModel):
    id: int
    email: Optional[str] = None
    first_name: Optional[str] = None
    last_name: Optional[str] = None
    phone: Optional[str] = None
    orders_count: int = 0
    total_spent: str = "0.00"
    tags: Optional[str] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None
    default_address: Optional[ShopifyAddress] = None

    class Config:
        extra = "allow"

    @property
    def full_name(self) -> str:
        parts = [self.first_name, self.last_name]
        return " ".join(p for p in parts if p)


# ── Inventory ──────────────────────────────────────────────


class ShopifyInventoryItem(BaseModel):
    id: int
    sku: Optional[str] = None
    title: Optional[str] = None
    quantity: int = 0
    location_id: Optional[int] = None
    available: int = 0
    cost: Optional[str] = None

    class Config:
        extra = "allow"


# ── Location ───────────────────────────────────────────────


class ShopifyLocation(BaseModel):
    id: int
    name: str
    address1: Optional[str] = None
    city: Optional[str] = None
    country: Optional[str] = None
    active: bool = True

    class Config:
        extra = "allow"


# ── Shop ───────────────────────────────────────────────────


class ShopifyShop(BaseModel):
    id: int
    name: str
    email: Optional[str] = None
    domain: str
    myshopify_domain: Optional[str] = None
    currency: str = "USD"
    timezone: Optional[str] = None
    plan_name: Optional[str] = None
    created_at: Optional[datetime] = None

    class Config:
        extra = "allow"


# ── Webhook Registration ───────────────────────────────────


class ShopifyWebhook(BaseModel):
    id: int
    topic: str
    address: str
    format: str = "json"
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

    class Config:
        extra = "allow"


# ── Paginated Response ─────────────────────────────────────


class PaginatedResponse(BaseModel):
    data: List[Any] = Field(default_factory=list)
    total_count: Optional[int] = None
    page_info: Optional[str] = None
    has_next_page: bool = False
    has_previous_page: bool = False
