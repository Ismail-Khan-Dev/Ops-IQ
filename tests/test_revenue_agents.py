"""Tests for the 3 new revenue agents: DynamicPricing, OrderSwaps, SmartReturns."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from ecommerce_ops.agents.factory import AgentFactory, UnifiedAgent


@pytest.fixture
def factory():
    return AgentFactory()


# ── Dynamic Pricing ───────────────────────────────────────


def test_factory_creates_dynamic_pricing(factory):
    agent = factory.get_agent("dynamic_pricing")
    assert isinstance(agent, UnifiedAgent)
    assert agent.name == "dynamic_pricing"


def test_dynamic_pricing_has_llm(factory):
    agent = factory.get_agent("dynamic_pricing")
    assert agent.llm_agent is not None
    assert agent.llm_method == "analyze"


def test_dynamic_pricing_adapt_input_empty():
    from ecommerce_ops.agents.dynamic_pricing_adapters import adapt_input

    assert adapt_input({"inventory_data": []}) is None


def test_dynamic_pricing_adapt_input_picks_lowest_margin():
    from ecommerce_ops.agents.dynamic_pricing_adapters import adapt_input

    items = [
        {"sku": "A", "price": 100, "unit_cost": 50, "stock": 10},
        {"sku": "B", "price": 100, "unit_cost": 90, "stock": 5},
    ]
    result = adapt_input({"inventory_data": items})
    assert result["sku"] == "B"


def test_dynamic_pricing_adapt_output_approve():
    from ecommerce_ops.agents.dynamic_pricing_adapters import adapt_output

    result = adapt_output({
        "recommended_price": 45.0,
        "change_percent": -10.0,
        "reasoning": "Competitor match",
        "confidence": 0.9,
    })
    assert result is not None
    assert result["action_type"] == "UPDATE_PRICE"
    assert result["data"]["new_price"] == 45.0


def test_dynamic_pricing_adapt_output_no_change():
    from ecommerce_ops.agents.dynamic_pricing_adapters import adapt_output

    assert adapt_output({"recommended_price": 0}) is None
    assert adapt_output({}) is None


def test_dynamic_pricing_adapt_output_injection():
    from ecommerce_ops.agents.dynamic_pricing_adapters import adapt_output
    from ecommerce_ops.safety.guardrails import GUARDRAIL_VIOLATION_KEY, guardrail_blocked

    blocked = guardrail_blocked(["ignore previous"])
    result = adapt_output(blocked)
    assert result is not None
    assert result["requires_approval"] is True
    assert result["confidence"] == 0.0
    assert GUARDRAIL_VIOLATION_KEY in result["data"]


@pytest.mark.asyncio
async def test_dynamic_pricing_rule_agent_run(factory):
    from ecommerce_ops.agents.dynamic_pricing.pricing import DynamicPricingAgent

    agent = DynamicPricingAgent()
    state = {
        "inventory_data": [
            {"sku": "TEST", "price": 100, "unit_cost": 30, "stock": 200, "daily_sales": 0.5}
        ],
        "decisions": [],
    }
    result = await agent.run(state)
    assert "decisions" in result


# ── Order Swaps ───────────────────────────────────────────


def test_factory_creates_order_swaps(factory):
    agent = factory.get_agent("order_swaps")
    assert isinstance(agent, UnifiedAgent)
    assert agent.name == "order_swaps"


def test_order_swaps_has_llm(factory):
    agent = factory.get_agent("order_swaps")
    assert agent.llm_agent is not None
    assert agent.llm_method == "analyze"


def test_order_swaps_adapt_input_empty():
    from ecommerce_ops.agents.order_swaps_adapters import adapt_input

    assert adapt_input({"out_of_stock_items": []}) is None


def test_order_swaps_adapt_input_selects_item_with_swaps():
    from ecommerce_ops.agents.order_swaps_adapters import adapt_input

    items = [
        {"original_sku": "A", "available_swaps": []},
        {"original_sku": "B", "available_swaps": [{"sku": "X"}]},
    ]
    result = adapt_input({"out_of_stock_items": items})
    assert result["original_sku"] == "B"


def test_order_swaps_adapt_output_should_swap():
    from ecommerce_ops.agents.order_swaps_adapters import adapt_output

    result = adapt_output({
        "should_swap": True,
        "original_sku": "A",
        "swap_sku": "X",
        "swap_name": "Substitute",
        "confidence": 0.8,
        "price_difference": 5.0,
        "reasoning": "Same category",
    })
    assert result is not None
    assert result["action_type"] == "SWAP_ITEM"
    assert result["requires_approval"] is True


def test_order_swaps_adapt_output_no_swap():
    from ecommerce_ops.agents.order_swaps_adapters import adapt_output

    assert adapt_output({"should_swap": False}) is None
    assert adapt_output({}) is None


def test_order_swaps_adapt_output_injection():
    from ecommerce_ops.agents.order_swaps_adapters import adapt_output
    from ecommerce_ops.safety.guardrails import guardrail_blocked

    result = adapt_output(guardrail_blocked(["injection"]))
    assert result is not None
    assert result["requires_approval"] is True


@pytest.mark.asyncio
async def test_order_swaps_rule_agent_run(factory):
    from ecommerce_ops.agents.order_swaps.swaps import OrderSwapsAgent

    agent = OrderSwapsAgent()
    state = {
        "out_of_stock_items": [
            {
                "order_id": "o1",
                "original_sku": "SHIRT-L",
                "original_name": "Shirt Large",
                "original_price": 50.0,
                "category": "apparel",
                "available_swaps": [
                    {"sku": "SHIRT-M", "name": "Shirt Medium", "price": 50.0, "stock": 10, "category": "apparel", "rating": 4.5},
                ],
            }
        ],
        "decisions": [],
    }
    result = await agent.run(state)
    assert "decisions" in result
    assert len(result["decisions"]) > 0


# ── Smart Returns ─────────────────────────────────────────


def test_factory_creates_smart_returns(factory):
    agent = factory.get_agent("smart_returns")
    assert isinstance(agent, UnifiedAgent)
    assert agent.name == "smart_returns"


def test_smart_returns_has_llm(factory):
    agent = factory.get_agent("smart_returns")
    assert agent.llm_agent is not None
    assert agent.llm_method == "analyze"


def test_smart_returns_adapt_input_empty():
    from ecommerce_ops.agents.smart_returns_adapters import adapt_input

    assert adapt_input({"pending_orders": []}) is None


def test_smart_returns_adapt_input_selects_order():
    from ecommerce_ops.agents.smart_returns_adapters import adapt_input

    orders = [{"order_id": "o1"}, {"order_id": "o2"}]
    result = adapt_input({"pending_orders": orders})
    assert result["order_id"] == "o1"


def test_smart_returns_adapt_output_high_risk():
    from ecommerce_ops.agents.smart_returns_adapters import adapt_output

    result = adapt_output({
        "return_risk": 0.8,
        "risk_level": "high",
        "reasoning": "High risk order",
        "confidence": 0.9,
        "preventive_actions": ["send_size_guide"],
        "recommended_insurance": True,
    })
    assert result is not None
    assert result["action_type"] == "FLAG_RETURN_RISK"
    assert result["requires_approval"] is True
    assert result["data"]["return_risk"] == 0.8


def test_smart_returns_adapt_output_low_risk():
    from ecommerce_ops.agents.smart_returns_adapters import adapt_output

    assert adapt_output({"return_risk": 0.1}) is None
    assert adapt_output({}) is None


def test_smart_returns_adapt_output_injection():
    from ecommerce_ops.agents.smart_returns_adapters import adapt_output
    from ecommerce_ops.safety.guardrails import guardrail_blocked

    result = adapt_output(guardrail_blocked(["prompt injection"]))
    assert result is not None
    assert result["requires_approval"] is True


@pytest.mark.asyncio
async def test_smart_returns_rule_agent_run(factory):
    from ecommerce_ops.agents.smart_returns.returns import SmartReturnsAgent

    agent = SmartReturnsAgent()
    state = {
        "pending_orders": [
            {
                "order_id": "o1",
                "order_total": 300,
                "categories": ["apparel"],
                "is_repeat_customer": False,
                "previous_returns": 3,
            }
        ],
        "decisions": [],
    }
    result = await agent.run(state)
    assert "decisions" in result
    assert len(result["decisions"]) > 0


# ── Registry Integration ──────────────────────────────────


def test_all_8_agents_registered(factory):
    agents = factory.list_agents()
    expected = {"fraud", "inventory", "pricing", "reviews", "marketing",
                "dynamic_pricing", "order_swaps", "smart_returns"}
    assert set(agents.keys()) == expected


def test_new_agents_have_slo_config(factory):
    agents = factory.list_agents()
    for name in ("dynamic_pricing", "order_swaps", "smart_returns"):
        assert "slo_p95_latency_ms" in agents[name]
        assert agents[name]["slo_p95_latency_ms"] > 0


def test_new_agents_state_keys(factory):
    agents = factory.list_agents()
    assert "inventory_data" in agents["dynamic_pricing"]["state_keys"]
    assert "out_of_stock_items" in agents["order_swaps"]["state_keys"]
    assert "pending_orders" in agents["smart_returns"]["state_keys"]
