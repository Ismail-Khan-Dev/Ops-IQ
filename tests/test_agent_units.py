import os

os.environ["ENV"] = "testing"
os.environ["DATABASE_URL"] = "sqlite+aiosqlite://"
os.environ["API_KEY"] = "test-key"
os.environ["DEEPSEEK_API_KEY"] = "sk-test-key"

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from ecommerce_ops.graph.state import AgentDecision, ReflectionFeedback


class TestBaseAgent:
    def test_init_with_deepseek_key(self):
        from ecommerce_ops.agents._base import BaseAgent
        class TestAgent(BaseAgent):
            async def run(self, state): return state
        with patch("ecommerce_ops.agents._base.settings") as mock_settings:
            mock_settings.GOOGLE_API_KEY = None
            mock_settings.DEEPSEEK_API_KEY = MagicMock(get_secret_value=MagicMock(return_value="sk-test"))
            mock_settings.LLM_MODEL = "test-model"
            mock_settings.DEEPSEEK_BASE_URL = "https://api.test.com"
            mock_settings.ENV = "testing"
            agent = TestAgent("TestAgent")
            assert agent.agent_name == "TestAgent"

    def test_init_with_google_key(self):
        from ecommerce_ops.agents._base import BaseAgent
        class TestAgent(BaseAgent):
            async def run(self, state): return state
        with patch("ecommerce_ops.agents._base.settings") as mock_settings:
            mock_settings.GOOGLE_API_KEY = MagicMock(get_secret_value=MagicMock(return_value="google-key"))
            mock_settings.DEEPSEEK_API_KEY = None
            agent = TestAgent("TestAgent")
            assert agent.agent_name == "TestAgent"

    def test_init_no_key_non_production(self):
        from ecommerce_ops.agents._base import BaseAgent
        class TestAgent(BaseAgent):
            async def run(self, state): return state
        with patch("ecommerce_ops.agents._base.settings") as mock_settings:
            mock_settings.GOOGLE_API_KEY = None
            mock_settings.DEEPSEEK_API_KEY = None
            mock_settings.ENV = "testing"
            mock_settings.LLM_MODEL = "test-model"
            agent = TestAgent("TestAgent")
            assert agent.agent_name == "TestAgent"

    def test_init_no_key_production_raises(self):
        from ecommerce_ops.agents._base import BaseAgent
        class TestAgent(BaseAgent):
            async def run(self, state): return state
        with patch("ecommerce_ops.agents._base.settings") as mock_settings:
            mock_settings.GOOGLE_API_KEY = None
            mock_settings.DEEPSEEK_API_KEY = None
            mock_settings.ENV = "production"
            with pytest.raises(RuntimeError, match="No LLM API key configured"):
                TestAgent("TestAgent")

    def test_create_decision(self):
        from ecommerce_ops.agents._base import BaseAgent
        class TestAgent(BaseAgent):
            async def run(self, state): return state
        with patch("ecommerce_ops.agents._base.settings") as mock_settings:
            mock_settings.GOOGLE_API_KEY = None
            mock_settings.DEEPSEEK_API_KEY = MagicMock(get_secret_value=MagicMock(return_value="sk-test"))
            mock_settings.LLM_MODEL = "test-model"
            mock_settings.DEEPSEEK_BASE_URL = ""
            agent = TestAgent("TestAgent")
            decision = agent.create_decision(
                action_type="HOLD_ORDER",
                reasoning="This is a valid reasoning string.",
                data={"order_id": "123"},
                confidence=0.85,
                requires_approval=True,
            )
            assert decision.action_type == "HOLD_ORDER"
            assert decision.confidence_score == 0.85
            assert decision.requires_approval is True

    @pytest.mark.asyncio
    async def test_run_not_implemented(self):
        from ecommerce_ops.agents._base import BaseAgent
        class MinimalAgent(BaseAgent):
            pass
        with patch("ecommerce_ops.agents._base.settings") as mock_settings:
            mock_settings.GOOGLE_API_KEY = None
            mock_settings.DEEPSEEK_API_KEY = MagicMock(get_secret_value=MagicMock(return_value="sk-test"))
            mock_settings.LLM_MODEL = "test-model"
            mock_settings.DEEPSEEK_BASE_URL = ""
            agent = MinimalAgent("TestAgent")
            with pytest.raises(NotImplementedError):
                await agent.run({})

    @pytest.mark.asyncio
    async def test_testing_env_never_constructs_real_provider(self):
        from ecommerce_ops.agents._base import BaseAgent, _DisabledLLM
        from ecommerce_ops.config import Environment

        class TestAgent(BaseAgent):
            async def run(self, state): return state

        with patch("ecommerce_ops.agents._base.settings") as mock_settings:
            mock_settings.GOOGLE_API_KEY = MagicMock(get_secret_value=MagicMock(return_value="google-key"))
            mock_settings.DEEPSEEK_API_KEY = MagicMock(get_secret_value=MagicMock(return_value="sk-test"))
            mock_settings.ENV = Environment.TESTING
            mock_settings.LLM_MODEL = "test-model"
            agent = TestAgent("TestAgent")
            assert isinstance(agent.llm, _DisabledLLM)
            assert agent.llm.with_structured_output("x") is agent.llm
            with pytest.raises(RuntimeError, match="hermetic guard"):
                await agent.llm.ainvoke([])

    @pytest.mark.asyncio
    async def test_load_memory_context(self):
        from ecommerce_ops.agents._base import BaseAgent
        class TestAgent(BaseAgent):
            async def run(self, state): return state
        with patch("ecommerce_ops.agents._base.settings") as mock_settings:
            mock_settings.GOOGLE_API_KEY = None
            mock_settings.DEEPSEEK_API_KEY = MagicMock(get_secret_value=MagicMock(return_value="sk-test"))
            mock_settings.LLM_MODEL = "test-model"
            mock_settings.DEEPSEEK_BASE_URL = ""
            agent = TestAgent("TestAgent")

        with patch("ecommerce_ops.agents._base.get_recent_memories", new_callable=AsyncMock) as mock_recent:
            mock_recent.return_value = [
                {"action_type": "HOLD_ORDER", "confidence": 0.8, "requires_approval": True, "reasoning": "test"},
            ]
            with patch("ecommerce_ops.agents._base.get_pattern_insight", new_callable=AsyncMock) as mock_insight:
                mock_insight.return_value = "Pattern detected"
                result = await agent.load_memory_context({})
                assert "Recent decisions" in result
                assert "Pattern insight" in result

    @pytest.mark.asyncio
    async def test_load_memory_context_empty(self):
        from ecommerce_ops.agents._base import BaseAgent
        class TestAgent(BaseAgent):
            async def run(self, state): return state
        with patch("ecommerce_ops.agents._base.settings") as mock_settings:
            mock_settings.GOOGLE_API_KEY = None
            mock_settings.DEEPSEEK_API_KEY = MagicMock(get_secret_value=MagicMock(return_value="sk-test"))
            mock_settings.LLM_MODEL = "test-model"
            mock_settings.DEEPSEEK_BASE_URL = ""
            agent = TestAgent("TestAgent")
        with patch("ecommerce_ops.agents._base.get_recent_memories", new_callable=AsyncMock, return_value=[]), patch(
            "ecommerce_ops.agents._base.get_pattern_insight", new_callable=AsyncMock, return_value=None
        ), patch("ecommerce_ops.agents._base.memory_retrieval") as mock_mr:
            mock_mr.get_context_window = AsyncMock(return_value="")
            result = await agent.load_memory_context({})
            assert result == ""

    @pytest.mark.asyncio
    async def test_load_memory_context_includes_vector_context(self):
        from ecommerce_ops.agents._base import BaseAgent
        class TestAgent(BaseAgent):
            async def run(self, state): return state
        with patch("ecommerce_ops.agents._base.settings") as mock_settings:
            mock_settings.GOOGLE_API_KEY = None
            mock_settings.DEEPSEEK_API_KEY = MagicMock(get_secret_value=MagicMock(return_value="sk-test"))
            mock_settings.LLM_MODEL = "test-model"
            mock_settings.DEEPSEEK_BASE_URL = ""
            agent = TestAgent("TestAgent")
        with patch("ecommerce_ops.agents._base.get_recent_memories", new_callable=AsyncMock, return_value=[]), patch(
            "ecommerce_ops.agents._base.get_pattern_insight", new_callable=AsyncMock, return_value=None
        ), patch("ecommerce_ops.agents._base.memory_retrieval") as mock_mr:
            mock_mr.get_context_window = AsyncMock(return_value="[episodic] fraud pattern on repeat orders")
            result = await agent.load_memory_context({})
            assert "Relevant knowledge" in result
            assert "fraud pattern" in result

    @pytest.mark.asyncio
    async def test_load_vector_context_fail_open(self):
        from ecommerce_ops.agents._base import BaseAgent
        class TestAgent(BaseAgent):
            async def run(self, state): return state
        with patch("ecommerce_ops.agents._base.settings") as mock_settings:
            mock_settings.GOOGLE_API_KEY = None
            mock_settings.DEEPSEEK_API_KEY = MagicMock(get_secret_value=MagicMock(return_value="sk-test"))
            mock_settings.LLM_MODEL = "test-model"
            mock_settings.DEEPSEEK_BASE_URL = ""
            agent = TestAgent("TestAgent")
        with patch("ecommerce_ops.agents._base.memory_retrieval") as mock_mr:
            mock_mr.get_context_window = AsyncMock(side_effect=RuntimeError("db down"))
            result = await agent._load_vector_context({})
            assert result == ""

    @pytest.mark.asyncio
    async def test_persist_decision(self):
        from ecommerce_ops.agents._base import BaseAgent
        class TestAgent(BaseAgent):
            async def run(self, state): return state
        with patch("ecommerce_ops.agents._base.settings") as mock_settings:
            mock_settings.GOOGLE_API_KEY = None
            mock_settings.DEEPSEEK_API_KEY = MagicMock(get_secret_value=MagicMock(return_value="sk-test"))
            mock_settings.LLM_MODEL = "test-model"
            mock_settings.DEEPSEEK_BASE_URL = ""
            agent = TestAgent("TestAgent")
        decision = AgentDecision(
            agent_id="TestAgent", action_type="TEST",
            reasoning="Test reasoning", confidence_score=0.8,
        )
        with patch("ecommerce_ops.agents._base.store_decision_memory", new_callable=AsyncMock) as mock_store, patch(
            "ecommerce_ops.agents._base.agent_memory_manager"
        ) as mock_mgr:
            mock_mgr.store_decision = AsyncMock()
            await agent.persist_decision(decision)
            mock_store.assert_called_once()
            mock_mgr.store_decision.assert_called_once()

    @pytest.mark.asyncio
    async def test_persist_decision_durable_fail_open(self):
        from ecommerce_ops.agents._base import BaseAgent
        class TestAgent(BaseAgent):
            async def run(self, state): return state
        with patch("ecommerce_ops.agents._base.settings") as mock_settings:
            mock_settings.GOOGLE_API_KEY = None
            mock_settings.DEEPSEEK_API_KEY = MagicMock(get_secret_value=MagicMock(return_value="sk-test"))
            mock_settings.LLM_MODEL = "test-model"
            mock_settings.DEEPSEEK_BASE_URL = ""
            agent = TestAgent("TestAgent")
        decision = AgentDecision(
            agent_id="TestAgent", action_type="TEST",
            reasoning="Test reasoning", confidence_score=0.8,
        )
        with patch("ecommerce_ops.agents._base.store_decision_memory", new_callable=AsyncMock) as mock_store, patch(
            "ecommerce_ops.agents._base.agent_memory_manager"
        ) as mock_mgr:
            mock_mgr.store_decision = AsyncMock(side_effect=RuntimeError("db down"))
            await agent.persist_decision(decision)
            mock_store.assert_called_once()


