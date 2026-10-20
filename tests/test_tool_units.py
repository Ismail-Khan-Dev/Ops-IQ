import os

os.environ["ENV"] = "testing"
os.environ["DATABASE_URL"] = "sqlite+aiosqlite://"
os.environ["API_KEY"] = "test-key"
os.environ["DEEPSEEK_API_KEY"] = "sk-test-key"

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


class TestToolExecutor:
    def test_init(self):
        from ecommerce_ops.tools.executor import ToolExecutor
        te = ToolExecutor()
        assert te.registry is not None
        assert te._execution_history == []

    @pytest.mark.asyncio
    async def test_execute_permission_denied(self):
        from ecommerce_ops.tools.executor import ToolExecutor
        te = ToolExecutor()
        with patch.object(te.registry, "has_permission", return_value=False):
            result = await te.execute("tool1", "agent1", {})
            assert result["success"] is False
            assert "permission" in result["error"].lower()

    @pytest.mark.asyncio
    async def test_execute_tool_not_found(self):
        from ecommerce_ops.tools.executor import ToolExecutor
        te = ToolExecutor()
        with patch.object(te.registry, "has_permission", return_value=True):
            with patch.object(te.registry, "get_tool", return_value=None):
                result = await te.execute("nonexistent", "agent1", {})
                assert result["success"] is False
                assert "not found" in result["error"]

    @pytest.mark.asyncio
    async def test_execute_success(self):
        from ecommerce_ops.tools.executor import ToolExecutor
        te = ToolExecutor()
        mock_tool = MagicMock()
        mock_tool.ainvoke = AsyncMock(return_value={"status": "ok"})
        with patch.object(te.registry, "has_permission", return_value=True):
            with patch.object(te.registry, "get_tool", return_value=mock_tool):
                result = await te.execute("tool1", "agent1", {"arg": "val"})
                assert result["success"] is True
                assert result["result"] == {"status": "ok"}
                assert result["execution_time_ms"] >= 0

    @pytest.mark.asyncio
    async def test_execute_failure(self):
        from ecommerce_ops.tools.executor import ToolExecutor
        te = ToolExecutor()
        mock_tool = MagicMock()
        mock_tool.ainvoke = AsyncMock(side_effect=RuntimeError("tool error"))
        with patch.object(te.registry, "has_permission", return_value=True):
            with patch.object(te.registry, "get_tool", return_value=mock_tool):
                result = await te.execute("tool1", "agent1", {})
                assert result["success"] is False
                assert "tool error" in result["error"]

    @pytest.mark.asyncio
    async def test_execute_records_history(self):
        from ecommerce_ops.tools.executor import ToolExecutor
        te = ToolExecutor()
        mock_tool = MagicMock()
        mock_tool.ainvoke = AsyncMock(return_value="ok")
        with patch.object(te.registry, "has_permission", return_value=True):
            with patch.object(te.registry, "get_tool", return_value=mock_tool):
                await te.execute("tool1", "agent1", {})
                assert len(te._execution_history) == 1
                assert te._execution_history[0]["tool_name"] == "tool1"

    @pytest.mark.asyncio
    async def test_execute_failure_records_history(self):
        from ecommerce_ops.tools.executor import ToolExecutor
        te = ToolExecutor()
        mock_tool = MagicMock()
        mock_tool.ainvoke = AsyncMock(side_effect=ValueError("fail"))
        with patch.object(te.registry, "has_permission", return_value=True):
            with patch.object(te.registry, "get_tool", return_value=mock_tool):
                await te.execute("tool1", "agent1", {})
                assert len(te._execution_history) == 1
                assert te._execution_history[0]["success"] is False

    @pytest.mark.asyncio
    async def test_execute_with_trace_id(self):
        from ecommerce_ops.tools.executor import ToolExecutor
        te = ToolExecutor()
        mock_tool = MagicMock()
        mock_tool.ainvoke = AsyncMock(return_value="ok")
        with patch.object(te.registry, "has_permission", return_value=True):
            with patch.object(te.registry, "get_tool", return_value=mock_tool):
                result = await te.execute("tool1", "agent1", {}, trace_id="trace-1")
                assert te._execution_history[0]["trace_id"] == "trace-1"

    @pytest.mark.asyncio
    async def test_execute_batch(self):
        from ecommerce_ops.tools.executor import ToolExecutor
        te = ToolExecutor()
        mock_tool = MagicMock()
        mock_tool.ainvoke = AsyncMock(return_value="ok")
        with patch.object(te.registry, "has_permission", return_value=True):
            with patch.object(te.registry, "get_tool", return_value=mock_tool):
                calls = [
                    {"tool_name": "t1", "arguments": {}},
                    {"tool_name": "t2", "arguments": {"x": 1}},
                ]
                results = await te.execute_batch(calls, "agent1")
                assert len(results) == 2
                assert all(r["success"] for r in results)

    @pytest.mark.asyncio
    async def test_execute_batch_empty(self):
        from ecommerce_ops.tools.executor import ToolExecutor
        te = ToolExecutor()
        results = await te.execute_batch([], "agent1")
        assert results == []

    def test_get_history_empty(self):
        from ecommerce_ops.tools.executor import ToolExecutor
        te = ToolExecutor()
        assert te.get_history() == []

    def test_get_history_with_entries(self):
        from ecommerce_ops.tools.executor import ToolExecutor
        te = ToolExecutor()
        te._execution_history = [
            {"agent_id": "a1", "tool_name": "t1", "success": True, "execution_time_ms": 10},
            {"agent_id": "a2", "tool_name": "t2", "success": False, "execution_time_ms": 5},
        ]
        assert len(te.get_history()) == 2

    def test_get_history_filter_by_agent(self):
        from ecommerce_ops.tools.executor import ToolExecutor
        te = ToolExecutor()
        te._execution_history = [
            {"agent_id": "a1", "tool_name": "t1", "success": True, "execution_time_ms": 10},
            {"agent_id": "a2", "tool_name": "t2", "success": False, "execution_time_ms": 5},
        ]
        history = te.get_history(agent_id="a1")
        assert len(history) == 1
        assert history[0]["agent_id"] == "a1"

    def test_get_history_filter_by_tool(self):
        from ecommerce_ops.tools.executor import ToolExecutor
        te = ToolExecutor()
        te._execution_history = [
            {"agent_id": "a1", "tool_name": "t1", "success": True, "execution_time_ms": 10},
            {"agent_id": "a2", "tool_name": "t2", "success": False, "execution_time_ms": 5},
        ]
        history = te.get_history(tool_name="t2")
        assert len(history) == 1

    def test_get_history_limit(self):
        from ecommerce_ops.tools.executor import ToolExecutor
        te = ToolExecutor()
        te._execution_history = [
            {"agent_id": "a1", "tool_name": f"t{i}", "success": True, "execution_time_ms": i}
            for i in range(20)
        ]
        history = te.get_history(limit=5)
        assert len(history) == 5

    def test_get_stats_empty(self):
        from ecommerce_ops.tools.executor import ToolExecutor
        te = ToolExecutor()
        stats = te.get_stats()
        assert stats["total_calls"] == 0
        assert stats["success_rate"] == 0

    def test_get_stats_with_data(self):
        from ecommerce_ops.tools.executor import ToolExecutor
        te = ToolExecutor()
        te._execution_history = [
            {"agent_id": "a1", "tool_name": "t1", "success": True, "execution_time_ms": 10},
            {"agent_id": "a1", "tool_name": "t2", "success": True, "execution_time_ms": 20},
            {"agent_id": "a2", "tool_name": "t3", "success": False, "execution_time_ms": 5},
        ]
        stats = te.get_stats()
        assert stats["total_calls"] == 3
        assert stats["successful_calls"] == 2
        assert stats["failed_calls"] == 1
        assert stats["success_rate"] == pytest.approx(2 / 3)
        assert stats["avg_execution_time_ms"] == pytest.approx(35 / 3)

    def test_get_stats_filter_by_agent(self):
        from ecommerce_ops.tools.executor import ToolExecutor
        te = ToolExecutor()
        te._execution_history = [
            {"agent_id": "a1", "tool_name": "t1", "success": True, "execution_time_ms": 10},
            {"agent_id": "a2", "tool_name": "t2", "success": False, "execution_time_ms": 5},
        ]
        stats = te.get_stats(agent_id="a1")
        assert stats["total_calls"] == 1
        assert stats["success_rate"] == 1.0


