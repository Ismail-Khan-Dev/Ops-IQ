"""
Tests for Option A: 3PL Fulfillment Hold Interceptor
Covers ShopifyClient Fulfillment Orders API, runner actions, fast-path interceptor,
webhook integration, and REST endpoints.
"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import pytest_asyncio
from fastapi.testclient import TestClient

from ecommerce_ops.api.app import app
from ecommerce_ops.connectors.shopify.client import ShopifyClient
from ecommerce_ops.connectors.shopify.fulfillment_interceptor import FulfillmentHoldInterceptor
from ecommerce_ops.connectors.shopify.handlers.order_handlers import handle_order_created
from ecommerce_ops.connectors.shopify.webhooks import WebhookEvent
from ecommerce_ops.models import ApprovalAction
from ecommerce_ops.pipeline.runner import execute_shop_action
from ecommerce_ops.security.models import Role, User


@pytest.fixture
def test_client():
    return TestClient(app)


@pytest.fixture
def mock_shopify_client():
    client = ShopifyClient(
        shop_domain="brand-test.myshopify.com",
        access_token="shpat_test_token_12345",
        api_version="2024-01",
    )
    return client


# ── 1. ShopifyClient Fulfillment Orders Tests ───────────────────────


@pytest.mark.asyncio
async def test_get_fulfillment_orders(mock_shopify_client):
    with patch.object(mock_shopify_client, "_get_with_retry", new_callable=AsyncMock) as mock_get:
        mock_get.return_value = {
            "fulfillment_orders": [
                {"id": 101, "order_id": 901, "status": "open"},
                {"id": 102, "order_id": 901, "status": "open"},
            ]
        }
        res = await mock_shopify_client.get_fulfillment_orders("901")
        assert len(res["fulfillment_orders"]) == 2
        mock_get.assert_called_once_with("/orders/901/fulfillment_orders.json")


@pytest.mark.asyncio
async def test_hold_fulfillment_order(mock_shopify_client):
    with patch.object(mock_shopify_client, "_post_with_retry", new_callable=AsyncMock) as mock_post:
        mock_post.return_value = {"fulfillment_order": {"id": 101, "status": "on_hold"}}
        res = await mock_shopify_client.hold_fulfillment_order(
            "101", reason="high_risk_of_fraud", reason_notes="OpsIQ test"
        )
        assert res["fulfillment_order"]["status"] == "on_hold"
        mock_post.assert_called_once_with(
            "/fulfillment_orders/101/hold.json",
            json={
                "fulfillment_hold": {
                    "reason": "high_risk_of_fraud",
                    "reason_notes": "OpsIQ test",
                }
            },
        )


@pytest.mark.asyncio
async def test_release_fulfillment_order_hold(mock_shopify_client):
    with patch.object(mock_shopify_client, "_post_with_retry", new_callable=AsyncMock) as mock_post:
        mock_post.return_value = {"fulfillment_order": {"id": 101, "status": "open"}}
        res = await mock_shopify_client.release_fulfillment_order_hold("101")
        assert res["fulfillment_order"]["status"] == "open"
        mock_post.assert_called_once_with(
            "/fulfillment_orders/101/release_hold.json",
            json={},
        )


@pytest.mark.asyncio
async def test_hold_order_fulfillments_multi_and_idempotent(mock_shopify_client):
    # Order has 1 open, 1 on_hold, 1 closed
    mock_fos = {
        "fulfillment_orders": [
            {"id": 101, "order_id": 901, "status": "open"},
            {"id": 102, "order_id": 901, "status": "on_hold"},
            {"id": 103, "order_id": 901, "status": "closed"},
        ]
    }
    with patch.object(mock_shopify_client, "get_fulfillment_orders", new_callable=AsyncMock) as mock_get_fo, \
         patch.object(mock_shopify_client, "hold_fulfillment_order", new_callable=AsyncMock) as mock_hold:
        mock_get_fo.return_value = mock_fos
        mock_hold.return_value = {"fulfillment_order": {"id": 101, "status": "on_hold"}}

        results = await mock_shopify_client.hold_order_fulfillments("901")

        assert len(results) == 2  # 101 held, 102 already_held; 103 closed ignored
        assert results[0]["fulfillment_order_id"] == "101"
        assert results[0]["status"] == "on_hold"
        assert results[1]["fulfillment_order_id"] == "102"
        assert results[1]["already_held"] is True
        mock_hold.assert_called_once_with(
            "101",
            reason="high_risk_of_fraud",
            reason_notes="OpsIQ 3PL Interceptor: High fraud risk detected.",
        )


@pytest.mark.asyncio
async def test_release_order_fulfillments(mock_shopify_client):
    mock_fos = {
        "fulfillment_orders": [
            {"id": 101, "order_id": 901, "status": "on_hold"},
            {"id": 102, "order_id": 901, "status": "open"},
        ]
    }
    with patch.object(mock_shopify_client, "get_fulfillment_orders", new_callable=AsyncMock) as mock_get_fo, \
         patch.object(mock_shopify_client, "release_fulfillment_order_hold", new_callable=AsyncMock) as mock_rel:
        mock_get_fo.return_value = mock_fos
        mock_rel.return_value = {"fulfillment_order": {"id": 101, "status": "open"}}

        results = await mock_shopify_client.release_order_fulfillments("901")

        assert len(results) == 2
        assert results[0]["fulfillment_order_id"] == "101"
        assert results[0]["status"] == "released"
        assert results[1]["fulfillment_order_id"] == "102"
        assert results[1]["already_released"] is True
        mock_rel.assert_called_once_with("101")


# ── 2. Runner execute_shop_action Live Actions ───────────────────────


@pytest.mark.asyncio
async def test_execute_shop_action_fraud_hold():
    action = ApprovalAction(
        id="act_fraud_1",
        run_id="run_1",
        agent="FraudAgent",
        action_type="fraud_hold",
        confidence_score=0.95,
        risk_level="high",
        payload={"order_id": "999888", "fraud_score": 88},
        shadow_mode=False,
    )

    with patch("ecommerce_ops.pipeline.runner._resolve_shop_credentials", new_callable=AsyncMock) as mock_creds, \
         patch("ecommerce_ops.connectors.shopify.client.ShopifyClient.get_order", new_callable=AsyncMock) as mock_get_order, \
         patch("ecommerce_ops.connectors.shopify.client.ShopifyClient.update_order", new_callable=AsyncMock) as mock_update_order, \
         patch("ecommerce_ops.connectors.shopify.client.ShopifyClient.hold_order_fulfillments", new_callable=AsyncMock) as mock_hold_fo:

        mock_creds.return_value = ("test-shop.myshopify.com", "shpat_mock_token")
        mock_get_order.return_value = {"order": {"id": 999888, "tags": "VIP, EXPEDITE"}}
        mock_hold_fo.return_value = [{"fulfillment_order_id": "fo_1", "status": "on_hold"}]

        success, msg = await execute_shop_action(action)

        assert success is True
        assert "Applied FRAUD_HOLD to order 999888 and intercepted 1 fulfillment order(s)" in msg
        # Verifies tags were appended cleanly
        mock_update_order.assert_called_once_with("999888", {"tags": "VIP, EXPEDITE, FRAUD_HOLD"})
        mock_hold_fo.assert_called_once()


@pytest.mark.asyncio
async def test_execute_shop_action_release_fraud_hold():
    action = ApprovalAction(
        id="act_rel_1",
        run_id="run_1",
        agent="FraudAgent",
        action_type="release_fraud_hold",
        confidence_score=0.90,
        risk_level="medium",
        payload={"order_id": "999888"},
        shadow_mode=False,
    )

    with patch("ecommerce_ops.pipeline.runner._resolve_shop_credentials", new_callable=AsyncMock) as mock_creds, \
         patch("ecommerce_ops.connectors.shopify.client.ShopifyClient.get_order", new_callable=AsyncMock) as mock_get_order, \
         patch("ecommerce_ops.connectors.shopify.client.ShopifyClient.update_order", new_callable=AsyncMock) as mock_update_order, \
         patch("ecommerce_ops.connectors.shopify.client.ShopifyClient.release_order_fulfillments", new_callable=AsyncMock) as mock_rel_fo:

        mock_creds.return_value = ("test-shop.myshopify.com", "shpat_mock_token")
        mock_get_order.return_value = {"order": {"id": 999888, "tags": "VIP, FRAUD_HOLD"}}
        mock_rel_fo.return_value = [{"fulfillment_order_id": "fo_1", "status": "released"}]

        success, msg = await execute_shop_action(action)

        assert success is True
        assert "Released FRAUD_HOLD for order 999888 and unblocked 1 fulfillment order(s)" in msg
        # Verifies FRAUD_HOLD tag removed and FRAUD_CLEARED added
        mock_update_order.assert_called_once_with("999888", {"tags": "VIP, FRAUD_CLEARED"})
        mock_rel_fo.assert_called_once()


# ── 3. Fast-Path Interceptor Tests ───────────────────────────────────


def test_interceptor_assess_risk_high_value_and_address_mismatch():
    order = {
        "id": "12345",
        "total_price": "1450.00",
        "shipping_address": {"country_code": "US", "zip": "90210"},
        "billing_address": {"country_code": "NG", "zip": "10001"},
    }
    score, factors, should_hold = FulfillmentHoldInterceptor.assess_order_fraud_risk(order)
    assert score >= 70
    assert should_hold is True
    assert "high_order_value_over_1000" in factors
    assert "international_billing_shipping_mismatch" in factors


def test_interceptor_assess_risk_low_risk_order():
    order = {
        "id": "54321",
        "total_price": "45.00",
        "shipping_address": {"country_code": "US", "zip": "10001"},
        "billing_address": {"country_code": "US", "zip": "10001"},
    }
    score, factors, should_hold = FulfillmentHoldInterceptor.assess_order_fraud_risk(order)
    assert score < 50
    assert should_hold is False


@pytest.mark.asyncio
async def test_interceptor_auto_hold_execution():
    high_risk_order = {
        "id": "777666",
        "total_price": "1200.00",
        "shipping_address": {"country_code": "US", "zip": "90210"},
        "billing_address": {"country_code": "CA", "zip": "M5V2T6"},
    }
    with patch("ecommerce_ops.connectors.shopify.client.ShopifyClient.get_order", new_callable=AsyncMock) as mock_get_order, \
         patch("ecommerce_ops.connectors.shopify.client.ShopifyClient.update_order", new_callable=AsyncMock) as mock_update_order, \
         patch("ecommerce_ops.connectors.shopify.client.ShopifyClient.hold_order_fulfillments", new_callable=AsyncMock) as mock_hold_fo:

        mock_get_order.return_value = {"order": {"id": 777666, "tags": ""}}
        mock_hold_fo.return_value = [{"fulfillment_order_id": "fo_777", "status": "on_hold"}]

        res = await FulfillmentHoldInterceptor.intercept_order_for_3pl(
            high_risk_order,
            shop_domain="brand.myshopify.com",
            access_token="shpat_valid_token",
        )

        assert res["intercepted"] is True
        assert res["tag_applied"] is True
        assert len(res["held_fulfillments"]) == 1
        mock_hold_fo.assert_called_once()
        mock_update_order.assert_called_once_with("777666", {"tags": "FRAUD_HOLD"})


# ── 4. Webhook Ingestion with Interceptor ────────────────────────────


@pytest.mark.asyncio
async def test_order_created_webhook_invokes_interceptor():
    event = WebhookEvent(
        topic="orders/create",
        shop_domain="brand.myshopify.com",
        api_version="2024-01",
        body={
            "id": 888999,
            "total_price": "1500.00",
            "currency": "USD",
            "email": "test@domain.com",
            "shipping_address": {"country_code": "US", "zip": "10001"},
            "billing_address": {"country_code": "UK", "zip": "SW1A1AA"},
        },
        headers={},
    )
    with patch("ecommerce_ops.connectors.shopify.fulfillment_interceptor.FulfillmentHoldInterceptor.intercept_order_for_3pl", new_callable=AsyncMock) as mock_intercept, \
         patch("ecommerce_ops.connectors.shopify.handlers.order_handlers._handle", new_callable=AsyncMock) as mock_handle:

        mock_intercept.return_value = {
            "order_id": "888999",
            "intercepted": True,
            "risk_score": 85,
            "risk_factors": ["international_billing_shipping_mismatch"],
        }

        await handle_order_created(event)

        mock_intercept.assert_called_once()
        mock_handle.assert_called_once()


# ── 5. REST Endpoints for 3PL Fulfillment Control ───────────────────


def test_api_fulfillment_orders_endpoint(test_client):
    admin_user = User(
        username="admin",
        role=Role.ADMIN,
        permissions=["shopify:view", "shopify:configure"],
    )
    with patch("ecommerce_ops.security.auth.get_current_user", return_value=admin_user), \
         patch("ecommerce_ops.connectors.shopify.client.ShopifyClient.get_fulfillment_orders", new_callable=AsyncMock) as mock_get_fo:

        mock_get_fo.return_value = {
            "fulfillment_orders": [{"id": "fo_1", "status": "open"}]
        }

        resp = test_client.get(
            "/api/v1/shopify/orders/12345/fulfillment-orders",
            headers={"Authorization": "Bearer dummy_test_token"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert len(data["fulfillment_orders"]) == 1


def test_api_hold_and_release_endpoints(test_client):
    admin_user = User(
        username="admin",
        role=Role.ADMIN,
        permissions=["shopify:view", "shopify:configure"],
    )
    with patch("ecommerce_ops.security.auth.get_current_user", return_value=admin_user), \
         patch("ecommerce_ops.connectors.shopify.client.ShopifyClient.get_order", new_callable=AsyncMock) as mock_get_order, \
         patch("ecommerce_ops.connectors.shopify.client.ShopifyClient.update_order", new_callable=AsyncMock) as mock_update_order, \
         patch("ecommerce_ops.connectors.shopify.client.ShopifyClient.hold_order_fulfillments", new_callable=AsyncMock) as mock_hold_fo, \
         patch("ecommerce_ops.connectors.shopify.client.ShopifyClient.release_order_fulfillments", new_callable=AsyncMock) as mock_rel_fo:

        mock_get_order.return_value = {"order": {"id": 12345, "tags": ""}}
        mock_hold_fo.return_value = [{"fulfillment_order_id": "fo_1", "status": "on_hold"}]
        mock_rel_fo.return_value = [{"fulfillment_order_id": "fo_1", "status": "released"}]

        # Test Hold Endpoint
        hold_resp = test_client.post(
            "/api/v1/shopify/orders/12345/hold-fulfillment",
            json={"reason": "high_risk_of_fraud", "reason_notes": "Operator manual test"},
            headers={"Authorization": "Bearer dummy_test_token"},
        )
        assert hold_resp.status_code == 200
        hold_data = hold_resp.json()
        assert hold_data["status"] == "held"
        assert hold_data["held_count"] == 1

        # Test Release Endpoint
        rel_resp = test_client.post(
            "/api/v1/shopify/orders/12345/release-fulfillment",
            headers={"Authorization": "Bearer dummy_test_token"},
        )
        assert rel_resp.status_code == 200
        rel_data = rel_resp.json()
        assert rel_data["status"] == "released"
        assert rel_data["unblocked_count"] == 1