class TestFraudAgent:
    def test_init(self):
        from ecommerce_ops.agents.fraud import FraudAgent
        with patch("ecommerce_ops.agents.fraud.BaseAgent.__init__"):
            agent = FraudAgent.__new__(FraudAgent)
            agent.agent_name = "FraudAgent"
            assert agent.agent_name == "FraudAgent"

    def test_assess_risk_suspicious_order(self):
        from ecommerce_ops.agents.fraud import FraudAgent
        agent = FraudAgent.__new__(FraudAgent)
        order = {"id": "o_suspicious"}
        score, factors = agent._assess_risk(order)
        assert score == 85
        assert "ip_shipping_mismatch" in factors

    def test_assess_risk_high_value_order(self):
        from ecommerce_ops.agents.fraud import FraudAgent
        agent = FraudAgent.__new__(FraudAgent)
        order = {"id": "o_high_value"}
        score, factors = agent._assess_risk(order)
        assert score == 60
        assert "amount_above_threshold" in factors

    def test_assess_risk_normal_order(self):
        from ecommerce_ops.agents.fraud import FraudAgent
        agent = FraudAgent.__new__(FraudAgent)
        order = {"id": "normal-order", "order_total": 50, "line_items": []}
        score, factors = agent._assess_risk(order)
        assert score == 50
        assert factors == ["standard_check"]

    def test_assess_risk_high_total(self):
        from ecommerce_ops.agents.fraud import FraudAgent
        agent = FraudAgent.__new__(FraudAgent)
        order = {"id": "order-1", "order_total": 2000, "line_items": []}
        score, factors = agent._assess_risk(order)
        assert score == 70
        assert "amount_above_threshold" in factors

    def test_assess_risk_bulk_order(self):
        from ecommerce_ops.agents.fraud import FraudAgent
        agent = FraudAgent.__new__(FraudAgent)
        items = [{"sku": f"s{i}"} for i in range(15)]
        order = {"id": "order-2", "order_total": 100, "line_items": items}
        score, factors = agent._assess_risk(order)
        assert score == 60
        assert "bulk_order" in factors

    def test_assess_risk_capped_at_100(self):
        from ecommerce_ops.agents.fraud import FraudAgent
        agent = FraudAgent.__new__(FraudAgent)
        items = [{"sku": f"s{i}"} for i in range(15)]
        order = {"id": "order-3", "order_total": 5000, "line_items": items}
        score, _factors = agent._assess_risk(order)
        assert score == 80

    @pytest.mark.asyncio
    async def test_run_no_orders(self):
        from ecommerce_ops.agents.fraud import FraudAgent
        agent = FraudAgent.__new__(FraudAgent)
        agent.agent_name = "FraudAgent"
        agent.persist_decision = AsyncMock()
        agent.create_decision = MagicMock(return_value=AgentDecision(
            agent_id="FraudAgent", action_type="HOLD_ORDER",
            reasoning="test", confidence_score=0.8,
        ))
        state = {"active_orders": []}
        result = await agent.run(state)
        assert result["decisions"] == []

    @pytest.mark.asyncio
    async def test_run_with_high_risk_order(self):
        from ecommerce_ops.agents.fraud import FraudAgent
        agent = FraudAgent.__new__(FraudAgent)
        agent.agent_name = "FraudAgent"
        agent.persist_decision = AsyncMock()
        order = {"id": "o_suspicious"}
        decision = AgentDecision(
            agent_id="FraudAgent", action_type="HOLD_ORDER",
            reasoning="Risk score 85", confidence_score=0.9,
            requires_approval=True,
        )
        agent.create_decision = MagicMock(return_value=decision)
        state = {"active_orders": [order]}
        result = await agent.run(state)
        assert len(result["decisions"]) == 1
        assert result["decisions"][0].requires_approval is True

    @pytest.mark.asyncio
    async def test_run_medium_risk_no_approval(self):
        from ecommerce_ops.agents.fraud import FraudAgent
        agent = FraudAgent.__new__(FraudAgent)
        agent.agent_name = "FraudAgent"
        agent.persist_decision = AsyncMock()
        order = {"id": "o_high_value"}
        decision = AgentDecision(
            agent_id="FraudAgent", action_type="HOLD_ORDER",
            reasoning="Risk score 60", confidence_score=0.8,
            requires_approval=False,
        )
        agent.create_decision = MagicMock(return_value=decision)
        state = {"active_orders": [order]}
        result = await agent.run(state)
        assert len(result["decisions"]) == 1

    @pytest.mark.asyncio
    async def test_run_preserves_existing_decisions(self):
        from ecommerce_ops.agents.fraud import FraudAgent
        agent = FraudAgent.__new__(FraudAgent)
        agent.agent_name = "FraudAgent"
        agent.persist_decision = AsyncMock()
        existing = AgentDecision(
            agent_id="Other", action_type="TEST",
            reasoning="existing", confidence_score=0.5,
        )
        state = {"active_orders": [], "decisions": [existing]}
        result = await agent.run(state)
        assert len(result["decisions"]) == 1
        assert result["decisions"][0].agent_id == "Other"


