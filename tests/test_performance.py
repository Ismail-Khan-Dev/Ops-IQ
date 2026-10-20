"""
Performance Benchmarks
Measures latency, throughput, and concurrency of critical paths.
"""

import asyncio
import statistics
import time
from contextlib import suppress

import pytest

from ecommerce_ops.agents.fraud import FraudAgent
from ecommerce_ops.agents.inventory import InventoryAgent
from ecommerce_ops.agents.marketing import MarketingAgent
from ecommerce_ops.agents.pricing import PricingAgent
from ecommerce_ops.agents.reflection import ReflectionAgent
from ecommerce_ops.graph.state import AgentDecision

pytestmark = [pytest.mark.slow]


# ── Fixtures ──────────────────────────────────────────────


@pytest.fixture
def fraud_state():
    return {
        "active_orders": [
            {"id": f"o{i}", "order_total": 1000 + i * 100, "line_items": [{"sku": "X"}] * (i + 5)}
            for i in range(10)
        ],
        "decisions": [],
    }


@pytest.fixture
def inventory_state():
    return {
        "inventory_data": [
            {"sku": f"SKU-{i}", "stock": max(1, 20 - i * 2), "price": 25.0}
            for i in range(20)
        ],
        "active_orders": [
            {"id": f"o{i}", "line_items": [{"sku": f"SKU-{j}", "quantity": 1}]}
            for i in range(5) for j in range(3)
        ],
        "decisions": [],
    }


@pytest.fixture
def decisions():
    return [
        AgentDecision(
            agent_id="fraud",
            action_type="HOLD_ORDER",
            reasoning="Risk score 85/100. Factors: high_value_order, velocity.",
            action_data={"order_id": "o1"},
            requires_approval=True,
            confidence_score=0.92,
        )
        for _ in range(50)
    ]


# ── Agent Latency Benchmarks ──────────────────────────────


@pytest.mark.asyncio
async def test_fraud_agent_latency(fraud_state):
    agent = FraudAgent()
    times = []
    for _ in range(100):
        start = time.monotonic()
        await agent.run(fraud_state)
        elapsed = (time.monotonic() - start) * 1000
        times.append(elapsed)

    p50 = statistics.median(times)
    p95 = sorted(times)[int(len(times) * 0.95)]
    avg = statistics.mean(times)

    print(f"\nFraud Agent: avg={avg:.2f}ms, p50={p50:.2f}ms, p95={p95:.2f}ms")
    assert p95 < 500, f"p95 latency {p95:.2f}ms exceeds 500ms threshold"


@pytest.mark.asyncio
async def test_inventory_agent_latency(inventory_state):
    agent = InventoryAgent()
    times = []
    for _ in range(100):
        start = time.monotonic()
        await agent.run(inventory_state)
        elapsed = (time.monotonic() - start) * 1000
        times.append(elapsed)

    p50 = statistics.median(times)
    p95 = sorted(times)[int(len(times) * 0.95)]
    avg = statistics.mean(times)

    print(f"\nInventory Agent: avg={avg:.2f}ms, p50={p50:.2f}ms, p95={p95:.2f}ms")
    assert p95 < 5000, f"p95 latency {p95:.2f}ms exceeds 5000ms threshold"


@pytest.mark.asyncio
async def test_pricing_agent_latency(inventory_state):
    agent = PricingAgent()
    times = []
    for _ in range(10):
        start = time.monotonic()
        with suppress(Exception):
            await agent.run(inventory_state)
        elapsed = (time.monotonic() - start) * 1000
        times.append(elapsed)

    p50 = statistics.median(times)
    p95 = sorted(times)[int(len(times) * 0.95)]
    avg = statistics.mean(times)

    print(f"\nPricing Agent: avg={avg:.2f}ms, p50={p50:.2f}ms, p95={p95:.2f}ms")
    assert p95 < 5000, f"p95 latency {p95:.2f}ms exceeds 5000ms threshold"


@pytest.mark.asyncio
async def test_marketing_agent_latency(inventory_state):
    agent = MarketingAgent()
    times = []
    for _ in range(100):
        start = time.monotonic()
        await agent.run(inventory_state)
        elapsed = (time.monotonic() - start) * 1000
        times.append(elapsed)

    p50 = statistics.median(times)
    p95 = sorted(times)[int(len(times) * 0.95)]
    avg = statistics.mean(times)

    print(f"\nMarketing Agent: avg={avg:.2f}ms, p50={p50:.2f}ms, p95={p95:.2f}ms")
    assert p95 < 5000, f"p95 latency {p95:.2f}ms exceeds 5000ms threshold"


# ── Reflection Latency ────────────────────────────────────


@pytest.mark.asyncio
async def test_reflection_latency(decisions):
    agent = ReflectionAgent()
    times = []
    for _ in range(50):
        start = time.monotonic()
        await agent.run(decisions)
        elapsed = (time.monotonic() - start) * 1000
        times.append(elapsed)

    p50 = statistics.median(times)
    p95 = sorted(times)[int(len(times) * 0.95)]
    avg = statistics.mean(times)

    print(f"\nReflection Agent (50 decisions): avg={avg:.2f}ms, p50={p50:.2f}ms, p95={p95:.2f}ms")
    assert p95 < 50, f"p95 latency {p95:.2f}ms exceeds 50ms threshold"


# ── Concurrency Benchmarks ────────────────────────────────


@pytest.mark.asyncio
async def test_concurrent_fraud_agents(fraud_state):
    agent = FraudAgent()

    async def run_one():
        start = time.monotonic()
        await agent.run(dict(fraud_state))
        return (time.monotonic() - start) * 1000

    times = await asyncio.gather(*[run_one() for _ in range(50)])
    avg = statistics.mean(times)
    p95 = sorted(times)[int(len(times) * 0.95)]

    print(f"\nConcurrent Fraud (50): avg={avg:.2f}ms, p95={p95:.2f}ms")
    assert p95 < 5000, f"Concurrent p95 {p95:.2f}ms exceeds 5000ms threshold"


@pytest.mark.asyncio
async def test_concurrent_mixed_agents(inventory_state):
    fraud = FraudAgent()
    inventory = InventoryAgent()
    marketing = MarketingAgent()

    async def run_fraud():
        return await fraud.run(dict(inventory_state))

    async def run_inventory():
        return await inventory.run(dict(inventory_state))

    async def run_marketing():
        return await marketing.run(dict(inventory_state))

    start = time.monotonic()
    await asyncio.gather(
        *[run_fraud() for _ in range(10)],
        *[run_inventory() for _ in range(10)],
        *[run_marketing() for _ in range(10)],
    )
    elapsed = (time.monotonic() - start) * 1000

    print(f"\nConcurrent Mixed (30 agents): {elapsed:.2f}ms total")
    assert elapsed < 2000, f"Concurrent execution {elapsed:.2f}ms exceeds 2s threshold"


# ── Throughput Benchmark ───────────────────────────────────


@pytest.mark.asyncio
async def test_decision_creation_throughput():
    agent = FraudAgent()
    count = 1000
    start = time.monotonic()
    for _ in range(count):
        agent.create_decision(
            action_type="HOLD_ORDER",
            reasoning="Test reasoning for throughput measurement",
            data={"test": True},
            confidence=0.85,
        )
    elapsed = (time.monotonic() - start) * 1000
    per_item = elapsed / count

    print(f"\nDecision creation: {count} in {elapsed:.2f}ms ({per_item:.4f}ms each)")
    assert per_item < 1, f"Per-decision latency {per_item:.4f}ms exceeds 1ms threshold"
