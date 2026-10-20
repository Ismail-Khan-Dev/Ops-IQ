"""
Tests for Phase 3: The High-ROI Wedge (Margin Preservation & Intelligent Swaps)
Covers MarginPreservationCalculator unit economics, OrderSwapsAgent, SmartReturnsAgent,
runner live execution of return/swap strategies, and ROI REST API endpoints.
"""

from unittest.mock import AsyncMock, patch

import pytest
from fastapi.testclient import TestClient

from ecommerce_ops.analytics.margin_preservation import MarginPreservationCalculator
from ecommerce_ops.api.app import app
from ecommerce_ops.models import ApprovalAction, async_session_factory
from ecommerce_ops.pipeline.runner import execute_shop_action
from ecommerce_ops.security.models import Role, User


@pytest.fixture
def test_client():
    return TestClient(app)


# ── 1. MarginPreservationCalculator Unit Tests ───────────────────────


def test_return_unit_economics_keep_it_credit_for_low_cost():
    calc = MarginPreservationCalculator()
    # A $32 t-shirt return costs ~$18+ in reverse shipping, restock, inspection, depreciation
    res = calc.evaluate_return_unit_economics(
        item_price=32.0,
        category="apparel",
        return_reason="changed_mind",
    )
    assert res["strategy"] == "keep_it_credit"
    assert res["avoided_reverse_costs"] > 0
    assert res["preserved_margin"] == res["avoided_reverse_costs"]
    assert "Keep-It" in res["recommendation_reason"]


def test_return_unit_economics_beauty_hygiene():
    calc = MarginPreservationCalculator()
    # Beauty products have 85% salvage loss (opened packaging cannot be resold)
    res = calc.evaluate_return_unit_economics(
        item_price=48.0,
        category="skincare",
        return_reason="defective",
    )
    assert res["strategy"] == "keep_it_credit"
    assert res["depreciation_loss"] > 35.0  # High depreciation


def test_return_unit_economics_instant_exchange():
    calc = MarginPreservationCalculator()
    # Sizing / fit issue on standard apparel -> recommend instant variant swap
    res = calc.evaluate_return_unit_economics(
        item_price=85.0,
        category="apparel",
        return_reason="sizing_fit",
    )
    assert res["strategy"] == "instant_exchange"
    assert res["preserved_margin"] > 50.0  # Preserves gross profit margin


def test_return_unit_economics_high_ticket_standard_return():
    calc = MarginPreservationCalculator()
    # A $250 leather jacket -> physical return with prepaid label makes sense
    res = calc.evaluate_return_unit_economics(
        item_price=250.0,
        category="apparel",
        return_reason="not_as_described",
    )
    assert res["strategy"] == "standard_return"


def test_order_swap_unit_economics():
    calc = MarginPreservationCalculator()
    # Out-of-stock item ($60, $16.80 COGS) swapped to available item ($65, $18.20 COGS)
    res = calc.evaluate_order_swap_unit_economics(
        original_price=60.0,
        swap_price=65.0,
    )
    assert res["preserved_gmv"] == 65.0
    assert res["preserved_net_margin"] > 40.0
    assert res["margin_delta"] > 0  # Upgraded margin


def test_aggregate_margin_metrics():
    actions = [
        ApprovalAction(
            id="a1",
            status="executed",
            action_type="order_swap",
            impact={"preserved_gmv": 75.0, "preserved_margin": 52.0},
        ),
        ApprovalAction(
            id="a2",
            status="executed",
            action_type="return_risk_flag",
            impact={"strategy": "keep_it_credit", "preserved_margin": 14.50, "reverse_costs_saved": 14.50},
        ),
        ApprovalAction(
            id="a3",
            status="pending",  # Pending should be skipped from executed totals
            action_type="order_swap",
            impact={"preserved_gmv": 100.0, "preserved_margin": 70.0},
        ),
    ]
    summary = MarginPreservationCalculator.aggregate_margin_metrics(actions)
    assert summary["total_gmv_preserved_usd"] == 75.0
    assert summary["reverse_logistics_saved_usd"] == 14.50
    assert summary["total_net_margin_preserved_usd"] == 66.50
    assert summary["total_value_delivered_usd"] == 81.00
    assert summary["strategy_breakdown"]["order_swap"] == 1
    assert summary["strategy_breakdown"]["keep_it_credit"] == 1


