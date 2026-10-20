import os

import pytest

from ecommerce_ops.agents.marketing import MarketingAgent

os.environ["DEEPSEEK_API_KEY"] = "sk-dummy-key"


@pytest.fixture
def mock_state():
    return {
        "inventory_data": [
            {"sku": "HOT-SKU-1", "stock": 5, "price": 30.0},
            {"sku": "LOW-SKU-2", "stock": 50, "price": 10.0},
        ],
        "decisions": [],
    }


@pytest.mark.asyncio
async def test_marketing_agent_drafts_campaign_for_low_stock(mock_state):
    agent = MarketingAgent()
    updated_state = await agent.run(mock_state)

    decisions = updated_state["decisions"]
    assert len(decisions) == 1

    campaign = decisions[0]
    assert campaign.action_type == "DRAFT_MARKETING_CAMPAIGN"
    assert campaign.action_data["sku"] == "HOT-SKU-1"
    assert "Hurry" in campaign.action_data.get("draft_copy", "")
    assert campaign.requires_approval is True
    assert campaign.agent_id == "MarketingAgent"


@pytest.mark.asyncio
async def test_marketing_agent_skips_abundant_stock(mock_state):
    agent = MarketingAgent()
    updated_state = await agent.run(mock_state)

    decisions = updated_state["decisions"]
    skus_triggered = [d.action_data["sku"] for d in decisions]
    assert "LOW-SKU-2" not in skus_triggered


@pytest.mark.asyncio
async def test_marketing_agent_empty_inventory():
    agent = MarketingAgent()
    updated_state = await agent.run({"inventory_data": [], "decisions": []})
    assert len(updated_state["decisions"]) == 0
