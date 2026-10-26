"""
Tests for Option C: Klaviyo & Gorgias Event Bridges
Covers KlaviyoClient JSON:API event tracking, GorgiasClient ticket and internal note injection,
runner execute_shop_action integrations, and ecosystem API routes.
"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from ecommerce_ops.api.app import app
from ecommerce_ops.connectors.gorgias import GorgiasClient
from ecommerce_ops.connectors.klaviyo import KlaviyoClient
from ecommerce_ops.models import ApprovalAction
from ecommerce_ops.pipeline.runner import execute_shop_action
from ecommerce_ops.security.models import Permission, Role, User


@pytest.fixture
def test_client():
    return TestClient(app)


# ── 1. KlaviyoClient Tests ──────────────────────────────────────────


@pytest.mark.asyncio
async def test_klaviyo_track_event_payload_structure():
    client = KlaviyoClient(api_key="pk_test_123456789")
    with patch.object(client, "_request", new_callable=AsyncMock) as mock_request:
        mock_request.return_value = {"data": {"id": "evt_101"}}

        res = await client.track_event(
            metric_name="OpsIQ Cart Recovery Triggered",
            customer_email="shopper@domain.com",
            properties={"cart_id": "c100", "cart_total": 89.95, "discount_code": "RECOVER10"},
            customer_phone="+15551234567",
        )

        mock_request.assert_called_once()
        call_args = mock_request.call_args
        method, path = call_args[0]
        json_data = call_args[1]["json_data"]

        assert method == "POST"
        assert path == "/events/"
        data_attr = json_data["data"]["attributes"]
        assert data_attr["metric"]["data"]["attributes"]["name"] == "OpsIQ Cart Recovery Triggered"
        assert data_attr["profile"]["data"]["attributes"]["email"] == "shopper@domain.com"
        assert data_attr["profile"]["data"]["attributes"]["phone_number"] == "+15551234567"
        assert data_attr["properties"]["cart_total"] == 89.95
        assert res["data"]["id"] == "evt_101"
    await client.close()


@pytest.mark.asyncio
async def test_klaviyo_trigger_cart_recovery():
    client = KlaviyoClient(api_key="pk_test_123456789")
    with patch.object(client, "track_event", new_callable=AsyncMock) as mock_track:
        mock_track.return_value = {"success": True}

        await client.trigger_cart_recovery(
            customer_email="buyer@test.com",
            cart_id="cart_999",
            cart_total=145.0,
            discount_code="SAVE15",
            discount_value=15.0,
            checkout_url="https://store.com/checkout/999",
        )

        mock_track.assert_called_once()
        name = mock_track.call_args[1]["metric_name"]
        props = mock_track.call_args[1]["properties"]
        assert name == "OpsIQ Cart Recovery Triggered"
        assert props["cart_id"] == "cart_999"
        assert props["discount_code"] == "SAVE15"
        assert props["discount_value"] == 15.0
    await client.close()


@pytest.mark.asyncio
async def test_klaviyo_unconfigured_simulation():
    # Without API key, operates in simulation mode for dev
    client = KlaviyoClient(api_key=None)
    res = await client.track_event(
        metric_name="Test Metric",
        customer_email="test@domain.com",
        properties={},
    )
    assert res.get("simulated") is True
    await client.close()


# ── 2. GorgiasClient Tests ──────────────────────────────────────────


@pytest.mark.asyncio
async def test_gorgias_domain_sanitization():
    c1 = GorgiasClient(domain="brand", email="a@b.com", api_key="k1")
    assert c1.base_url == "https://brand.gorgias.com/api"

    c2 = GorgiasClient(domain="brand.gorgias.com", email="a@b.com", api_key="k2")
    assert c2.base_url == "https://brand.gorgias.com/api"

    c3 = GorgiasClient(domain="https://brand.gorgias.com/", email="a@b.com", api_key="k3")
    assert c3.base_url == "https://brand.gorgias.com/api"


@pytest.mark.asyncio
async def test_gorgias_add_internal_note():
    client = GorgiasClient(domain="mybrand", email="ops@mybrand.com", api_key="secret_key")
    with patch.object(client, "_request", new_callable=AsyncMock) as mock_req:
        mock_req.return_value = {"id": 501, "channel": "internal-note"}

        res = await client.add_internal_note(
            ticket_id="1234",
            note_body="OpsIQ AI Recommendation: Approve replacement item.",
        )

        mock_req.assert_called_once()
        method, path = mock_req.call_args[0]
        json_data = mock_req.call_args[1]["json_data"]

        assert method == "POST"
        assert path == "/tickets/1234/messages"
        assert json_data["channel"] == "internal-note"
        assert json_data["from_agent"] is True
        assert "OpsIQ AI Recommendation" in json_data["body_text"]
    await client.close()


@pytest.mark.asyncio
async def test_gorgias_create_ticket():
    client = GorgiasClient(domain="mybrand", email="ops@mybrand.com", api_key="secret_key")
    with patch.object(client, "_request", new_callable=AsyncMock) as mock_req:
        mock_req.return_value = {"id": 8801, "subject": "Damaged Package"}

        res = await client.create_ticket(
            customer_email="unhappy@shopper.com",
            subject="Damaged Package",
            message_body="My mug arrived cracked.",
            tags=["opsiq-damaged", "expedite"],
        )

        mock_req.assert_called_once()
        method, path = mock_req.call_args[0]
        json_data = mock_req.call_args[1]["json_data"]

        assert method == "POST"
        assert path == "/tickets"
        assert json_data["subject"] == "Damaged Package"
        assert json_data["customer"]["email"] == "unhappy@shopper.com"
        assert any(t["name"] == "opsiq-damaged" for t in json_data["tags"])
    await client.close()


# ── 3. Pipeline Runner execute_shop_action Integration ──────────────


@pytest.mark.asyncio
async def test_execute_shop_action_cart_recovery_with_klaviyo():
    action = ApprovalAction(
        id="act_cart_rec_1",
        agent="AbandonedCartAgent",
        action_type="cart_recovery",
        confidence_score=0.88,
        risk_level="low",
        payload={
            "cart_id": "cart_abc",
            "customer_email": "vip.buyer@gmail.com",
            "total_value": 120.00,
            "discount_code": "VIP15-ABC",
            "discount_value": 15.0,
            "strategy": "discount_urgency",
            "checkout_url": "https://brand.com/checkouts/abc",
        },
        evidence=[],
        impact={},
        shadow_mode=False,
    )

    with patch("ecommerce_ops.pipeline.runner._resolve_shop_credentials", new_callable=AsyncMock) as mock_creds, \
         patch("ecommerce_ops.connectors.shopify.client.ShopifyClient.create_price_rule", new_callable=AsyncMock) as mock_price_rule, \
         patch("ecommerce_ops.connectors.shopify.client.ShopifyClient.create_discount_code", new_callable=AsyncMock) as mock_discount_code, \
         patch("ecommerce_ops.connectors.klaviyo.KlaviyoClient.trigger_cart_recovery", new_callable=AsyncMock) as mock_klaviyo:

        mock_creds.return_value = ("brand.myshopify.com", "shpat_mock_token")
        mock_price_rule.return_value = {"price_rule": {"id": "pr_1001"}}
        mock_discount_code.return_value = {"discount_code": {"id": "dc_2001"}}
        mock_klaviyo.return_value = {"status": "success"}

        success, msg = await execute_shop_action(action)

        assert success is True
        assert "Dispatched Klaviyo cart recovery for cart cart_abc" in msg
        mock_price_rule.assert_called_once()
        mock_discount_code.assert_called_once_with("pr_1001", "VIP15-ABC")
        mock_klaviyo.assert_called_once()
        assert mock_klaviyo.call_args[1]["customer_email"] == "vip.buyer@gmail.com"
        assert mock_klaviyo.call_args[1]["discount_code"] == "VIP15-ABC"


@pytest.mark.asyncio
async def test_execute_shop_action_support_response_with_gorgias():
    action = ApprovalAction(
        id="act_support_rec_1",
        agent="CustomerSupportAgent",
        action_type="support_response",
        confidence_score=0.91,
        risk_level="low",
        payload={
            "ticket_id": "9012",
            "customer_email": "jane@customer.com",
            "draft_response": "We have expedited a replacement shipment for your order.",
            "sentiment": "negative",
            "urgency": "high",
        },
        evidence=[],
        impact={},
        shadow_mode=False,
    )

    with patch("ecommerce_ops.pipeline.runner._resolve_shop_credentials", new_callable=AsyncMock) as mock_creds, \
         patch("ecommerce_ops.connectors.gorgias.GorgiasClient.add_internal_note", new_callable=AsyncMock) as mock_note, \
         patch("ecommerce_ops.connectors.gorgias.GorgiasClient.update_ticket_tags", new_callable=AsyncMock) as mock_tags:

        mock_creds.return_value = ("brand.myshopify.com", "shpat_mock_token")
        mock_note.return_value = {"id": "msg_123"}
        mock_tags.return_value = {"status": "updated"}

        success, msg = await execute_shop_action(action)

        assert success is True
        assert "Injected OpsIQ draft note and tags into Gorgias ticket #9012" in msg
        mock_note.assert_called_once()
        assert "expedited a replacement shipment" in mock_note.call_args[0][1]
        mock_tags.assert_called_once_with("9012", ["opsiq-ai-draft", "sentiment-negative"])


# ── 4. Ecosystem Integration REST API Tests ─────────────────────────


def test_api_ecosystem_status(test_client):
    admin_user = User(
        id="usr_admin_1",
        email="admin@example.com",
        name="Admin",
        role=Role.ADMIN,
        permissions={Permission.INTEGRATIONS_MANAGE},
    )
    with patch("ecommerce_ops.security.auth.AuthenticationMiddleware._matches_configured_key", return_value=True), \
         patch("ecommerce_ops.security.auth.get_authenticated_user", return_value=admin_user):
        resp = test_client.get(
            "/api/v1/integrations/ecosystem-status",
            headers={"Authorization": "Bearer dummy_test_token"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert "klaviyo" in data
        assert "gorgias" in data
        assert "slack" in data


def test_api_klaviyo_and_gorgias_test_routes(test_client):
    admin_user = User(
        id="usr_admin_1",
        email="admin@example.com",
        name="Admin",
        role=Role.ADMIN,
        permissions={Permission.INTEGRATIONS_MANAGE},
    )
    with patch("ecommerce_ops.security.auth.AuthenticationMiddleware._matches_configured_key", return_value=True), \
         patch("ecommerce_ops.security.auth.get_authenticated_user", return_value=admin_user), \
         patch("ecommerce_ops.connectors.klaviyo.KlaviyoClient.trigger_cart_recovery", new_callable=AsyncMock) as mock_klaviyo, \
         patch("ecommerce_ops.connectors.gorgias.GorgiasClient.create_ticket", new_callable=AsyncMock) as mock_gorgias:

        mock_klaviyo.return_value = {"simulated": True}
        mock_gorgias.return_value = {"id": 111}

        # Klaviyo Test
        k_resp = test_client.post(
            "/api/v1/integrations/klaviyo/test",
            json={"customer_email": "test@domain.com", "cart_id": "c1"},
            headers={"Authorization": "Bearer dummy_test_token"},
        )
        assert k_resp.status_code == 200
        assert k_resp.json()["status"] == "success"

        # Gorgias Test
        g_resp = test_client.post(
            "/api/v1/integrations/gorgias/test",
            json={"customer_email": "test@domain.com", "subject": "Help", "message": "Test note"},
            headers={"Authorization": "Bearer dummy_test_token"},
        )
        assert g_resp.status_code == 200
        assert g_resp.json()["status"] == "success"
