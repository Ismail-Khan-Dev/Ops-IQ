"""Tests for Supervisor Graph and Reflection Agent."""

from unittest.mock import AsyncMock, patch

import pytest

from ecommerce_ops.agents.reflection import ReflectionAgent
from ecommerce_ops.graph.state import (
    AgentDecision,
    ExecutionPlan,
    ReflectionFeedback,
)

# ── State Model Tests ─────────────────────────────────────


def test_agent_decision_creation():
    d = AgentDecision(
        agent_id="fraud",
        action_type="HOLD_ORDER",
        reasoning="High risk order detected",
        action_data={"order_id": "o1", "risk_score": 85},
        requires_approval=True,
        confidence_score=0.92,
    )
    assert d.agent_id == "fraud"
    assert d.requires_approval is True
    assert d.confidence_score == 0.92


def test_execution_plan_creation():
    plan = ExecutionPlan(
        agents_to_run=["fraud", "inventory", "pricing"],
        rationale="dynamic",
    )
    assert len(plan.agents_to_run) == 3


def test_reflection_feedback_creation():
    fb = ReflectionFeedback(
        agent_id="fraud",
        decision_index=0,
        passed=True,
        issues=[],
        adjusted_confidence=None,
    )
    assert fb.passed is True


# ── Reflection Agent Tests ────────────────────────────────


@pytest.mark.asyncio
async def test_reflection_passes_valid_decision():
    agent = ReflectionAgent()
    decision = AgentDecision(
        agent_id="fraud",
        action_type="HOLD_ORDER",
        reasoning="Risk score 85/100. Factors: high_value_order.",
        action_data={},
        requires_approval=True,
        confidence_score=0.85,
    )
    feedback = await agent.run([decision])
    assert len(feedback) == 1
    assert feedback[0].passed is True


@pytest.mark.asyncio
async def test_reflection_flags_low_confidence():
    agent = ReflectionAgent()
    decision = AgentDecision(
        agent_id="fraud",
        action_type="HOLD_ORDER",
        reasoning="Uncertain detection with minimal supporting data available",
        action_data={},
        requires_approval=False,
        confidence_score=0.3,
    )
    feedback = await agent.run([decision])
    assert len(feedback) == 1
    assert feedback[0].passed is False
    assert any("low confidence" in issue.lower() for issue in feedback[0].issues)


@pytest.mark.asyncio
async def test_reflection_flags_high_confidence_hitl():
    agent = ReflectionAgent()
    decision = AgentDecision(
        agent_id="fraud",
        action_type="HOLD_ORDER",
        reasoning="Very confident fraud detection with strong evidence patterns",
        action_data={},
        requires_approval=True,
        confidence_score=0.99,
    )
    feedback = await agent.run([decision])
    assert any("high confidence" in issue.lower() for issue in feedback[0].issues)


@pytest.mark.asyncio
async def test_reflection_flags_empty_reasoning():
    agent = ReflectionAgent()
    decision = AgentDecision(
        agent_id="fraud",
        action_type="HOLD_ORDER",
        reasoning="short",
        action_data={},
        confidence_score=0.7,
    )
    feedback = await agent.run([decision])
    assert any("short" in issue.lower() for issue in feedback[0].issues)


@pytest.mark.asyncio
async def test_reflection_corrects_confidence():
    agent = ReflectionAgent()
    decision = AgentDecision(
        agent_id="fraud",
        action_type="HOLD_ORDER",
        reasoning="Low confidence detection without sufficient supporting data",
        action_data={},
        requires_approval=False,
        confidence_score=0.3,
    )
    feedback_list = await agent.run([decision])
    corrected = await agent.correct_decision(decision, feedback_list[0])
    assert corrected.confidence_score == 0.3
    assert corrected.requires_approval is True


@pytest.mark.asyncio
async def test_reflection_no_change_when_passed():
    agent = ReflectionAgent()
    decision = AgentDecision(
        agent_id="fraud",
        action_type="HOLD_ORDER",
        reasoning="Risk score 85/100. Factors: high_value, bulk_order, velocity.",
        action_data={},
        requires_approval=True,
        confidence_score=0.85,
    )
    feedback_list = await agent.run([decision])
    corrected = await agent.correct_decision(decision, feedback_list[0])
    assert corrected == decision


# ── Supervisor Graph Tests ────────────────────────────────


@pytest.mark.asyncio
async def test_planner_builds_plan_for_orders():
    from ecommerce_ops.graph.supervisor import planner

    state = {
        "active_orders": [{"id": "o1"}],
        "inventory_data": [{"sku": "X"}],
        "reviews_data": [{"id": "r1"}],
    }
    result = await planner(state)
    plan = result["execution_plan"]
    assert "fraud" in plan.agents_to_run
    assert "inventory" in plan.agents_to_run
    assert "pricing" in plan.agents_to_run
    assert "reviews" in plan.agents_to_run
    assert "marketing" in plan.agents_to_run


@pytest.mark.asyncio
async def test_planner_builds_plan_for_inventory_only():
    from ecommerce_ops.graph.supervisor import planner

    state = {"inventory_data": [{"sku": "X"}]}
    result = await planner(state)
    plan = result["execution_plan"]
    assert "inventory" in plan.agents_to_run
    assert "fraud" not in plan.agents_to_run
    assert "marketing" in plan.agents_to_run


@pytest.mark.asyncio
async def test_planner_default_plan_when_empty():
    from ecommerce_ops.graph.supervisor import planner

    state = {}
    result = await planner(state)
    plan = result["execution_plan"]
    assert plan.agents_to_run == ["fraud", "inventory", "pricing", "reviews", "marketing"]


@pytest.mark.asyncio
async def test_router_ends_at_reflection():
    from ecommerce_ops.graph.supervisor import router

    state = {
        "execution_plan": ExecutionPlan(agents_to_run=["fraud"], rationale="test"),
        "step_index": 1,
    }
    result = await router(state)
    assert result == "reflection"


@pytest.mark.asyncio
async def test_router_no_plan_ends():
    from ecommerce_ops.graph.supervisor import router

    state = {"execution_plan": None}
    result = await router(state)
    assert result == "__end__"


@pytest.mark.asyncio
async def test_run_agent_calls_factory():
    from ecommerce_ops.graph.supervisor import run_agent

    state = {"active_orders": [], "decisions": [], "errors": []}
    with patch("ecommerce_ops.graph.supervisor.agent_factory") as mock_factory:
        mock_agent = AsyncMock()
        mock_agent.run.return_value = state
        mock_factory.get_agent.return_value = mock_agent

        result = await run_agent("fraud", state)
        mock_factory.get_agent.assert_called_with("fraud")
        mock_agent.run.assert_called_once()


@pytest.mark.asyncio
async def test_run_agent_handles_failure():
    from ecommerce_ops.graph.supervisor import run_agent

    state = {"active_orders": [], "decisions": [], "errors": []}
    with patch("ecommerce_ops.graph.supervisor.agent_factory") as mock_factory:
        mock_factory.get_agent.side_effect = Exception("Agent init failed")

        result = await run_agent("fraud", state)
        assert len(result["errors"]) > 0
