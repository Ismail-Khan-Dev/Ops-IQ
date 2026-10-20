"""
Tests for Phase 1 Implementation:
- Dynamic LangGraph Supervisor (10 domain agents)
- Multi-Worker Redis SSO State & Session Lifecycle
- Enhanced Decision Types & Allowlist Mapping
- Safety Rules for Swaps, Returns, Cart Recovery, Support
- Competitor Price Scraper Caching
"""

import os
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from ecommerce_ops.agents.registry import agent_registry
from ecommerce_ops.graph.state import ExecutionPlan
from ecommerce_ops.graph.supervisor import Supervisor, _entry_router, _get_registered_agents, planner, router
from ecommerce_ops.models.db import StoreSettings
from ecommerce_ops.pipeline.builder import build_payload_and_evidence
from ecommerce_ops.pipeline.runner import ACTION_TYPE_AGENT_ALLOWLIST, DECISION_TYPE_MAP
from ecommerce_ops.safety.safety_rules import evaluate_action_safety
from ecommerce_ops.security.sso import SSOManager, SSOSession


# ── 1. Dynamic Supervisor Tests ──────────────────────────────────────────


def test_registered_agents_includes_all_ten_domains():
    agent_registry.scan()
    registered = _get_registered_agents()
    expected_agents = [
        "fraud",
        "inventory",
        "pricing",
        "dynamic_pricing",
        "order_swaps",
        "smart_returns",
        "reviews",
        "marketing",
        "cart_recovery",
        "customer_support",
    ]
    for agent in expected_agents:
        assert agent in registered, f"Expected {agent} to be registered in supervisor"


@pytest.mark.asyncio
async def test_planner_includes_order_swaps_and_returns():
    state = {
        "active_orders": [{"id": "ord_101"}],
        "out_of_stock_items": [{"original_sku": "SKU-OUT"}],
        "pending_orders": [{"order_id": "ord_102"}],
        "inventory_data": [{"sku": "SKU-A"}],
        "reviews_data": [],
        "abandoned_carts": [{"id": "cart_1"}],
        "support_tickets": [{"id": "ticket_1"}],
    }
    result = await planner(state)
    plan = result["execution_plan"]
    assert "fraud" in plan.agents_to_run
    assert "order_swaps" in plan.agents_to_run
    assert "smart_returns" in plan.agents_to_run
    assert "inventory" in plan.agents_to_run
    assert "pricing" in plan.agents_to_run
    assert "cart_recovery" in plan.agents_to_run
    assert "customer_support" in plan.agents_to_run
    assert "marketing" in plan.agents_to_run


def test_entry_router_selects_first_planned_agent():
    state = {
        "execution_plan": ExecutionPlan(
            agents_to_run=["cart_recovery", "marketing"],
            rationale="test",
        )
    }
    target = _entry_router(state)
    assert target == "cart_recovery"


@pytest.mark.asyncio
async def test_router_routes_through_extended_agents():
    state = {
        "execution_plan": ExecutionPlan(
            agents_to_run=["order_swaps", "smart_returns", "marketing"],
            rationale="test",
        ),
        "step_index": 1,
    }
    next_node = await router(state)
    assert next_node == "smart_returns"


# ── 2. Redis SSO State & Session Tests ────────────────────────────────────


@pytest.mark.asyncio
async def test_sso_manager_async_redis_state_validation():
    mock_redis = AsyncMock()
    mock_redis.getdel.return_value = b"google"

    mgr = SSOManager(redis_client=mock_redis)
    provider = await mgr.validate_state_async("test_oauth_state")

    assert provider == "google"
    mock_redis.getdel.assert_awaited_once_with("sso:state:test_oauth_state")