class TestCircuitBreaker:
    @pytest.mark.asyncio
    async def test_call_success(self):
        from ecommerce_ops.infra.circuit_breaker import CircuitBreaker
        cb = CircuitBreaker("test", failure_threshold=3, recovery_timeout=1.0)

        async def ok():
            return "ok"

        result = await cb.call(ok)
        assert result == "ok"
        assert cb.state.value == "closed"

    @pytest.mark.asyncio
    async def test_call_failure_increments_count(self):
        from ecommerce_ops.infra.circuit_breaker import CircuitBreaker
        cb = CircuitBreaker("test", failure_threshold=3, recovery_timeout=1.0)

        async def fail():
            raise ValueError("fail")

        with pytest.raises(ValueError):
            await cb.call(fail)
        assert cb._failure_count == 1

    @pytest.mark.asyncio
    async def test_call_opens_after_threshold(self):
        from ecommerce_ops.infra.circuit_breaker import CircuitBreaker, CircuitBreakerOpenError
        cb = CircuitBreaker("test", failure_threshold=2, recovery_timeout=10.0)

        async def fail():
            raise ValueError("fail")

        with pytest.raises(ValueError):
            await cb.call(fail)
        with pytest.raises(ValueError):
            await cb.call(fail)
        assert cb.state.value == "open"
        with pytest.raises(CircuitBreakerOpenError):
            await cb.call(fail)

    @pytest.mark.asyncio
    async def test_reset(self):
        from ecommerce_ops.infra.circuit_breaker import CircuitBreaker
        cb = CircuitBreaker("test", failure_threshold=2, recovery_timeout=10.0)
        cb._failure_count = 5
        cb._state = cb._state.__class__.OPEN
        await cb.reset()
        assert cb.state.value == "closed"
        assert cb._failure_count == 0