class TestInventoryAgent:
    def test_calculate_velocity_no_orders(self):
        from ecommerce_ops.agents.inventory import InventoryAgent
        agent = InventoryAgent.__new__(InventoryAgent)
        assert agent._calculate_velocity("SKU-A", []) == 0.0

    def test_calculate_velocity_with_matching_orders(self):
        from ecommerce_ops.agents.inventory import InventoryAgent
        agent = InventoryAgent.__new__(InventoryAgent)
        orders = [
            {"line_items": [{"sku": "SKU-A", "quantity": 30}]},
            {"line_items": [{"sku": "SKU-A", "quantity": 30}]},
        ]
        velocity = agent._calculate_velocity("SKU-A", orders)
        assert velocity == 2.0

    def test_calculate_velocity_no_match(self):
        from ecommerce_ops.agents.inventory import InventoryAgent
        agent = InventoryAgent.__new__(InventoryAgent)
        orders = [{"line_items": [{"sku": "SKU-B", "quantity": 10}]}]
        velocity = agent._calculate_velocity("SKU-A", orders)
        assert velocity == 0.0

    @pytest.mark.asyncio
    async def test_run_no_inventory(self):
        from ecommerce_ops.agents.inventory import InventoryAgent
        agent = InventoryAgent.__new__(InventoryAgent)
        agent.agent_name = "InventoryAgent"
        agent.load_memory_context = AsyncMock(return_value="")
        agent.persist_decision = AsyncMock()
        state = {"inventory_data": [], "active_orders": []}
        result = await agent.run(state)
        assert result["decisions"] == []

    @pytest.mark.asyncio
    async def test_run_item_with_zero_velocity(self):
        from ecommerce_ops.agents.inventory import InventoryAgent
        agent = InventoryAgent.__new__(InventoryAgent)
        agent.agent_name = "InventoryAgent"
        agent.load_memory_context = AsyncMock(return_value="")
        agent.persist_decision = AsyncMock()
        state = {
            "inventory_data": [{"sku": "SKU-X", "stock": 100}],
            "active_orders": [],
        }
        result = await agent.run(state)
        assert result["decisions"] == []

    @pytest.mark.asyncio
    async def test_run_item_low_stock_triggers_po(self):
        from ecommerce_ops.agents.inventory import InventoryAgent
        agent = InventoryAgent.__new__(InventoryAgent)
        agent.agent_name = "InventoryAgent"
        agent.load_memory_context = AsyncMock(return_value="")
        agent.persist_decision = AsyncMock()
        decision = AgentDecision(
            agent_id="InventoryAgent", action_type="DRAFT_PO",
            reasoning="test", confidence_score=0.95,
        )
        agent.create_decision = MagicMock(return_value=decision)
        orders = [{"line_items": [{"sku": "SKU-LOW", "quantity": 30}]}]
        state = {
            "inventory_data": [{"sku": "SKU-LOW", "stock": 5}],
            "active_orders": orders,
        }
        result = await agent.run(state)
        assert len(result["decisions"]) >= 1


