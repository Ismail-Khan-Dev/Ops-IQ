"""
Tests for Phase 4: Merchant Pilot & App Store Launch
Validates:
1. Mandatory GDPR & App Store lifecycle webhooks (app/uninstalled, customers/redact, shop/redact, customers/data_request).
2. App Bridge v4 Session Token verification and dynamic CSP frame-ancestors middleware.
3. Shopify Billing Manager (Recurring charges, 14-day trials, activation, tier limits).
4. Pilot Onboarding Engine (Store readiness audit, pilot provisioning, cohort tracking).
5. REST API routes for onboarding, billing, and safety guardrails.
"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from ecommerce_ops.api.app import app
from ecommerce_ops.connectors.shopify.app_bridge import (
    ShopifyAppBridgeMiddleware,
    verify_shopify_session_token,
)
from ecommerce_ops.connectors.shopify.billing import (
    SHOPIFY_SUBSCRIPTION_PLANS,
    ShopifyBillingManager,
)
from ecommerce_ops.connectors.shopify.handlers.compliance_handlers import (
    handle_app_uninstalled,
    handle_customers_data_request,
    handle_customers_redact,
    handle_shop_redact,
)
from ecommerce_ops.connectors.shopify.handlers.order_handlers import (
    SHOPIFY_TASK_NAMES,
    WEBHOOK_HANDLERS,
)
from ecommerce_ops.connectors.shopify.onboarding import (
    MANDATORY_COMPLIANCE_TOPICS,
    REQUIRED_PILOT_SCOPES,
    PilotOnboardingEngine,
)
from ecommerce_ops.models import ShopifyShopCredential, StoreSettings
from ecommerce_ops.security.models import Role, User


@pytest.fixture
def test_client():
    return TestClient(app)


# ── 1. Mandatory GDPR & App Store Lifecycle Webhooks ────────────────────────


def test_mandatory_topics_registered_in_webhook_registry():
    """All 4 mandatory Shopify App Store compliance topics must be registered."""
    for topic in MANDATORY_COMPLIANCE_TOPICS:
        assert topic in WEBHOOK_HANDLERS, f"Missing handler for mandatory topic {topic}"
        assert topic in SHOPIFY_TASK_NAMES, f"Missing task name for mandatory topic {topic}"


@pytest.mark.asyncio
async def test_handle_customers_data_request():
    payload = {
        "shop_id": 998877,
        "shop_domain": "pilot-store.myshopify.com",
        "customer": {"id": 12345, "email": "shopper@example.com", "phone": "+15551234567"},
        "orders_requested": [101, 102],
    }
    with patch("ecommerce_ops.models.async_session_factory") as mock_session_ctx:
        mock_session = AsyncMock()
        mock_session_ctx.return_value.__aenter__.return_value = mock_session

        res = await handle_customers_data_request(payload, "pilot-store.myshopify.com")
        assert res["status"] == "acknowledged"
        assert res["customer_id"] == 12345
        assert res["orders_count"] == 2
        mock_session.commit.assert_called_once()


@pytest.mark.asyncio
async def test_handle_customers_redact():
    payload = {
        "shop_id": 998877,
        "shop_domain": "pilot-store.myshopify.com",
        "customer": {"id": 54321, "email": "redact@example.com"},
        "orders_to_redact": [201],
    }
    with patch("ecommerce_ops.models.async_session_factory") as mock_session_ctx:
        mock_session = AsyncMock()
        mock_session_ctx.return_value.__aenter__.return_value = mock_session

        res = await handle_customers_redact(payload, "pilot-store.myshopify.com")
        assert res["status"] == "redacted"
        assert res["customer_id"] == 54321
        mock_session.commit.assert_called_once()


@pytest.mark.asyncio
async def test_handle_shop_redact():
    payload = {
        "shop_id": 998877,
        "shop_domain": "pilot-store.myshopify.com",
    }
    with patch("ecommerce_ops.models.async_session_factory") as mock_session_ctx:
        mock_session = AsyncMock()
        mock_session_ctx.return_value.__aenter__.return_value = mock_session

        res = await handle_shop_redact(payload, "pilot-store.myshopify.com")
        assert res["status"] == "purged"
        assert res["shop_domain"] == "pilot-store.myshopify.com"
        mock_session.commit.assert_called_once()


@pytest.mark.asyncio
async def test_handle_app_uninstalled():
    payload = {
        "id": 998877,
        "myshopify_domain": "pilot-store.myshopify.com",
    }
    mock_cred = ShopifyShopCredential(
        shop_domain="pilot-store.myshopify.com",
        access_token="shpat_test_token",
        is_active=True,
    )
    with patch("ecommerce_ops.models.async_session_factory") as mock_session_ctx:
        mock_session = AsyncMock()
        mock_session_ctx.return_value.__aenter__.return_value = mock_session

        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = [mock_cred]
        mock_session.execute.return_value = mock_result

        res = await handle_app_uninstalled(payload, "pilot-store.myshopify.com")
        assert res["status"] == "deactivated"
        assert mock_cred.is_active is False
        mock_session.commit.assert_called_once()


# ── 2. App Bridge v4 Session Token & Dynamic CSP Middleware ─────────────────


def test_verify_shopify_session_token_success():
    payload = {
        "iss": "https://pilot-brand.myshopify.com/admin",
        "dest": "https://pilot-brand.myshopify.com",
        "aud": "test_api_key_123",
        "sub": "user_456",
        "exp": 1999999999,
        "nbf": 1000000000,
    }
    with patch("jwt.decode", return_value=payload), \
         patch("ecommerce_ops.config.settings.SHOPIFY_API_KEY", "test_api_key_123"), \
         patch("ecommerce_ops.config.settings.SHOPIFY_API_SECRET") as mock_sec:
        mock_sec.get_secret_value.return_value = "mock_secret"

        verified = verify_shopify_session_token("mock.jwt.token")
        assert verified["shop_domain"] == "pilot-brand.myshopify.com"
        assert verified["sub"] == "user_456"


def test_verify_shopify_session_token_invalid_issuer():
    payload = {
        "iss": "https://malicious-site.com",
        "dest": "https://pilot-brand.myshopify.com",
        "aud": "test_api_key_123",
        "sub": "user_456",
    }
    with patch("jwt.decode", return_value=payload), \
         patch("ecommerce_ops.config.settings.SHOPIFY_API_KEY", "test_api_key_123"), \
         patch("ecommerce_ops.config.settings.SHOPIFY_API_SECRET") as mock_sec:
        mock_sec.get_secret_value.return_value = "mock_secret"

        with pytest.raises(ValueError, match="Invalid token issuer"):
            verify_shopify_session_token("mock.jwt.token")


def test_app_bridge_csp_middleware(test_client):
    """Test CSP frame-ancestors header injection for Shopify Admin embedding."""
    resp = test_client.get("/api/v1/version?shop=pilot-brand.myshopify.com")
    assert resp.status_code == 200
    csp = resp.headers.get("Content-Security-Policy", "")
    assert "frame-ancestors" in csp
    assert "https://pilot-brand.myshopify.com" in csp
    assert "https://admin.shopify.com" in csp


# ── 3. Shopify Billing Manager Tests ────────────────────────────────────────


def test_subscription_plan_tiers():
    assert "starter" in SHOPIFY_SUBSCRIPTION_PLANS
    assert "growth" in SHOPIFY_SUBSCRIPTION_PLANS
    assert "enterprise" in SHOPIFY_SUBSCRIPTION_PLANS

    growth = SHOPIFY_SUBSCRIPTION_PLANS["growth"]
    assert growth["price"] == 999.0
    assert growth["trial_days"] == 14
    assert growth["max_orders_per_month"] == 5000


@pytest.mark.asyncio
async def test_billing_create_recurring_charge():
    mgr = ShopifyBillingManager("test-shop.myshopify.com", "shpat_test_token")

    mock_charge_response = {
        "recurring_application_charge": {
            "id": 998811,
            "name": "Ops-IQ Growth",
            "price": "999.00",
            "status": "pending",
            "confirmation_url": "https://test-shop.myshopify.com/admin/charges/998811/confirm_recurring_application_charge",
            "trial_days": 14,
        }
    }

    with patch.object(mgr.client, "_post_with_retry", new_callable=AsyncMock) as mock_post, \
         patch.object(mgr.client, "close", new_callable=AsyncMock):
        mock_post.return_value = mock_charge_response

        res = await mgr.create_recurring_charge(plan_tier="growth", test_mode=True)
        assert res["charge_id"] == 998811
        assert res["status"] == "pending"
        assert res["price"] == 999.0
        assert "confirm_recurring_application_charge" in res["confirmation_url"]


@pytest.mark.asyncio
async def test_billing_activate_charge():
    mgr = ShopifyBillingManager("test-shop.myshopify.com", "shpat_test_token")

    mock_activate_response = {
        "recurring_application_charge": {
            "id": 998811,
            "status": "active",
        }
    }

    with patch.object(mgr.client, "_post_with_retry", new_callable=AsyncMock) as mock_post, \
         patch.object(mgr.client, "close", new_callable=AsyncMock):
        mock_post.return_value = mock_activate_response

        res = await mgr.activate_charge(998811)
        assert res["charge_id"] == 998811
        assert res["status"] == "active"
        assert res["activated"] is True


@pytest.mark.asyncio
async def test_billing_get_active_subscription():
    mgr = ShopifyBillingManager("test-shop.myshopify.com", "shpat_test_token")

    mock_charges = {
        "recurring_application_charges": [
            {
                "id": 998811,
                "name": "Ops-IQ Growth",
                "price": "999.00",
                "status": "active",
                "billing_on": "2026-11-04",
            }
        ]
    }

    with patch.object(mgr.client, "_get_with_retry", new_callable=AsyncMock) as mock_get, \
         patch.object(mgr.client, "close", new_callable=AsyncMock):
        mock_get.return_value = mock_charges

        sub = await mgr.get_active_subscription()
        assert sub["has_active_subscription"] is True
        assert sub["plan_name"] == "Ops-IQ Growth"
        assert sub["status"] == "active"


# ── 4. Pilot Onboarding & Pre-Flight Readiness Engine ───────────────────────


@pytest.mark.asyncio
async def test_verify_store_readiness_missing_credentials():
    with patch("ecommerce_ops.models.async_session_factory") as mock_session_ctx, \
         patch("ecommerce_ops.config.settings.SHOPIFY_SHOP_DOMAIN", None):
        mock_session = AsyncMock()
        mock_session_ctx.return_value.__aenter__.return_value = mock_session

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_result.scalar.return_value = 0
        mock_session.execute.return_value = mock_result

        readiness = await PilotOnboardingEngine.verify_store_readiness("unregistered.myshopify.com")
        assert readiness["is_ready_for_pilot"] is False
        assert readiness["checklist"]["credentials"]["status"] == "failed"
        assert any("Install Ops-IQ via Shopify OAuth" in r for r in readiness["recommendations"])


@pytest.mark.asyncio
async def test_verify_store_readiness_complete():
    mock_cred = ShopifyShopCredential(
        shop_domain="perfect-pilot.myshopify.com",
        access_token="shpat_valid_pilot_token",
        scope="read_orders,write_orders,read_products,write_products,read_inventory,read_assigned_fulfillment_orders,write_assigned_fulfillment_orders",
        is_active=True,
    )
    mock_settings = StoreSettings(
        id=1,
        shadow_mode=True,
        fraud_threshold=70,
    )

    with patch("ecommerce_ops.models.async_session_factory") as mock_session_ctx:
        mock_session = AsyncMock()
        mock_session_ctx.return_value.__aenter__.return_value = mock_session

        # Setup mock queries sequence
        res1 = MagicMock()
        res1.scalar_one_or_none.return_value = mock_cred
        res2 = MagicMock()
        res2.scalar_one_or_none.return_value = mock_settings
        res3 = MagicMock()
        res3.scalar.return_value = 150  # products
        res4 = MagicMock()
        res4.scalar.return_value = 450  # orders

        mock_session.execute.side_effect = [res1, res2, res3, res4]

        readiness = await PilotOnboardingEngine.verify_store_readiness("perfect-pilot.myshopify.com")
        assert readiness["is_ready_for_pilot"] is True
        assert readiness["readiness_score"] >= 80
        assert readiness["checklist"]["credentials"]["status"] == "passed"
        assert readiness["checklist"]["scopes"]["status"] == "passed"
        assert readiness["checklist"]["fulfillment_interceptor_3pl"]["status"] == "passed"
        assert readiness["checklist"]["safety_guardrails"]["shadow_mode_active"] is True


@pytest.mark.asyncio
async def test_provision_pilot_merchant():
    with patch("ecommerce_ops.models.async_session_factory") as mock_session_ctx, \
         patch("ecommerce_ops.connectors.shopify.billing.ShopifyBillingManager.for_shop") as mock_billing_mgr, \
         patch.object(PilotOnboardingEngine, "verify_store_readiness") as mock_readiness:

        mock_session = AsyncMock()
        mock_session_ctx.return_value.__aenter__.return_value = mock_session
        res_cred = MagicMock()
        res_cred.scalar_one_or_none.return_value = None
        res_settings = MagicMock()
        res_settings.scalar_one_or_none.return_value = None
        mock_session.execute.side_effect = [res_cred, res_settings]

        mock_mgr_instance = AsyncMock()
        mock_mgr_instance.create_recurring_charge.return_value = {
            "charge_id": 112233,
            "confirmation_url": "https://confirm.charge/url",
            "trial_days": 14,
            "price": 999.0,
        }
        mock_billing_mgr.return_value = mock_mgr_instance

        mock_readiness.return_value = {
            "is_ready_for_pilot": True,
            "readiness_score": 95,
        }

        res = await PilotOnboardingEngine.provision_pilot_merchant(
            shop_domain="pilot-brand-1.myshopify.com",
            plan_tier="growth",
            shadow_mode=True,
            auto_sync=False,
        )

        assert res["success"] is True
        assert res["shop_domain"] == "pilot-brand-1.myshopify.com"
        assert res["plan_tier"] == "growth"
        assert res["shadow_mode"] is True
        assert res["billing"]["status"] == "charge_created"
        assert res["billing"]["charge_id"] == 112233


# ── 5. REST API Integration Endpoints ───────────────────────────────────────


def test_api_list_billing_plans(test_client):
    resp = test_client.get("/api/v1/billing/plans")
    assert resp.status_code == 200
    data = resp.json()
    assert "starter" in data["plans"]
    assert "growth" in data["plans"]
    assert "enterprise" in data["plans"]
    assert data["trial_days"] == 14


def test_api_onboarding_readiness_endpoint(test_client):
    admin_user = User(
        username="admin",
        role=Role.ADMIN,
        permissions=["shopify:configure"],
    )
    with patch("ecommerce_ops.security.auth.get_current_user", return_value=admin_user), \
         patch.object(PilotOnboardingEngine, "verify_store_readiness") as mock_verify:

        mock_verify.return_value = {
            "shop_domain": "pilot.myshopify.com",
            "readiness_score": 90,
            "is_ready_for_pilot": True,
            "checklist": {},
        }

        resp = test_client.get(
            "/api/v1/onboarding/readiness?shop=pilot.myshopify.com",
            headers={"Authorization": "Bearer dummy_test_token"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["readiness_score"] == 90
        assert data["is_ready_for_pilot"] is True


def test_api_onboarding_provision_endpoint(test_client):
    admin_user = User(
        username="admin",
        role=Role.ADMIN,
        permissions=["shopify:configure"],
    )
    with patch("ecommerce_ops.security.auth.get_current_user", return_value=admin_user), \
         patch.object(PilotOnboardingEngine, "provision_pilot_merchant") as mock_provision:

        mock_provision.return_value = {
            "success": True,
            "shop_domain": "brand-pilot.myshopify.com",
            "plan_tier": "growth",
            "shadow_mode": True,
        }

        resp = test_client.post(
            "/api/v1/onboarding/provision",
            json={
                "shop_domain": "brand-pilot.myshopify.com",
                "plan_tier": "growth",
                "shadow_mode": True,
            },
            headers={"Authorization": "Bearer dummy_test_token"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is True
        assert data["shop_domain"] == "brand-pilot.myshopify.com"


def test_api_billing_callback_endpoint(test_client):
    with patch("ecommerce_ops.connectors.shopify.billing.ShopifyBillingManager.for_shop") as mock_billing_mgr:
        mock_mgr_instance = AsyncMock()
        mock_mgr_instance.activate_charge.return_value = {
            "charge_id": "778899",
            "status": "active",
            "activated": True,
        }
        mock_billing_mgr.return_value = mock_mgr_instance

        resp = test_client.get("/api/v1/billing/callback?shop=test.myshopify.com&charge_id=778899")
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "success"
        assert data["charge_id"] == "778899"
        assert data["activation"]["activated"] is True


def test_api_update_pilot_settings_endpoint(test_client):
    admin_user = User(
        username="admin",
        role=Role.ADMIN,
        permissions=["shopify:configure"],
    )
    with patch("ecommerce_ops.security.auth.get_current_user", return_value=admin_user), \
         patch.object(PilotOnboardingEngine, "update_pilot_settings") as mock_update:

        mock_update.return_value = {
            "success": True,
            "shadow_mode": False,
            "fraud_threshold": 80,
        }

        resp = test_client.patch(
            "/api/v1/onboarding/settings",
            json={
                "shadow_mode": False,
                "fraud_threshold": 80,
            },
            headers={"Authorization": "Bearer dummy_test_token"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is True
        assert data["shadow_mode"] is False
        assert data["fraud_threshold"] == 80