# ── 2. Agents Margin Preservation Integration ────────────────────────


@pytest.mark.asyncio
async def test_order_swaps_agent_generates_margin_metrics():
    from ecommerce_ops.agents.order_swaps.swaps import OrderSwapsAgent

    agent = OrderSwapsAgent()
    state = {
        "out_of_stock_items": [
            {
                "order_id": "ORD-501",
                "original_sku": "SHIRT-BLU-M",
                "original_name": "Classic Blue Shirt",
                "original_price": 45.0,
                "category": "apparel",
                "available_swaps": [
                    {
                        "sku": "SHIRT-BLK-M",
                        "name": "Classic Black Shirt",
                        "price": 45.0,
                        "stock": 12,
                        "rating": 4.8,
                        "category": "apparel",
                    }
                ],
            }
        ],
        "decisions": [],
    }

    updated_state = await agent.run(state)
    decisions = updated_state["decisions"]
    assert len(decisions) == 1
    d = decisions[0]
    assert d.action_type == "SWAP_ITEM"
    assert d.action_data["swap_sku"] == "SHIRT-BLK-M"
    assert d.action_data["preserved_gmv"] == 45.0
    assert "Preserves $45.00 GMV" in d.reasoning


@pytest.mark.asyncio
async def test_smart_returns_agent_selects_keep_it_credit():
    from ecommerce_ops.agents.smart_returns.returns import SmartReturnsAgent

    agent = SmartReturnsAgent()
    state = {
        "pending_orders": [
            {
                "order_id": "ORD-702",
                "order_total": 28.0,
                "category": "apparel",
                "categories": ["apparel"],
                "return_reason": "changed_mind",
                "previous_returns": 3,
            }
        ],
        "decisions": [],
    }

    updated_state = await agent.run(state)
    decisions = updated_state["decisions"]
    assert len(decisions) == 1
    d = decisions[0]
    assert d.action_type == "FLAG_RETURN_RISK"
    assert d.action_data["strategy"] == "keep_it_credit"
    assert "offer_keep_it_store_credit" in d.action_data["preventive_actions"]


# ── 3. Runner execute_shop_action for Swaps & Returns ────────────────


@pytest.mark.asyncio
async def test_execute_shop_action_order_swap():
    action = ApprovalAction(
        id="act_swap_1",
        run_id="run_swap_1",
        agent="OrderSwapsAgent",
        action_type="order_swap",
        confidence_score=0.85,
        risk_level="low",
        payload={
            "order_id": "8877",
            "original_sku": "JEANS-32",
            "swap_sku": "JEANS-33",
            "swap_name": "Relaxed Jeans",
            "preserved_gmv": 78.0,
            "preserved_margin": 54.0,
            "customer_email": "shopper@test.com",
        },
        shadow_mode=False,
    )

    with patch("ecommerce_ops.pipeline.runner._resolve_shop_credentials", new_callable=AsyncMock) as mock_creds, \
         patch("ecommerce_ops.connectors.shopify.client.ShopifyClient.get_order", new_callable=AsyncMock) as mock_get_order, \
         patch("ecommerce_ops.connectors.shopify.client.ShopifyClient.update_order", new_callable=AsyncMock) as mock_update_order, \
         patch("ecommerce_ops.connectors.klaviyo.KlaviyoClient.track_event", new_callable=AsyncMock) as mock_klaviyo:

        mock_creds.return_value = ("brand.myshopify.com", "shpat_mock_token")
        mock_get_order.return_value = {"order": {"id": 8877, "tags": "PRIORITY"}}
        mock_klaviyo.return_value = {"status": "success"}

        success, msg = await execute_shop_action(action)

        assert success is True
        assert "Applied swap JEANS-32 -> JEANS-33 to order 8877" in msg
        mock_update_order.assert_called_once()
        sent_tags = mock_update_order.call_args[0][1]["tags"]
        assert "SWAP_ACTIVE:JEANS-32->JEANS-33" in sent_tags
        mock_klaviyo.assert_called_once()


