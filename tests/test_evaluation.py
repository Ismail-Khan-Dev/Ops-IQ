"""
Evaluation Suite: Tests agent decision quality across predefined scenarios.
Run with: python -m pytest tests/test_evaluation.py -v --asyncio-mode=auto
"""

import pytest

from ecommerce_ops.safety.safety_rules import evaluate_action_safety


class MockSettings:
    def __init__(self, shadow_mode=False, fraud_threshold=70, po_limit=1000.0,
                 pricing_limit=5.0, reviews_rating_threshold=4):
        self.shadow_mode = shadow_mode
        self.fraud_threshold = fraud_threshold
        self.po_limit = po_limit
        self.pricing_limit = pricing_limit
        self.reviews_rating_threshold = reviews_rating_threshold


SCENARIOS = [
    # FraudAgent always requires HITL and always high risk
    ("Fraud: high-risk order", "FraudAgent", "fraud_hold",
     {"order_id": "ORD-100", "fraud_score": 92, "order_total": 500.0}, 0.72, True, "high"),
    ("Fraud: low-risk order", "FraudAgent", "fraud_hold",
     {"order_id": "ORD-101", "fraud_score": 15, "order_total": 25.0}, 0.92, True, "high"),

    # InventoryAgent: > limit → HITL + medium risk (unless > 5x limit)
    ("Inventory: PO above limit", "InventoryAgent", "purchase_order",
     {"sku": "EXP-MUG", "total_po_value": 2500.0, "reorder_quantity": 500}, 0.80, True, "medium"),
    ("Inventory: PO below limit", "InventoryAgent", "purchase_order",
     {"sku": "CHEAP-MUG", "total_po_value": 100.0, "reorder_quantity": 50}, 0.85, False, "low"),

    # PricingAgent: >20% → critical, 5-12% → medium, <5% → low
    ("Pricing: small change", "PricingAgent", "price_change",
     {"sku": "TSHIRT-BLU", "old_price": 25.0, "new_price": 24.0, "change_pct": 4.0}, 0.90, False, "low"),
    ("Pricing: medium change", "PricingAgent", "price_change",
     {"sku": "TSHIRT-BLU", "old_price": 25.0, "new_price": 22.0, "change_pct": 12.0}, 0.70, True, "medium"),
    ("Pricing: large change", "PricingAgent", "price_change",
     {"sku": "TSHIRT-BLU", "old_price": 25.0, "new_price": 18.0, "change_pct": 28.0}, 0.55, True, "critical"),

    # ReviewsAgent: <4 → HITL + medium, >=4 → auto-approve + low
    ("Reviews: negative response", "ReviewsAgent", "review_response",
     {"review_id": "R-100", "rating": 2, "content": "Product broke after 2 days"}, 0.65, True, "medium"),
    ("Reviews: positive response", "ReviewsAgent", "review_response",
     {"review_id": "R-101", "rating": 5, "content": "Amazing quality!"}, 0.95, False, "low"),

    # MarketingAgent: always HITL + medium
    ("Marketing: campaign draft", "MarketingAgent", "marketing_campaign",
     {"campaign_type": "flash_sale", "discount_pct": 20}, 0.70, True, "medium"),
]


@pytest.mark.parametrize("name,agent,action_type,payload,confidence,expect_hitl,expect_risk", SCENARIOS)
def test_safety_rules_scenario(name, agent, action_type, payload, confidence, expect_hitl, expect_risk):
    settings = MockSettings()
    requires_hitl, risk_level, impact = evaluate_action_safety(agent, action_type, payload, confidence, settings)

    assert requires_hitl == expect_hitl, (
        f"[{name}] Expected requires_hitl={expect_hitl}, got {requires_hitl}"
    )
    assert risk_level == expect_risk, (
        f"[{name}] Expected risk_level={expect_risk}, got {risk_level}"
    )


@pytest.mark.parametrize("name,agent,action_type,payload,confidence,expect_hitl,expect_risk", SCENARIOS)
def test_shadow_mode_forces_hitl(name, agent, action_type, payload, confidence, expect_hitl, expect_risk):
    settings = MockSettings(shadow_mode=True)
    requires_hitl, risk_level, impact = evaluate_action_safety(agent, action_type, payload, confidence, settings)
    assert requires_hitl is True, (
        f"[{name}] Shadow mode should force HITL"
    )