class TestRetry:
    def test_async_retry_decorator_is_callable(self):
        from ecommerce_ops.infra.retry import async_retry_decorator
        dec = async_retry_decorator(exceptions=(ValueError,), max_attempts=2)
        assert callable(dec)

    def test_async_retry_returns_function(self):
        from ecommerce_ops.infra.retry import async_retry_decorator
        dec = async_retry_decorator(exceptions=(ValueError,), max_attempts=2)

        @dec
        async def my_func():
            return 42

        assert asyncio.iscoroutinefunction(my_func)


class TestToolRegistrySimple:
    def test_register_and_get(self):
        from ecommerce_ops.tools.registry import Tool, ToolRegistry
        reg = ToolRegistry()
        reg._tools.clear()

        class DummyTool(Tool):
            name = "dummy"
            description = "A dummy tool"
            async def run(self, **kwargs):
                return "ok"

        reg.register(DummyTool())
        assert reg.get("dummy") is not None

    def test_get_nonexistent(self):
        from ecommerce_ops.tools.registry import ToolRegistry
        reg = ToolRegistry()
        reg._tools.clear()
        assert reg.get("nonexistent") is None

    def test_list_tools(self):
        from ecommerce_ops.tools.registry import Tool, ToolRegistry
        reg = ToolRegistry()
        reg._tools.clear()

        class DummyTool(Tool):
            name = "dummy"
            description = "A dummy tool"
            async def run(self, **kwargs):
                return "ok"

        reg.register(DummyTool())
        tools = reg.list_tools()
        assert len(tools) == 1
        assert tools[0]["name"] == "dummy"

    @pytest.mark.asyncio
    async def test_run_tool(self):
        from ecommerce_ops.tools.registry import Tool, ToolRegistry
        reg = ToolRegistry()
        reg._tools.clear()

        class DummyTool(Tool):
            name = "dummy"
            description = "A dummy tool"
            async def run(self, **kwargs):
                return "result"

        reg.register(DummyTool())
        result = await reg.run_tool("dummy", x=1)
        assert result == "result"

    @pytest.mark.asyncio
    async def test_run_tool_unknown(self):
        from ecommerce_ops.tools.registry import ToolRegistry
        reg = ToolRegistry()
        reg._tools.clear()
        with pytest.raises(ValueError, match="Unknown tool"):
            await reg.run_tool("nonexistent")


