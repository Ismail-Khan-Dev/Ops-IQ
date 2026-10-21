"""
Tests for Direction 2: Killer Features
Validates:
1. Wardrobing & Bracketing Anti-Abuse Shield (Multi-size detection, serial returner penalties).
2. Post-Purchase Up-Exchange Engine (Keep-It Sweetener Bundles & Tier-Up Upgrades).
3. Live Margin Preserved Counter & Shopify Admin Badge Widget.
4. REST API endpoints and MCP Tool dispatchers.
"""

from unittest.mock import AsyncMock, patch

import pytest
from fastapi.testclient import TestClient

from ecommerce_ops.api.app import app
from ecommerce_ops.mcp.tools import execute_tool
from ecommerce_ops.returns.live_margin_widget import LiveMarginWidget
from ecommerce_ops.returns.up_exchange import UpExchangeEngine
from ecommerce_ops.returns.wardrobing_shield import WardrobingShield
from ecommerce_ops.security.models import Role, User


@pytest.fixture
def test_client():
    return TestClient(app)


# ── 1. Wardrobing & Bracketing Shield Unit Tests ────────────────────────────


def test_wardrobing_normal_order():
    order = {
        "id": "ord_101",
        "total_price": "65.00",
        "line_items": [
            {"product_id": 1, "title": "Denim Jeans - 32"},
            {"product_id": 2, "title": "White T-Shirt - M"},
        ],
    }
    res = WardrobingShield.detect_bracketing(order)
    assert res["is_bracketing_detected"] is False
    assert res["excess_units_likely_returned"] == 0
    assert res["avoidable_reverse_logistics_cost_usd"] == 0.0


def test_wardrobing_duplicate_sizes_detected():
    # Customer orders Medium and Large of the exact same product
    order = {
        "id": "ord_102",
        "total_price": "160.00",
        "line_items": [
            {"product_id": 88, "title": "Silk Summer Dress - M", "variant_title": "M"},
            {"product_id": 88, "title": "Silk Summer Dress - L", "variant_title": "L"},
        ],
    }
    res = WardrobingShield.detect_bracketing(order)
    assert res["is_bracketing_detected"] is True
    assert res["excess_units_likely_returned"] == 1
    assert res["avoidable_reverse_logistics_cost_usd"] == 14.50
    assert res["bracketing_risk_score"] >= 65
    assert "SIZING_VERIFICATION_PROMPT" in res["mitigation_strategies"]


def test_wardrobing_serial_returner_penalty():
    # Customer orders 3 sizes of the same dress AND has 45% return rate
    order = {
        "id": "ord_103",
        "total_price": "240.00",
        "line_items": [
            {"product_id": 99, "title": "Cocktail Dress - S", "variant_title": "S"},
            {"product_id": 99, "title": "Cocktail Dress - M", "variant_title": "M"},
            {"product_id": 99, "title": "Cocktail Dress - L", "variant_title": "L"},
        ],
    }
    res = WardrobingShield.detect_bracketing(
        order,
        historical_return_rate=0.45,
        previous_returns_count=4,
    )
    assert res["is_bracketing_detected"] is True
    assert res["excess_units_likely_returned"] == 2
    assert res["bracketing_risk_score"] >= 85
    assert "REVOKE_FREE_RETURN_SHIPPING" in res["mitigation_strategies"]


# ── 2. Up-Exchange Engine Unit Tests ────────────────────────────────────────


def test_up_exchange_generate_offers():
    res = UpExchangeEngine.generate_up_exchange_offers(
        item_price=80.0,
        title="Merino Wool Sweater",
        category="apparel",
        return_reason="sizing_fit",
    )
    assert res["avoided_reverse_logistics_cost_usd"] == 14.50
    assert len(res["offers"]) == 2

    offer1 = res["offers"][0]
    assert offer1["strategy"] == "KEEP_IT_SWEETENER_BUNDLE"
    assert offer1["customer_pays"] == 15.0
    assert offer1["merchant_preserved_margin_usd"] > 80.0

    offer2 = res["offers"][1]
    assert offer2["strategy"] == "TIER_UP_UPGRADE_EXCHANGE"
    assert offer2["customer_pays"] > 0
    assert offer2["merchant_preserved_margin_usd"] > 80.0


# ── 3. Live Margin Widget Unit Tests ────────────────────────────────────────


@pytest.mark.asyncio
async def test_live_margin_widget():
    summary = await LiveMarginWidget.get_live_margin_summary()
    assert summary["total_net_margin_preserved_usd"] > 0
    assert summary["total_gmv_preserved_usd"] > 0
    assert "x" in summary["software_roi_multiple"]
    assert "<div" in summary["badge_html"]
    assert "OpsIQ Margin Preservation Engine" in summary["badge_html"]


# ── 4. REST API Integration Tests ───────────────────────────────────────────


def test_api_wardrobing_evaluate(test_client):
    admin_user = User(
        username="admin",
        role=Role.ADMIN,
        permissions=["observability:view"],
    )
    with patch("ecommerce_ops.security.auth.get_current_user", return_value=admin_user):
        resp = test_client.post(
            "/api/v1/roi/wardrobing/evaluate",
            json={
                "order": {
                    "id": "ord_test_99",
                    "total_price": "180.00",
                    "line_items": [
                        {"product_id": 501, "title": "Linen Trousers - 32"},
                        {"product_id": 501, "title": "Linen Trousers - 34"},
                    ],
                },
                "historical_return_rate": 0.25,
            },
            headers={"Authorization": "Bearer dummy_test_token"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["is_bracketing_detected"] is True
        assert data["excess_units_likely_returned"] == 1


def test_api_up_exchange_negotiate(test_client):
    admin_user = User(
        username="admin",
        role=Role.ADMIN,
        permissions=["observability:view"],
    )
    with patch("ecommerce_ops.security.auth.get_current_user", return_value=admin_user):
        resp = test_client.post(
            "/api/v1/roi/up-exchange/negotiate",
            json={
                "item_price": 95.0,
                "title": "Winter Parka",
                "category": "apparel",
                "return_reason": "color_not_as_expected",
            },
            headers={"Authorization": "Bearer dummy_test_token"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert len(data["offers"]) == 2


def test_api_live_margin_widget(test_client):
    admin_user = User(
        username="admin",
        role=Role.ADMIN,
        permissions=["observability:view"],
    )
    with patch("ecommerce_ops.security.auth.get_current_user", return_value=admin_user):
        resp = test_client.get(
            "/api/v1/roi/live-widget",
            headers={"Authorization": "Bearer dummy_test_token"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert "badge_html" in data
        assert "total_net_margin_preserved_usd" in data


# ── 5. MCP Tool Dispatcher Tests ────────────────────────────────────────────


@pytest.mark.asyncio
async def test_mcp_execute_bracketing():
    order = {
        "id": "mcp_ord_1",
        "line_items": [
            {"product_id": 777, "title": "Sneakers - 10"},
            {"product_id": 777, "title": "Sneakers - 11"},
        ],
    }
    res = await execute_tool("opsiq_detect_bracketing_risk", {"order": order})
    assert res["is_bracketing_detected"] is True
    assert res["excess_units_likely_returned"] == 1


@pytest.mark.asyncio
async def test_mcp_execute_up_exchange():
    res = await execute_tool("opsiq_generate_up_exchange_offer", {"item_price": 70.0, "category": "beauty"})
    assert len(res["offers"]) == 2
    assert res["avoided_reverse_logistics_cost_usd"] == 14.50
