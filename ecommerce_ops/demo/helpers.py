"""
Demo Helpers
Utilities for running demonstrations and generating sample data.
"""

import random
import uuid
from datetime import timedelta
from typing import Any, Dict

from ecommerce_ops.utils import utc_now


def generate_demo_order() -> Dict[str, Any]:
    """Generate a realistic demo order."""
    products = [
        {"id": "PROD-001", "name": "Wireless Headphones", "price": 79.99},
        {"id": "PROD-002", "name": "Smart Watch", "price": 199.99},
        {"id": "PROD-003", "name": "Running Shoes", "price": 129.99},
        {"id": "PROD-004", "name": "Laptop Stand", "price": 49.99},
        {"id": "PROD-005", "name": "USB-C Hub", "price": 39.99},
        {"id": "PROD-006", "name": "Mechanical Keyboard", "price": 149.99},
        {"id": "PROD-007", "name": "Webcam HD", "price": 89.99},
        {"id": "PROD-008", "name": "Wireless Mouse", "price": 29.99},
    ]

    product = random.choice(products)
    quantity = random.randint(1, 5)
    total = product["price"] * quantity

    risk_factors = ["low", "low", "low", "medium", "medium", "high"]
    risk = random.choice(risk_factors)

    return {
        "id": f"ORD-{uuid.uuid4().hex[:8].upper()}",
        "shopify_id": f"{random.randint(100000000, 999999999)}",
        "product": product["name"],
        "product_id": product["id"],
        "quantity": quantity,
        "unit_price": product["price"],
        "total": round(total, 2),
        "currency": "USD",
        "customer_email": f"demo{random.randint(100, 999)}@example.com",
        "shipping_address": {
            "city": random.choice(["New York", "Los Angeles", "Chicago", "Houston", "Phoenix"]),
            "state": random.choice(["NY", "CA", "IL", "TX", "AZ"]),
            "country": "US",
        },
        "payment_method": random.choice(["credit_card", "paypal", "apple_pay"]),
        "risk_level": risk,
        "created_at": utc_now().isoformat(),
        "status": "pending",
    }


def generate_demo_cart() -> Dict[str, Any]:
    """Generate a demo abandoned cart."""
    items = [
        {"name": "Wireless Headphones", "price": 79.99, "quantity": 1},
        {"name": "Smart Watch", "price": 199.99, "quantity": 1},
        {"name": "Running Shoes", "price": 129.99, "quantity": 1},
        {"name": "Laptop Stand", "price": 49.99, "quantity": 2},
    ]

    cart_items = random.sample(items, k=random.randint(1, len(items)))
    total = sum(item["price"] * item["quantity"] for item in cart_items)

    abandoned_at = utc_now() - timedelta(hours=random.randint(1, 72))

    recovery_strategies = [
        "discount_10_percent",
        "discount_15_percent",
        "free_shipping",
        "urgency_message",
        "social_proof",
    ]

    return {
        "id": f"CART-{uuid.uuid4().hex[:8].upper()}",
        "customer_email": f"cart{random.randint(100, 999)}@example.com",
        "items": cart_items,
        "total": round(total, 2),
        "currency": "USD",
        "abandoned_at": abandoned_at.isoformat(),
        "recovery_strategy": random.choice(recovery_strategies),
        "recovery_email_sent": random.choice([True, False]),
        "recovered": random.choice([True, False, False, False]),
        "recovery_rate": round(random.uniform(0.05, 0.25), 2),
        "session_duration_seconds": random.randint(60, 1800),
        "pages_viewed": random.randint(3, 20),
    }


def generate_demo_ticket() -> Dict[str, Any]:
    """Generate a demo support ticket."""
    subjects = [
        "Order not received",
        "Wrong item shipped",
        "Refund request",
        "Product defect",
        "Billing question",
        "Shipping delay",
        "Account access issue",
        "Promotion code not working",
    ]

    sentiments = ["positive", "neutral", "negative", "negative", "negative"]
    priorities = ["low", "medium", "medium", "high", "urgent"]

    return {
        "id": f"TICKET-{uuid.uuid4().hex[:8].upper()}",
        "customer_email": f"support{random.randint(100, 999)}@example.com",
        "subject": random.choice(subjects),
        "message": "This is a demo support ticket for testing the customer support agent.",
        "sentiment": random.choice(sentiments),
        "priority": random.choice(priorities),
        "category": random.choice(
            [
                "order_issue",
                "billing",
                "product_question",
                "technical_support",
                "feedback",
            ]
        ),
        "status": random.choice(["open", "in_progress", "resolved"]),
        "created_at": utc_now().isoformat(),
        "response_time_hours": round(random.uniform(0.5, 24.0), 1),
        "satisfaction_score": random.randint(1, 5),
    }


def generate_demo_product() -> Dict[str, Any]:
    """Generate a demo product."""
    products = [
        {"name": "Wireless Headphones", "category": "Electronics", "base_price": 79.99},
        {"name": "Smart Watch", "category": "Electronics", "base_price": 199.99},
        {"name": "Running Shoes", "category": "Footwear", "base_price": 129.99},
        {"name": "Laptop Stand", "category": "Accessories", "base_price": 49.99},
        {"name": "USB-C Hub", "category": "Electronics", "base_price": 39.99},
        {"name": "Mechanical Keyboard", "category": "Electronics", "base_price": 149.99},
        {"name": "Webcam HD", "category": "Electronics", "base_price": 89.99},
        {"name": "Wireless Mouse", "category": "Electronics", "base_price": 29.99},
    ]

    product = random.choice(products)
    stock = random.randint(0, 500)
    price_variation = random.uniform(0.8, 1.2)
    current_price = round(product["base_price"] * price_variation, 2)

    return {
        "id": f"PROD-{uuid.uuid4().hex[:8].upper()}",
        "shopify_id": f"{random.randint(100000000, 999999999)}",
        "name": product["name"],
        "category": product["category"],
        "price": current_price,
        "compare_at_price": round(current_price * 1.2, 2),
        "inventory_quantity": stock,
        "inventory_management": "shopify",
        "status": "active" if stock > 0 else "out_of_stock",
        "created_at": utc_now().isoformat(),
        "updated_at": utc_now().isoformat(),
    }


def generate_demo_analytics() -> Dict[str, Any]:
    """Generate demo analytics data."""
    return {
        "period": "last_30_days",
        "revenue": {
            "total": round(random.uniform(50000, 200000), 2),
            "orders": random.randint(500, 2000),
            "average_order_value": round(random.uniform(50, 150), 2),
        },
        "fraud_detection": {
            "orders_analyzed": random.randint(1000, 5000),
            "fraud_detected": random.randint(10, 100),
            "false_positives": random.randint(0, 10),
            "money_saved": round(random.uniform(5000, 50000), 2),
        },
        "cart_recovery": {
            "carts_abandoned": random.randint(100, 500),
            "recovery_emails_sent": random.randint(80, 400),
            "carts_recovered": random.randint(10, 100),
            "revenue_recovered": round(random.uniform(5000, 30000), 2),
        },
        "customer_support": {
            "tickets_received": random.randint(50, 300),
            "auto_resolved": random.randint(30, 200),
            "escalated": random.randint(5, 50),
            "average_response_time_hours": round(random.uniform(0.5, 4.0), 1),
        },
        "performance": {
            "average_agent_response_ms": random.randint(100, 500),
            "uptime_percent": round(random.uniform(99.5, 99.99), 2),
            "error_rate_percent": round(random.uniform(0.01, 0.5), 2),
        },
    }