class TestPricingAgent:
    @pytest.mark.asyncio
    async def test_run_no_inventory(self):
        from ecommerce_ops.agents.pricing import PricingAgent
        agent = PricingAgent.__new__(PricingAgent)
        agent.agent_name = "PricingAgent"
        agent.persist_decision = AsyncMock()
        state = {"inventory_data": []}
        result = await agent.run(state)
        assert result["decisions"] == []

    @pytest.mark.asyncio
    async def test_run_skip_no_competitor_price(self):
        from ecommerce_ops.agents.pricing import PricingAgent
        agent = PricingAgent.__new__(PricingAgent)
        agent.agent_name = "PricingAgent"
        agent.persist_decision = AsyncMock()
        agent._get_competitor_price = AsyncMock(return_value=None)
        state = {
            "inventory_data": [{"sku": "SKU-1", "price": 50.0, "variant_id": "v1"}],
        }
        result = await agent.run(state)
        assert result["decisions"] == []

    @pytest.mark.asyncio
    async def test_run_competitor_lower_price(self):
        from ecommerce_ops.agents.pricing import PricingAgent
        agent = PricingAgent.__new__(PricingAgent)
        agent.agent_name = "PricingAgent"
        agent.persist_decision = AsyncMock()
        agent._get_competitor_price = AsyncMock(return_value=40.0)
        decision = AgentDecision(
            agent_id="PricingAgent", action_type="UPDATE_PRICE",
            reasoning="test", confidence_score=0.85,
        )
        agent.create_decision = MagicMock(return_value=decision)
        state = {
            "inventory_data": [{"sku": "SKU-1", "price": 50.0, "variant_id": "v1"}],
        }
        result = await agent.run(state)
        assert len(result["decisions"]) >= 1

    @pytest.mark.asyncio
    async def test_run_competitor_higher_price_no_change(self):
        from ecommerce_ops.agents.pricing import PricingAgent
        agent = PricingAgent.__new__(PricingAgent)
        agent.agent_name = "PricingAgent"
        agent.persist_decision = AsyncMock()
        agent._get_competitor_price = AsyncMock(return_value=60.0)
        state = {
            "inventory_data": [{"sku": "SKU-1", "price": 50.0, "variant_id": "v1"}],
        }
        result = await agent.run(state)
        assert result["decisions"] == []

    @pytest.mark.asyncio
    async def test_get_competitor_price_cache_hit(self):
        from ecommerce_ops.agents.pricing import PricingAgent
        agent = PricingAgent.__new__(PricingAgent)
        with patch("ecommerce_ops.agents.pricing.cache") as mock_cache:
            mock_cache.get = AsyncMock(return_value=45.0)
            price = await agent._get_competitor_price("SKU-1")
            assert price == 45.0

    @pytest.mark.asyncio
    async def test_get_competitor_price_cache_miss_tool_hit(self):
        from ecommerce_ops.agents.pricing import PricingAgent
        agent = PricingAgent.__new__(PricingAgent)
        with patch("ecommerce_ops.agents.pricing.cache") as mock_cache:
            mock_cache.get = AsyncMock(return_value=None)
            mock_cache.set = AsyncMock(return_value=True)
            with patch("ecommerce_ops.agents.pricing.ToolRegistry") as mock_registry:
                mock_registry.run_tool = AsyncMock(return_value=55.0)
                price = await agent._get_competitor_price("SKU-1")
                assert price == 55.0
                mock_cache.set.assert_called_once()

    @pytest.mark.asyncio
    async def test_get_competitor_price_all_miss(self):
        from ecommerce_ops.agents.pricing import PricingAgent
        agent = PricingAgent.__new__(PricingAgent)
        with patch("ecommerce_ops.agents.pricing.cache") as mock_cache:
            mock_cache.get = AsyncMock(return_value=None)
            with patch("ecommerce_ops.agents.pricing.ToolRegistry") as mock_registry:
                mock_registry.run_tool = AsyncMock(return_value=None)
                price = await agent._get_competitor_price("SKU-1")
                assert price is None


