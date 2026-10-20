import json
import os
from unittest.mock import patch

import pytest

from ecommerce_ops.agents.inventory import InventoryAgent

# Mock settings for testing
os.environ["DEEPSEEK_API_KEY"] = "sk-dummy-key"

@pytest.fixture
def mock_state():
    with open("tests/fixtures/shopify_data.json") as f:
        data = json.load(f)

    return {
        "inventory_data": data["inventory"],
        "active_orders": data["orders"],
        "decisions": [],
        "hitl_queue": [],
        "messages": [],
        "errors": []
    }

@pytest.mark.asyncio
async def test_inventory_agent_drafts_po(mock_state):
    # Make sure at least one SKU triggers a PO by lowering stock
    mock_state["inventory_data"][0]["stock"] = 1

    # Initialize agent
    agent = InventoryAgent()

    # Run agent
    updated_state = await agent.run(mock_state)

    # Assertions
    decisions = updated_state["decisions"]
    assert len(decisions) >= 1

    # Check if TSHIRT-BLUE-L triggered a PO (calculated velocity in mock is 5/30 = 0.16)
    # Wait, in the mock logic if orders exist it calculates.
    # Let's check TSHIRT-BLUE-L specifically. Stock=10, 30-day sales=5 -> Velocity=0.166 -> days_left=60.
    # MUG-WHITE: Stock=5, 30-day sales=1 -> Velocity=0.033 -> days_left=150.

    # Actually, my mock _calculate_velocity returns 2.5 if orders are empty.
    # If I provide orders, it should use them.
    # Let's adjust the test to ensure a PO is drafted by manually setting velocity or stock.

    # Test case: Low stock for MUG-WHITE (Stock=5, but let's say velocity is 1/day)
    with patch.object(InventoryAgent, '_calculate_velocity', return_value=1.5):
        updated_state = await agent.run(mock_state)
        po_decisions = [d for d in updated_state["decisions"] if d.action_type == "DRAFT_PO"]
        assert len(po_decisions) > 0
        assert po_decisions[0].agent_id == "InventoryAgent"
        assert "stockout" in po_decisions[0].reasoning.lower()


