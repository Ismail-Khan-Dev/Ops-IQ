import json
import os
from unittest.mock import AsyncMock, patch

import pytest

from ecommerce_ops.agents.pricing import PricingAgent
from ecommerce_ops.tools.registry import ToolRegistry

os.environ["DEEPSEEK_API_KEY"] = "sk-dummy-key"

@pytest.fixture
def mock_state():
    with open("tests/fixtures/shopify_data.json") as f:
        data = json.load(f)

    return {
        "inventory_data": data["inventory"],
        "decisions": [],
    }

@pytest.mark.asyncio
async def test_pricing_agent_scrapes_and_adjusts(mock_state):
    with patch.object(ToolRegistry, "run_tool", new_callable=AsyncMock) as mock_run_tool, \
         patch("ecommerce_ops.agents.pricing.cache.get", new_callable=AsyncMock) as mock_cache_get, \
         patch("ecommerce_ops.agents.pricing.cache.set", new_callable=AsyncMock) as mock_cache_set:

        mock_cache_get.return_value = None
        mock_run_tool.return_value = 21.00

        agent = PricingAgent()
        updated_state = await agent.run(mock_state)

        decisions = updated_state["decisions"]

        pricing_decisions = [d for d in decisions if d.action_type == "UPDATE_PRICE"]
        assert len(pricing_decisions) >= 1

        blue_tshirt_decision = next((d for d in pricing_decisions if d.action_data["sku"] == "TSHIRT-BLUE-L"), None)
        assert blue_tshirt_decision is not None
        assert blue_tshirt_decision.action_data["new_price"] == 21.00

        assert mock_run_tool.called
        mock_cache_set.assert_called()