@pytest.mark.asyncio
async def test_execute_shop_action_return_risk_keep_it_credit():
    action = ApprovalAction(
        id="act_return_keep_1",
        run_id="run_ret_1",
        agent="SmartReturnsAgent",
        action_type="return_risk_flag",
        confidence_score=0.80,
        risk_level="medium",
        payload={
            "order_id": "6655",
            "strategy": "keep_it_credit",
            "item_price": 35.0,
            "preserved_margin": 14.50,
            "reverse_costs_saved": 14.50,
        },
        shadow_mode=False,
    )

    with patch("ecommerce_ops.pipeline.runner._resolve_shop_credentials", new_callable=AsyncMock) as mock_creds, \
         patch("ecommerce_ops.connectors.shopify.client.ShopifyClient.get_order", new_callable=AsyncMock) as mock_get_order, \
         patch("ecommerce_ops.connectors.shopify.client.ShopifyClient.create_price_rule", new_callable=AsyncMock) as mock_price_rule, \
         patch("ecommerce_ops.connectors.shopify.client.ShopifyClient.create_discount_code", new_callable=AsyncMock) as mock_discount_code, \
         patch("ecommerce_ops.connectors.shopify.client.ShopifyClient.update_order", new_callable=AsyncMock) as mock_update_order:

        mock_creds.return_value = ("brand.myshopify.com", "shpat_mock_token")
        mock_get_order.return_value = {"order": {"id": 6655, "tags": ""}}
        mock_price_rule.return_value = {"price_rule": {"id": "pr_keep_101"}}
        mock_discount_code.return_value = {"discount_code": {"id": "dc_keep_101"}}

        success, msg = await execute_shop_action(action)

        assert success is True
        assert "Applied return strategy [KEEP_IT_CREDIT]" in msg
        mock_price_rule.assert_called_once()
        mock_discount_code.assert_called_once_with("pr_keep_101", "KEEPIT-6655")
        mock_update_order.assert_called_once()
        assert "RETURN_STRATEGY:KEEP_IT_CREDIT" in mock_update_order.call_args[0][1]["tags"]


# ── 4. ROI Analytics REST API Tests ─────────────────────────────────


def test_api_margin_preservation_summary(test_client):
    admin_user = User(
        username="admin",
        role=Role.ADMIN,
        permissions=["observability:view"],
    )
    with patch("ecommerce_ops.security.auth.get_current_user", return_value=admin_user):
        resp = test_client.get(
            "/api/v1/roi/margin-preservation",
            headers={"Authorization": "Bearer dummy_test_token"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert "total_gmv_preserved_usd" in data
        assert "total_net_margin_preserved_usd" in data
        assert "estimated_software_roi_multiple" in data


def test_api_return_evaluation_endpoint(test_client):
    admin_user = User(
        username="admin",
        role=Role.ADMIN,
        permissions=["observability:view"],
    )
    with patch("ecommerce_ops.security.auth.get_current_user", return_value=admin_user):
        resp = test_client.post(
            "/api/v1/roi/returns/evaluate",
            json={
                "item_price": 29.99,
                "category": "beauty",
                "return_reason": "damaged",
            },
            headers={"Authorization": "Bearer dummy_test_token"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["strategy"] == "keep_it_credit"
        assert data["avoided_reverse_costs"] > 0


def test_api_swap_evaluation_endpoint(test_client):
    admin_user = User(
        username="admin",
        role=Role.ADMIN,
        permissions=["observability:view"],
    )
    with patch("ecommerce_ops.security.auth.get_current_user", return_value=admin_user):
        resp = test_client.post(
            "/api/v1/roi/swaps/evaluate",
            json={
                "original_price": 50.0,
                "swap_price": 55.0,
            },
            headers={"Authorization": "Bearer dummy_test_token"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["preserved_gmv"] == 55.0
        assert data["margin_delta"] > 0
