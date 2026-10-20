import os
from unittest.mock import AsyncMock, patch

import pytest

from ecommerce_ops.agents.reviews import ReviewsAgent

os.environ["DEEPSEEK_API_KEY"] = "sk-dummy-key"

@pytest.fixture
def mock_state():
    return {
        "reviews_data": [
            {"id": "r1", "content": "This shirt shrank after one wash and the color faded. Very disappointed.", "rating": 2},
        ],
        "decisions": [],
    }

@pytest.mark.asyncio
async def test_reviews_agent_llm_analysis(mock_state):
    agent = ReviewsAgent()

    mock_llm_output = {
        "sentiment": "Negative",
        "themes": ["Quality", "Washing"],
        "response": "We are so sorry to hear the shirt shrank and faded. We'd love to offer a replacement or refund.",
        "contains_refund_offer": True,
        "confidence": 0.95
    }

    with patch.object(agent, "_analyze_review", new_callable=AsyncMock) as mock_analyze:
        mock_analyze.return_value = mock_llm_output

        updated_state = await agent.run(mock_state)
        decisions = updated_state["decisions"]

        assert len(decisions) == 1
        decision = decisions[0]

        assert decision.action_type == "POST_REVIEW_RESPONSE"
        assert decision.action_data["sentiment"] == "Negative"
        assert decision.action_data["response_content"].startswith("We are so sorry")
        assert decision.requires_approval is True