@pytest.mark.asyncio
async def test_sso_manager_async_session_storage():
    mock_redis = AsyncMock()
    mock_redis.get.return_value = (
        b'{"provider": "google", "user_email": "ops@brand.com", "user_name": "Ops Lead", "role": "operator", "expires_at": 1799999999}'
    )

    mgr = SSOManager(redis_client=mock_redis)
    session = await mgr.get_session_async("test_token")

    assert session is not None
    assert session.user_email == "ops@brand.com"
    assert session.role == "operator"


# ── 3. Decision Type & Allowlist Mapping Tests ────────────────────────────


def test_new_action_types_mapped():
    assert DECISION_TYPE_MAP["SWAP_ITEM"] == "order_swap"
    assert DECISION_TYPE_MAP["FLAG_RETURN_RISK"] == "return_risk_flag"
    assert DECISION_TYPE_MAP["recover_cart"] == "cart_recovery"
    assert DECISION_TYPE_MAP["respond_to_ticket"] == "support_response"


def test_new_agent_capabilities_authorized():
    assert "OrderSwapsAgent" in ACTION_TYPE_AGENT_ALLOWLIST["order_swap"]
    assert "SmartReturnsAgent" in ACTION_TYPE_AGENT_ALLOWLIST["return_risk_flag"]
    assert "AbandonedCartAgent" in ACTION_TYPE_AGENT_ALLOWLIST["cart_recovery"]
    assert "CustomerSupportAgent" in ACTION_TYPE_AGENT_ALLOWLIST["support_response"]


# ── 4. Safety Rules Tests ─────────────────────────────────────────────────


def test_order_swap_safety_rules():
    settings = StoreSettings(shadow_mode=False, po_limit=1000.0, pricing_limit=5.0)

    # Moderate price difference ($10) -> Low risk
    hitl, risk, impact = evaluate_action_safety(
        "OrderSwapsAgent",
        "order_swap",
        {"price_difference": 10.0},
        confidence=0.85,
        settings=settings,
    )
    assert hitl is False
    assert risk == "low"
    assert impact == -10.0

    # High price difference ($45) -> Elevated risk
    hitl, risk, impact = evaluate_action_safety(
        "OrderSwapsAgent",
        "order_swap",
        {"price_difference": 45.0},
        confidence=0.85,
        settings=settings,
    )
    assert hitl is True
    assert risk == "medium"


def test_smart_returns_safety_rules():
    settings = StoreSettings(shadow_mode=False, po_limit=1000.0, pricing_limit=5.0)
    hitl, risk, _ = evaluate_action_safety(
        "SmartReturnsAgent",
        "return_risk_flag",
        {"return_risk": 0.85},
        confidence=0.90,
        settings=settings,
    )
    assert hitl is True
    assert risk == "high"


# ── 5. Payload Builder Tests ──────────────────────────────────────────────


def test_build_payload_order_swaps():
    decision = MagicMock(
        agent_id="OrderSwapsAgent",
        reasoning="Swap suggested for stockout",
        action_data={
            "order_id": "ORD-555",
            "original_sku": "TSHIRT-S",
            "swap_sku": "TSHIRT-M",
            "swap_price": 28.0,
            "price_difference": 3.0,
        },
    )
    payload, evidence = build_payload_and_evidence(decision, reviews_data=[])
    assert payload["order_id"] == "ORD-555"
    assert payload["swap_sku"] == "TSHIRT-M"
    assert payload["price_difference"] == 3.0
    assert any(e["label"] == "Swap SKU" for e in evidence)


# ── 6. Competitor Scraper Caching Test ────────────────────────────────────


@pytest.mark.asyncio
async def test_competitor_scraper_cache_hit():
    with patch("ecommerce_ops.memory.cache.cache.get", new_callable=AsyncMock) as mock_get:
        mock_get.return_value = 24.99
        from ecommerce_ops.connectors.competitor_scraper import scrape_competitor_price

        price = await scrape_competitor_price("TEST-SKU-123")
        assert price == 24.99
        mock_get.assert_awaited_once_with("competitor_price:TEST-SKU-123")
