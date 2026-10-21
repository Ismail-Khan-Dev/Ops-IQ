"""
Tests for Ad-Spend Bleed Stopper (Step 2: Meta Ads OOS Auto-Pause Guardian).
Validates inventory-to-ad set synchronization, automated ad pauses on 0-stock SKUs,
reactivation on restock, financial spend-preservation metrics, and REST API endpoints.
"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from ecommerce_ops.api.app import app
from ecommerce_ops.connectors.meta import MetaAdsClient
from ecommerce_ops.marketing.ad_spend_guardian import AdSpendGuardian, _PAUSED_ADSETS
from ecommerce_ops.mcp.tools import execute_tool
from ecommerce_ops.security.models import Role, User


@pytest.fixture
def test_client():
    return TestClient(app)


@pytest.fixture(autouse=True)
def clean_paused_registry():
    _PAUSED_ADSETS.clear()
    yield
    _PAUSED_ADSETS.clear()


# ── 1. AdSpendGuardian Unit Tests ───────────────────────────────────────────


def test_matches_adset_to_sku_matching():
    guardian = AdSpendGuardian()
    assert guardian._matches_adset_to_sku("Retargeting - SKU-101 - Broad", "SKU-101", None) is True
    assert guardian._matches_adset_to_sku("Summer Collection - Linen Shirt M", "LNN-01", "Linen Shirt") is True
    assert guardian._matches_adset_to_sku("Completely Unrelated Ad", "SKU-999", "Denim Jacket") is False


@pytest.mark.asyncio
async def test_sync_inventory_to_ads_pauses_oos():
    mock_client = AsyncMock(spec=MetaAdsClient)
    mock_client.get_adsets.return_value = [
        {
            "id": "adset_101",
            "name": "Scale - Black Linen Shirt - SKU-BLK-M",
            "status": "ACTIVE",
            "daily_budget": "10000",  # $100.00/day
            "campaign_id": "cmp_1",
        }
    ]
    mock_client.pause_adset.return_value = {"status": "PAUSED"}

    guardian = AdSpendGuardian(meta_client=mock_client)

    inventory_payload = [
        {
            "sku": "SKU-BLK-M",
            "inventory_quantity": 0,  # OUT OF STOCK!
            "title": "Black Linen Shirt",
        }
    ]

    report = await guardian.sync_inventory_to_ads(inventory_payload, oos_threshold=0)

    assert len(report["adsets_paused"]) == 1
    assert report["adsets_paused"][0]["adset_id"] == "adset_101"
    assert report["adsets_paused"][0]["daily_budget_usd"] == 100.0
    assert report["daily_ad_spend_saved_usd"] == 100.0
    mock_client.pause_adset.assert_called_once_with("adset_101")


@pytest.mark.asyncio
async def test_sync_inventory_to_ads_unpauses_on_restock():
    mock_client = AsyncMock(spec=MetaAdsClient)
    mock_client.get_adsets.return_value = [
        {
            "id": "adset_101",
            "name": "Scale - Black Linen Shirt - SKU-BLK-M",
            "status": "PAUSED",
            "daily_budget": "10000",
            "campaign_id": "cmp_1",
        }
    ]
    mock_client.unpause_adset.return_value = {"status": "ACTIVE"}

    guardian = AdSpendGuardian(meta_client=mock_client)

    # Pre-seed adset as paused in registry
    _PAUSED_ADSETS["adset_101"] = {
        "adset_name": "Scale - Black Linen Shirt - SKU-BLK-M",
        "sku": "SKU-BLK-M",
        "daily_budget": 100.0,
    }

    # Inventory restocked to 45 units!
    inventory_payload = [
        {
            "sku": "SKU-BLK-M",
            "inventory_quantity": 45,
            "title": "Black Linen Shirt",
        }
    ]

    report = await guardian.sync_inventory_to_ads(inventory_payload, oos_threshold=0)

    assert len(report["adsets_unpaused"]) == 1
    assert report["adsets_unpaused"][0]["adset_id"] == "adset_101"
    mock_client.unpause_adset.assert_called_once_with("adset_101")
    assert "adset_101" not in _PAUSED_ADSETS


def test_ad_spend_saved_summary():
    guardian = AdSpendGuardian()
    _PAUSED_ADSETS["adset_99"] = {
        "adset_name": "Ad Set 99",
        "sku": "SKU-99",
        "daily_budget": 150.0,
    }

    summary = guardian.get_ad_spend_saved_summary()
    assert summary["currently_paused_adsets_count"] == 1
    assert summary["daily_ad_spend_preserved_usd"] == 150.0
    assert summary["annual_projected_ad_spend_preserved_usd"] == 150.0 * 365.0


# ── 2. REST API Integration Tests ───────────────────────────────────────────


def test_api_sync_inventory_with_meta_ads(test_client):
    admin_user = User(
        username="admin",
        role=Role.ADMIN,
        permissions=["shopify:configure"],
    )
    with patch("ecommerce_ops.security.auth.get_current_user", return_value=admin_user), \
         patch.object(AdSpendGuardian, "sync_inventory_to_ads") as mock_sync:

        mock_sync.return_value = {
            "adsets_audited_count": 5,
            "adsets_paused": [{"adset_id": "ad_1", "daily_budget_usd": 85.0}],
            "daily_ad_spend_saved_usd": 85.0,
        }

        resp = test_client.post(
            "/api/v1/marketing/meta/sync-inventory",
            json={
                "items": [{"sku": "SKU-OOS-1", "inventory_quantity": 0, "title": "Bestseller Tee"}],
                "oos_threshold": 0,
                "auto_execute": True,
            },
            headers={"Authorization": "Bearer dummy_test_token"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["daily_ad_spend_saved_usd"] == 85.0


def test_api_get_ad_spend_saved_metrics(test_client):
    admin_user = User(
        username="admin",
        role=Role.ADMIN,
        permissions=["observability:view"],
    )
    with patch("ecommerce_ops.security.auth.get_current_user", return_value=admin_user), \
         patch.object(AdSpendGuardian, "get_ad_spend_saved_summary") as mock_summary:

        mock_summary.return_value = {
            "currently_paused_adsets_count": 2,
            "daily_ad_spend_preserved_usd": 175.0,
            "annual_projected_ad_spend_preserved_usd": 63875.0,
        }

        resp = test_client.get(
            "/api/v1/marketing/meta/saved-spend",
            headers={"Authorization": "Bearer dummy_test_token"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["daily_ad_spend_preserved_usd"] == 175.0


# ── 3. MCP Tool Dispatcher Integration Test ─────────────────────────────────


@pytest.mark.asyncio
async def test_mcp_execute_sync_meta_ad_spend():
    with patch("ecommerce_ops.marketing.ad_spend_guardian.AdSpendGuardian.sync_inventory_to_ads") as mock_sync:
        mock_sync.return_value = {
            "adsets_audited_count": 4,
            "adsets_paused": [{"adset_id": "ad_88", "daily_budget_usd": 120.0}],
            "daily_ad_spend_saved_usd": 120.0,
        }

        result = await execute_tool("opsiq_sync_meta_ad_spend", {"oos_threshold": 0})
        assert result["daily_ad_spend_saved_usd"] == 120.0
        assert len(result["adsets_paused"]) == 1
