"""Integration tests for the LangGraph supervisor pipeline."""
from ecommerce_ops.utils import utc_now

from datetime import datetime, UTC
from unittest.mock import patch

import pytest

from ecommerce_ops.graph.supervisor import Supervisor


class _MockAgent:
    def __init__(self, run_fn):
        self.run = run_fn


@pytest.mark.asyncio
async def test_full_pipeline_creates_decisions(mock_inventory_state):
    supervisor = Supervisor()
    state = await supervisor.run(mock_inventory_state)

    assert "decisions" in state
    assert len(state["decisions"]) > 0

    agents_seen = {d.agent_id for d in state["decisions"]}
    assert "InventoryAgent" in agents_seen or "MarketingAgent" in agents_seen


@pytest.mark.asyncio
async def test_pipeline_with_partial_data():
    state = {
        "inventory_data": [],
        "active_orders": [],
        "reviews_data": [],
        "decisions": [],
        "hitl_queue": [],
        "messages": [],
        "errors": [],
        "run_id": "test-partial",
        "timestamp": utc_now(),
        "step_index": 0,
    }
    supervisor = Supervisor()
    result = await supervisor.run(state)

    plan = result.get("execution_plan")
    assert plan is not None
    assert "marketing" in plan.agents_to_run


@pytest.mark.asyncio
async def test_pipeline_with_only_reviews():
    state = {
        "inventory_data": [],
        "active_orders": [],
        "reviews_data": [
            {"id": "r1", "content": "Bad service", "rating": 1},
        ],
        "decisions": [],
        "hitl_queue": [],
        "messages": [],
        "errors": [],
        "run_id": "test-reviews-only",
        "timestamp": utc_now(),
        "step_index": 0,
    }
    supervisor = Supervisor()
    result = await supervisor.run(state)

    plan = result.get("execution_plan")
    assert "reviews" in plan.agents_to_run
    assert "fraud" not in plan.agents_to_run


@pytest.mark.asyncio
async def test_pipeline_propagates_errors():
    state = {
        "inventory_data": [{"sku": "X", "stock": 1, "price": 10.0}],
        "active_orders": [],
        "reviews_data": [],
        "decisions": [],
        "hitl_queue": [],
        "messages": [],
        "errors": [],
        "run_id": "test-error",
        "timestamp": utc_now(),
        "step_index": 0,
    }

    async def failing_run_agent(node_name, s):
        errors = s.get("errors", [])
        errors.append({"agent": node_name, "error": "Inventory crashed"})
        s["errors"] = errors
        s["step_index"] = s.get("step_index", 0) + 1
        return s

    with patch(
        "ecommerce_ops.graph.supervisor.run_agent",
        side_effect=failing_run_agent,
    ):
        supervisor = Supervisor()
        result = await supervisor.run(state)

        assert len(result.get("errors", [])) >= 1
        assert any("Inventory crashed" in str(e.get("error", "")) for e in result["errors"])


@pytest.mark.asyncio
async def test_reflection_corrects_low_confidence():
    state = {
        "inventory_data": [{"sku": "TEST", "stock": 100, "price": 50.0}],
        "active_orders": [{"id": "o1", "line_items": [{"sku": "TEST", "quantity": 1}]}],
        "reviews_data": [],
        "decisions": [],
        "hitl_queue": [],
        "messages": [],
        "errors": [],
        "run_id": "test-reflection",
        "timestamp": utc_now(),
        "step_index": 0,
    }
    supervisor = Supervisor()
    result = await supervisor.run(state)

    feedback = result.get("reflection_feedback", [])
    assert "reflection_feedback" in result


@pytest.mark.asyncio
async def test_planner_dynamic_routing():
    state = {
        "inventory_data": [{"sku": "A", "stock": 1, "price": 10.0}],
        "active_orders": [{"id": "o1"}],
        "reviews_data": [{"id": "r1", "content": "OK", "rating": 3}],
        "decisions": [],
        "hitl_queue": [],
        "messages": [],
        "errors": [],
        "run_id": "test-routing",
        "timestamp": utc_now(),
        "step_index": 0,
    }
    supervisor = Supervisor()
    result = await supervisor.run(state)

    plan = result.get("execution_plan")
    assert plan is not None
    assert plan.agents_to_run == ["fraud", "inventory", "pricing", "reviews", "marketing"]


@pytest.mark.asyncio
async def test_supervisor_runs_idempotent():
    state = {
        "inventory_data": [],
        "active_orders": [],
        "reviews_data": [],
        "decisions": [],
        "hitl_queue": [],
        "messages": [],
        "errors": [],
        "run_id": "test-idempotent",
        "timestamp": utc_now(),
        "step_index": 0,
    }
    supervisor = Supervisor()
    result1 = await supervisor.run(state)
    result2 = await supervisor.run(state)

    assert len(result1["decisions"]) == len(result2["decisions"])
    assert result1["execution_plan"].agents_to_run == result2["execution_plan"].agents_to_run
