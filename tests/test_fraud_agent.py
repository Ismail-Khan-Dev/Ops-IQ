import os

import pytest

from ecommerce_ops.agents.fraud import FraudAgent

os.environ["DEEPSEEK_API_KEY"] = "sk-dummy-key"

@pytest.fixture
def mock_state():
    return {
        "active_orders": [
            {
                "id": "o1",
                "customer": {"email": "test@example.com"},
            },
            {
                "id": "o_suspicious",
                "customer": {"email": "suspicious@example.com"},
            }
        ],
        "decisions": [],
    }

@pytest.mark.asyncio
async def test_fraud_agent_detects_risk(mock_state):
    agent = FraudAgent()
    updated_state = await agent.run(mock_state)

    decisions = updated_state["decisions"]
    assert len(decisions) == 1

    fraud_decision = decisions[0]
    assert fraud_decision.action_data["order_id"] == "o_suspicious"
    assert "ip_shipping_mismatch" in fraud_decision.action_data["risk_factors"]
    assert fraud_decision.action_data["risk_score"] == 85
    assert fraud_decision.requires_approval is True