class TestReviewsAgent:
    def test_fallback_analysis_positive(self):
        from ecommerce_ops.agents.reviews import ReviewsAgent
        agent = ReviewsAgent.__new__(ReviewsAgent)
        result = agent._fallback_analysis(5)
        assert result["sentiment"] == "Positive"
        assert result["contains_refund_offer"] is False

    def test_fallback_analysis_negative(self):
        from ecommerce_ops.agents.reviews import ReviewsAgent
        agent = ReviewsAgent.__new__(ReviewsAgent)
        result = agent._fallback_analysis(1)
        assert result["sentiment"] == "Negative"
        assert result["contains_refund_offer"] is True

    def test_fallback_analysis_neutral(self):
        from ecommerce_ops.agents.reviews import ReviewsAgent
        agent = ReviewsAgent.__new__(ReviewsAgent)
        result = agent._fallback_analysis(3)
        assert result["sentiment"] == "Neutral"
        assert result["contains_refund_offer"] is False

    @pytest.mark.asyncio
    async def test_analyze_review_short_content(self):
        from ecommerce_ops.agents.reviews import ReviewsAgent
        agent = ReviewsAgent.__new__(ReviewsAgent)
        agent._llm_circuit_breaker = MagicMock()
        agent._retry_llm = lambda f: f
        result = await agent._analyze_review("hi", 5)
        assert result["sentiment"] == "Neutral"
        assert result["confidence"] == 0.5

    @pytest.mark.asyncio
    async def test_analyze_review_cache_hit(self):
        from ecommerce_ops.agents.reviews import ReviewsAgent
        agent = ReviewsAgent.__new__(ReviewsAgent)
        cached = {"sentiment": "Positive", "themes": ["Quality"], "response": "Thanks!", "contains_refund_offer": False, "confidence": 0.9}
        with patch("ecommerce_ops.agents.reviews.llm_response_cache") as mock_cache:
            mock_cache.get = AsyncMock(return_value=cached)
            result = await agent._analyze_review("Great product, love it so much!", 5)
            assert result["sentiment"] == "Positive"

    @pytest.mark.asyncio
    async def test_analyze_review_llm_success(self):
        from ecommerce_ops.agents.reviews import ReviewAnalysisOutput, ReviewsAgent
        agent = ReviewsAgent.__new__(ReviewsAgent)
        llm_result = ReviewAnalysisOutput(
            sentiment="Positive", themes=["Quality"], response="Thank you!",
            contains_refund_offer=False, confidence=0.85,
        )
        breaker = MagicMock()
        breaker.call = AsyncMock(return_value=llm_result)
        agent._llm_circuit_breaker = breaker
        with patch("ecommerce_ops.agents.reviews.llm_response_cache") as mock_cache:
            mock_cache.get = AsyncMock(return_value=None)
            mock_cache.set = AsyncMock()
            result = await agent._analyze_review("Excellent product with amazing quality and fast shipping!", 5)
            assert result["sentiment"] == "Positive"
            mock_cache.set.assert_called_once()

    @pytest.mark.asyncio
    async def test_analyze_review_llm_sentiment_override_high_rating(self):
        from ecommerce_ops.agents.reviews import ReviewAnalysisOutput, ReviewsAgent
        agent = ReviewsAgent.__new__(ReviewsAgent)
        llm_result = ReviewAnalysisOutput(
            sentiment="Neutral", themes=["General"], response="Thanks",
            contains_refund_offer=False, confidence=0.5,
        )
        breaker = MagicMock()
        breaker.call = AsyncMock(return_value=llm_result)
        agent._llm_circuit_breaker = breaker
        with patch("ecommerce_ops.agents.reviews.llm_response_cache") as mock_cache:
            mock_cache.get = AsyncMock(return_value=None)
            mock_cache.set = AsyncMock()
            result = await agent._analyze_review("Really great product, happy with everything overall", 5)
            assert result["sentiment"] == "Positive"

    @pytest.mark.asyncio
    async def test_analyze_review_llm_sentiment_override_low_rating(self):
        from ecommerce_ops.agents.reviews import ReviewAnalysisOutput, ReviewsAgent
        agent = ReviewsAgent.__new__(ReviewsAgent)
        llm_result = ReviewAnalysisOutput(
            sentiment="Positive", themes=["General"], response="Thanks",
            contains_refund_offer=False, confidence=0.5,
        )
        breaker = MagicMock()
        breaker.call = AsyncMock(return_value=llm_result)
        agent._llm_circuit_breaker = breaker
        with patch("ecommerce_ops.agents.reviews.llm_response_cache") as mock_cache:
            mock_cache.get = AsyncMock(return_value=None)
            mock_cache.set = AsyncMock()
            result = await agent._analyze_review("Terrible quality, arrived broken and damaged badly", 1)
            assert result["sentiment"] == "Negative"

    @pytest.mark.asyncio
    async def test_analyze_review_llm_failure(self):
        from openai import APIError

        from ecommerce_ops.agents.reviews import ReviewsAgent
        agent = ReviewsAgent.__new__(ReviewsAgent)
        breaker = MagicMock()
        breaker.call = AsyncMock(side_effect=APIError(message="LLM down", request=MagicMock(), body=None))
        agent._llm_circuit_breaker = breaker
        result = await agent._analyze_review("Good product, fast shipping and great quality overall", 5)
        assert result["sentiment"] in ("Positive", "Neutral", "Negative")

    @pytest.mark.asyncio
    async def test_run_no_reviews(self):
        from ecommerce_ops.agents.reviews import ReviewsAgent
        agent = ReviewsAgent.__new__(ReviewsAgent)
        agent.agent_name = "ReviewsAgent"
        agent.persist_decision = AsyncMock()
        state = {"reviews_data": []}
        result = await agent.run(state)
        assert result["decisions"] == []

    @pytest.mark.asyncio
    async def test_run_with_review(self):
        from ecommerce_ops.agents.reviews import ReviewsAgent
        agent = ReviewsAgent.__new__(ReviewsAgent)
        agent.agent_name = "ReviewsAgent"
        agent.persist_decision = AsyncMock()
        analysis = {"sentiment": "Positive", "themes": ["Quality"], "response": "Thanks!", "contains_refund_offer": False, "confidence": 0.8}
        agent._analyze_review = AsyncMock(return_value=analysis)
        decision = AgentDecision(
            agent_id="ReviewsAgent", action_type="POST_REVIEW_RESPONSE",
            reasoning="test", confidence_score=0.8,
        )
        agent.create_decision = MagicMock(return_value=decision)
        state = {"reviews_data": [{"id": "r1", "content": "Great!", "rating": 5}]}
        result = await agent.run(state)
        assert len(result["decisions"]) == 1


