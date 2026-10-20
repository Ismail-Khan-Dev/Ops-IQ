"""Tests for cart_recovery API routes."""
import os

import pytest
from httpx import ASGITransport, AsyncClient

os.environ.setdefault("ENV", "testing")
os.environ.setdefault("API_KEY", "opsiq-dev-key-2024")
os.environ.setdefault("DATABASE_URL", "sqlite+aiosqlite://")
os.environ.setdefault("DEEPSEEK_API_KEY", "sk-test-key")

from ecommerce_ops.api.app import app

AUTH = {"Authorization": "Bearer opsiq-dev-key-2024"}


@pytest.fixture
def client():
    transport = ASGITransport(app=app)
    return AsyncClient(transport=transport, base_url="http://test", headers=AUTH)


@pytest.mark.asyncio
async def test_analyze_cart(client):
    resp = await client.post(
        "/cart-recovery/analyze",
        json={"cart_id": "c1", "total_value": 99.99, "items": [{"product_id": 1, "variant_id": 1, "title": "Shirt", "price": 99.99}]},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["cart_id"] == "c1"
    assert "recommendation" in body
    assert "strategy" in body["recommendation"]
    assert "recovery_probability" in body["recommendation"]


@pytest.mark.asyncio
async def test_analyze_cart_with_discount(client):
    resp = await client.post(
        "/cart-recovery/analyze",
        json={"cart_id": "c2", "total_value": 250.0, "items": [{"product_id": 2, "variant_id": 2, "title": "Shoes", "price": 250.0}]},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["cart_id"] == "c2"
    assert "email_context" in body


@pytest.mark.asyncio
async def test_analyze_carts_batch(client):
    resp = await client.post(
        "/cart-recovery/analyze/batch",
        json=[
            {"cart_id": "b1", "total_value": 50.0, "items": []},
            {"cart_id": "b2", "total_value": 150.0, "items": []},
        ],
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["analyzed"] == 2
    assert "total_value" in body
    assert "total_potential_revenue" in body
    assert len(body["results"]) == 2


@pytest.mark.asyncio
async def test_trigger_recovery(client):
    resp = await client.post(
        "/cart-recovery/recover",
        json={"cart_id": "c3", "strategy": "discount_percent", "discount_value": 10.0},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "recovery_initiated"
    assert body["cart_id"] == "c3"
    assert "discount_code" in body


@pytest.mark.asyncio
async def test_trigger_batch_recovery(client):
    resp = await client.post(
        "/cart-recovery/recover/batch",
        json={"cart_ids": ["b1", "b2", "b3"], "min_value": 5.0},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "batch_recovery_initiated"
    assert body["count"] == 3
    assert len(body["results"]) == 3
    for r in body["results"]:
        assert r["status"] == "initiated"
        assert "discount_code" in r


@pytest.mark.asyncio
async def test_get_cart_analytics(client):
    resp = await client.get("/cart-recovery/analytics?days=14")
    assert resp.status_code == 200
    body = resp.json()
    assert "total_abandoned" in body
    assert "total_recovered" in body
    assert "recovery_rate" in body
    assert "strategy_breakdown" in body
    assert "risk_distribution" in body


@pytest.mark.asyncio
async def test_get_strategy_analytics(client):
    resp = await client.get("/cart-recovery/analytics/strategies")
    assert resp.status_code == 200
    body = resp.json()
    assert "strategies" in body
    assert len(body["strategies"]) >= 3
    assert "best_practices" in body


@pytest.mark.asyncio
async def test_cart_recovery_health(client):
    resp = await client.get("/cart-recovery/health")
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "healthy"
    assert body["agent"] == "AbandonedCartAgent"
    assert "timestamp" in body


@pytest.mark.asyncio
async def test_analyze_cart_empty_items(client):
    resp = await client.post(
        "/cart-recovery/analyze",
        json={"cart_id": "c_empty", "total_value": 0.0, "items": []},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["cart_id"] == "c_empty"
    assert "recommendation" in body


@pytest.mark.asyncio
async def test_batch_recovery_empty_list(client):
    resp = await client.post(
        "/cart-recovery/recover/batch",
        json={"cart_ids": [], "min_value": 0.0},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["count"] == 0
    assert body["results"] == []