class TestToolDefinitions:
    def test_tool_registry_singleton_has_tools(self):
        from ecommerce_ops.tools.definitions import tool_registry
        tools = tool_registry.get_all_tools()
        assert len(tools) >= 10

    def test_has_permission_known_agent(self):
        from ecommerce_ops.tools.definitions import tool_registry
        assert tool_registry.has_permission("fraud_detection", "get_order") is True
        assert tool_registry.has_permission("fraud_detection", "send_email") is False

    def test_has_permission_unknown_agent(self):
        from ecommerce_ops.tools.definitions import tool_registry
        assert tool_registry.has_permission("unknown_agent", "get_order") is False

    def test_get_tools_for_agent(self):
        from ecommerce_ops.tools.definitions import tool_registry
        tools = tool_registry.get_tools_for_agent("fraud_detection")
        assert len(tools) > 0

    def test_get_tools_for_unknown_agent(self):
        from ecommerce_ops.tools.definitions import tool_registry
        tools = tool_registry.get_tools_for_agent("unknown")
        assert tools == []

    def test_get_tool_schemas(self):
        from ecommerce_ops.tools.definitions import tool_registry
        schemas = tool_registry.get_tool_schemas()
        assert len(schemas) > 0
        assert "function" in schemas[0]

    def test_get_all_tools(self):
        from ecommerce_ops.tools.definitions import tool_registry
        tools = tool_registry.get_all_tools()
        assert len(tools) >= 14

    @pytest.mark.asyncio
    async def test_send_email_tool(self):
        from ecommerce_ops.tools.definitions import _send_email
        result = await _send_email("test@test.com", "Subject", "Body")
        assert result["success"] is True

    @pytest.mark.asyncio
    async def test_send_sms_tool(self):
        from ecommerce_ops.tools.definitions import _send_sms
        result = await _send_sms("+1234567890", "Hello")
        assert result["success"] is True

    @pytest.mark.asyncio
    async def test_search_products_tool(self):
        from ecommerce_ops.tools.definitions import _search_products
        result = await _search_products("shoes")
        assert "products" in result

    @pytest.mark.asyncio
    async def test_get_order_tool(self):
        from ecommerce_ops.tools.definitions import _get_order
        result = await _get_order("order-123")
        assert result["order_id"] == "order-123"

    @pytest.mark.asyncio
    async def test_analyze_customer_tool(self):
        from ecommerce_ops.tools.definitions import _analyze_customer
        result = await _analyze_customer("cust-1")
        assert result["customer_id"] == "cust-1"

    @pytest.mark.asyncio
    async def test_update_inventory_tool(self):
        from ecommerce_ops.tools.definitions import _update_inventory
        result = await _update_inventory("prod-1", 50, reason="restock")
        assert result["success"] is True

    @pytest.mark.asyncio
    async def test_log_audit_event_tool(self):
        from ecommerce_ops.tools.definitions import _log_audit_event
        result = await _log_audit_event("auth", "login", "user")
        assert result["success"] is True

    @pytest.mark.asyncio
    async def test_check_inventory_level_tool(self):
        from ecommerce_ops.tools.definitions import _check_inventory_level
        result = await _check_inventory_level("prod-1")
        assert result["product_id"] == "prod-1"

    @pytest.mark.asyncio
    async def test_get_customer_history_tool(self):
        from ecommerce_ops.tools.definitions import _get_customer_history
        result = await _get_customer_history("cust-1")
        assert result["customer_id"] == "cust-1"

    @pytest.mark.asyncio
    async def test_create_purchase_order_tool(self):
        from ecommerce_ops.tools.definitions import _create_purchase_order
        result = await _create_purchase_order("sup-1", "prod-1", 10, 5.0)
        assert result["success"] is True

    @pytest.mark.asyncio
    async def test_update_shopify_price_tool(self):
        from ecommerce_ops.tools.definitions import _update_shopify_price
        result = await _update_shopify_price("prod-1", 29.99, reason="sale")
        assert result["success"] is True

    @pytest.mark.asyncio
    async def test_create_discount_code_tool(self):
        from ecommerce_ops.tools.definitions import _create_discount_code
        result = await _create_discount_code("SAVE10", "percentage", 10.0)
        assert result["success"] is True

    @pytest.mark.asyncio
    async def test_send_slack_message_tool(self):
        from ecommerce_ops.tools.definitions import _send_slack_message
        result = await _send_slack_message("general", "Hello team!")
        assert result["success"] is True

    @pytest.mark.asyncio
    async def test_create_shopify_order_tool(self):
        from ecommerce_ops.tools.definitions import _create_shopify_order
        result = await _create_shopify_order(
            "test@test.com",
            [{"product_id": "p1", "quantity": 2, "price": 10.0}],
        )
        assert result["success"] is True
        assert result["total"] == 20.0