class TestMarketingAgent:
    @pytest.mark.asyncio
    async def test_run_no_inventory(self):
        from ecommerce_ops.agents.marketing import MarketingAgent
        agent = MarketingAgent.__new__(MarketingAgent)
        agent.agent_name = "MarketingAgent"
        agent.persist_decision = AsyncMock()
        state = {"inventory_data": []}
        result = await agent.run(state)
        assert result["decisions"] == []

    @pytest.mark.asyncio
    async def test_run_stock_zero_no_campaign(self):
        from ecommerce_ops.agents.marketing import MarketingAgent
        agent = MarketingAgent.__new__(MarketingAgent)
        agent.agent_name = "MarketingAgent"
        agent.persist_decision = AsyncMock()
        state = {"inventory_data": [{"sku": "SKU-1", "stock": 0}]}
        result = await agent.run(state)
        assert result["decisions"] == []

    @pytest.mark.asyncio
    async def test_run_stock_100_no_campaign(self):
        from ecommerce_ops.agents.marketing import MarketingAgent
        agent = MarketingAgent.__new__(MarketingAgent)
        agent.agent_name = "MarketingAgent"
        agent.persist_decision = AsyncMock()
        state = {"inventory_data": [{"sku": "SKU-1", "stock": 100}]}
        result = await agent.run(state)
        assert result["decisions"] == []

    @pytest.mark.asyncio
    async def test_run_critical_stock(self):
        from ecommerce_ops.agents.marketing import MarketingAgent
        agent = MarketingAgent.__new__(MarketingAgent)
        agent.agent_name = "MarketingAgent"
        agent.persist_decision = AsyncMock()
        decision = AgentDecision(
            agent_id="MarketingAgent", action_type="DRAFT_MARKETING_CAMPAIGN",
            reasoning="test", confidence_score=0.85,
        )
        agent.create_decision = MagicMock(return_value=decision)
        state = {"inventory_data": [{"sku": "SKU-CRIT", "stock": 3}]}
        result = await agent.run(state)
        assert len(result["decisions"]) == 1

    @pytest.mark.asyncio
    async def test_run_moderate_stock(self):
        from ecommerce_ops.agents.marketing import MarketingAgent
        agent = MarketingAgent.__new__(MarketingAgent)
        agent.agent_name = "MarketingAgent"
        agent.persist_decision = AsyncMock()
        decision = AgentDecision(
            agent_id="MarketingAgent", action_type="DRAFT_MARKETING_CAMPAIGN",
            reasoning="test", confidence_score=0.75,
        )
        agent.create_decision = MagicMock(return_value=decision)
        state = {"inventory_data": [{"sku": "SKU-MOD", "stock": 15}]}
        result = await agent.run(state)
        assert len(result["decisions"]) == 1

    @pytest.mark.asyncio
    async def test_run_preserves_existing_decisions(self):
        from ecommerce_ops.agents.marketing import MarketingAgent
        agent = MarketingAgent.__new__(MarketingAgent)
        agent.agent_name = "MarketingAgent"
        agent.persist_decision = AsyncMock()
        existing = AgentDecision(
            agent_id="Other", action_type="TEST",
            reasoning="existing", confidence_score=0.5,
        )
        state = {"inventory_data": [], "decisions": [existing]}
        result = await agent.run(state)
        assert len(result["decisions"]) == 1


class TestReflectionAgent:
    @pytest.mark.asyncio
    async def test_run_passes_valid_decision(self):
        from ecommerce_ops.agents.reflection import ReflectionAgent
        agent = ReflectionAgent()
        decision = AgentDecision(
            agent_id="A", action_type="TEST",
            reasoning="Valid reasoning string here.", confidence_score=0.8,
            requires_approval=False,
        )
        feedback = await agent.run([decision])
        assert len(feedback) == 1
        assert feedback[0].passed is True
        assert feedback[0].issues == []

    @pytest.mark.asyncio
    async def test_run_flags_confidence_out_of_range(self):
        from ecommerce_ops.agents.reflection import ReflectionAgent
        agent = ReflectionAgent()
        decision = AgentDecision(
            agent_id="A", action_type="TEST",
            reasoning="Valid reasoning string here.", confidence_score=1.5,
            requires_approval=False,
        )
        feedback = await agent.run([decision])
        assert feedback[0].passed is False
        assert any("out of [0, 1]" in i for i in feedback[0].issues)
        assert feedback[0].adjusted_confidence == 1.0

    @pytest.mark.asyncio
    async def test_run_flags_negative_confidence(self):
        from ecommerce_ops.agents.reflection import ReflectionAgent
        agent = ReflectionAgent()
        decision = AgentDecision(
            agent_id="A", action_type="TEST",
            reasoning="Valid reasoning string here.", confidence_score=-0.5,
            requires_approval=False,
        )
        feedback = await agent.run([decision])
        assert feedback[0].passed is False
        assert feedback[0].adjusted_confidence == 0.0

    @pytest.mark.asyncio
    async def test_run_flags_high_confidence_with_approval(self):
        from ecommerce_ops.agents.reflection import ReflectionAgent
        agent = ReflectionAgent()
        decision = AgentDecision(
            agent_id="A", action_type="TEST",
            reasoning="Valid reasoning string here.", confidence_score=0.98,
            requires_approval=True,
        )
        feedback = await agent.run([decision])
        assert feedback[0].passed is False
        assert any("HITL" in i for i in feedback[0].issues)

    @pytest.mark.asyncio
    async def test_run_flags_low_confidence_auto_approved(self):
        from ecommerce_ops.agents.reflection import ReflectionAgent
        agent = ReflectionAgent()
        decision = AgentDecision(
            agent_id="A", action_type="TEST",
            reasoning="Valid reasoning string here.", confidence_score=0.3,
            requires_approval=False,
        )
        feedback = await agent.run([decision])
        assert feedback[0].passed is False
        assert any("auto-approved" in i for i in feedback[0].issues)

    @pytest.mark.asyncio
    async def test_run_flags_short_reasoning(self):
        from ecommerce_ops.agents.reflection import ReflectionAgent
        agent = ReflectionAgent()
        decision = AgentDecision(
            agent_id="A", action_type="TEST",
            reasoning="Short", confidence_score=0.8,
            requires_approval=False,
        )
        feedback = await agent.run([decision])
        assert feedback[0].passed is False
        assert any("too short" in i for i in feedback[0].issues)

    @pytest.mark.asyncio
    async def test_run_flags_fraud_hold_low_confidence(self):
        from ecommerce_ops.agents.reflection import ReflectionAgent
        agent = ReflectionAgent()
        decision = AgentDecision(
            agent_id="A", action_type="HOLD_ORDER",
            reasoning="Valid reasoning string here.", confidence_score=0.5,
            requires_approval=True,
        )
        feedback = await agent.run([decision])
        assert feedback[0].passed is False
        assert any("Fraud hold" in i for i in feedback[0].issues)

    @pytest.mark.asyncio
    async def test_run_empty_decisions(self):
        from ecommerce_ops.agents.reflection import ReflectionAgent
        agent = ReflectionAgent()
        feedback = await agent.run([])
        assert feedback == []

    @pytest.mark.asyncio
    async def test_correct_decision_passes_through(self):
        from ecommerce_ops.agents.reflection import ReflectionAgent
        agent = ReflectionAgent()
        decision = AgentDecision(
            agent_id="A", action_type="TEST",
            reasoning="Valid reasoning string here.", confidence_score=0.8,
        )
        fb = ReflectionFeedback(
            agent_id="A", decision_index=0, passed=True, issues=[],
        )
        result = await agent.correct_decision(decision, fb)
        assert result == decision

    @pytest.mark.asyncio
    async def test_correct_decision_adjusts_confidence(self):
        from ecommerce_ops.agents.reflection import ReflectionAgent
        agent = ReflectionAgent()
        decision = AgentDecision(
            agent_id="A", action_type="TEST",
            reasoning="Valid reasoning string here.", confidence_score=1.5,
        )
        fb = ReflectionFeedback(
            agent_id="A", decision_index=0, passed=False,
            issues=["out of range"], adjusted_confidence=1.0,
        )
        result = await agent.correct_decision(decision, fb)
        assert result.confidence_score == 1.0

    @pytest.mark.asyncio
    async def test_correct_decision_never_removes_hitl_gate(self):
        from ecommerce_ops.agents.reflection import ReflectionAgent
        agent = ReflectionAgent()
        decision = AgentDecision(
            agent_id="A", action_type="TEST",
            reasoning="Valid reasoning string here.", confidence_score=0.98,
            requires_approval=True,
        )
        fb = ReflectionFeedback(
            agent_id="A", decision_index=0, passed=False,
            issues=["High confidence decision sent to HITL"],
        )
        result = await agent.correct_decision(decision, fb)
        assert result.requires_approval is True

    @pytest.mark.asyncio
    async def test_correct_decision_auto_approved_adds_approval(self):
        from ecommerce_ops.agents.reflection import ReflectionAgent
        agent = ReflectionAgent()
        decision = AgentDecision(
            agent_id="A", action_type="TEST",
            reasoning="Valid reasoning string here.", confidence_score=0.3,
            requires_approval=False,
        )
        fb = ReflectionFeedback(
            agent_id="A", decision_index=0, passed=False,
            issues=["Low confidence decision auto-approved"],
        )
        result = await agent.correct_decision(decision, fb)
        assert result.requires_approval is True

