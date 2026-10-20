import os

os.environ["ENV"] = "testing"
os.environ["DATABASE_URL"] = "sqlite+aiosqlite://"
os.environ["API_KEY"] = "test-key"
os.environ["DEEPSEEK_API_KEY"] = "sk-test-key"

from unittest.mock import AsyncMock, patch

import pytest


class TestCache:
    def test_cache_key_generation(self):
        from ecommerce_ops.memory.cache import _cache_key
        key1 = _cache_key("GET", "/api/analytics", "q=1")
        key2 = _cache_key("GET", "/api/analytics", "q=1")
        assert key1 == key2
        assert key1.startswith("http_cache:")

    def test_cache_key_different_inputs(self):
        from ecommerce_ops.memory.cache import _cache_key
        key1 = _cache_key("GET", "/api/analytics")
        key2 = _cache_key("POST", "/api/analytics")
        assert key1 != key2

    def test_get_ttl_match(self):
        from ecommerce_ops.memory.cache import _get_ttl
        assert _get_ttl("/api/analytics") == 10
        assert _get_ttl("/api/agents/status") == 5
        assert _get_ttl("/api/settings") == 30
        assert _get_ttl("/api/approvals") == 5
        assert _get_ttl("/api/audit") == 10
        assert _get_ttl("/health") == 5

    def test_get_ttl_no_match(self):
        from ecommerce_ops.memory.cache import _get_ttl
        assert _get_ttl("/unknown/path") == 0

    @pytest.mark.asyncio
    async def test_redis_cache_get_returns_none_when_no_client(self):
        from ecommerce_ops.memory.cache import RedisCache
        rc = RedisCache()
        rc._redis = None
        with patch.object(rc, "get_client", new_callable=AsyncMock, return_value=None):
            result = await rc.get("key")
            assert result is None

    @pytest.mark.asyncio
    async def test_redis_cache_set_returns_false_when_no_client(self):
        from ecommerce_ops.memory.cache import RedisCache
        rc = RedisCache()
        rc._redis = None
        with patch.object(rc, "get_client", new_callable=AsyncMock, return_value=None):
            result = await rc.set("key", "value")
            assert result is False

    @pytest.mark.asyncio
    async def test_redis_cache_close(self):
        from ecommerce_ops.memory.cache import RedisCache
        rc = RedisCache()
        rc._redis = AsyncMock()
        await rc.close()
        assert rc._redis is None

    @pytest.mark.asyncio
    async def test_redis_cache_close_no_client(self):
        from ecommerce_ops.memory.cache import RedisCache
        rc = RedisCache()
        rc._redis = None
        await rc.close()

    @pytest.mark.asyncio
    async def test_get_cached_response_no_ttl(self):
        from ecommerce_ops.memory.cache import RedisCache
        rc = RedisCache()
        result = await rc.get_cached_response("GET", "/unknown/path")
        assert result is None

    @pytest.mark.asyncio
    async def test_get_cached_response_post_method(self):
        from ecommerce_ops.memory.cache import RedisCache
        rc = RedisCache()
        result = await rc.get_cached_response("POST", "/api/analytics")
        assert result is None

    @pytest.mark.asyncio
    async def test_set_cached_response_no_ttl(self):
        from ecommerce_ops.memory.cache import RedisCache
        rc = RedisCache()
        rc._redis = AsyncMock()
        await rc.set_cached_response("POST", "/api/analytics", "", 200, {})

    @pytest.mark.asyncio
    async def test_get_client_initializes(self):
        from ecommerce_ops.config import Environment
        from ecommerce_ops.memory.cache import RedisCache
        rc = RedisCache()
        rc._redis = None
        with patch("ecommerce_ops.memory.cache.settings.ENV", Environment.DEVELOPMENT), patch(
            "ecommerce_ops.memory.cache.redis"
        ) as mock_redis_mod:
            mock_client = AsyncMock()
            mock_client.ping = AsyncMock()
            mock_redis_mod.from_url.return_value = mock_client
            client = await rc.get_client()
            assert client == mock_client

    @pytest.mark.asyncio
    async def test_get_client_failure(self):
        from ecommerce_ops.config import Environment
        from ecommerce_ops.memory.cache import RedisCache
        rc = RedisCache()
        rc._redis = None
        with patch("ecommerce_ops.memory.cache.settings.ENV", Environment.DEVELOPMENT), patch(
            "ecommerce_ops.memory.cache.redis"
        ) as mock_redis_mod:
            mock_redis_mod.from_url.side_effect = Exception("Connection refused")
            client = await rc.get_client()
            assert client is None

    @pytest.mark.asyncio
    async def test_get_client_skips_network_in_testing(self):
        from ecommerce_ops.config import Environment, settings
        from ecommerce_ops.memory.cache import RedisCache
        rc = RedisCache()
        rc._redis = None
        assert settings.ENV == Environment.TESTING
        with patch("ecommerce_ops.memory.cache.redis") as mock_redis_mod:
            client = await rc.get_client()
            assert client is None
            mock_redis_mod.from_url.assert_not_called()

    @pytest.mark.asyncio
    async def test_get_with_retry_no_client(self):
        from ecommerce_ops.memory.cache import RedisCache
        rc = RedisCache()
        with patch.object(rc, "get_client", new_callable=AsyncMock, return_value=None):
            result = await rc._get_with_retry("key")
            assert result is None

    @pytest.mark.asyncio
    async def test_set_with_retry_no_client(self):
        from ecommerce_ops.memory.cache import RedisCache
        rc = RedisCache()
        with patch.object(rc, "get_client", new_callable=AsyncMock, return_value=None):
            result = await rc._set_with_retry("key", "value", 60)
            assert result is False

    @pytest.mark.asyncio
    async def test_get_with_retry_success(self):
        import json

        from ecommerce_ops.memory.cache import RedisCache
        rc = RedisCache()
        mock_client = AsyncMock()
        mock_client.get = AsyncMock(return_value=json.dumps({"data": "test"}))
        with patch.object(rc, "get_client", new_callable=AsyncMock, return_value=mock_client):
            result = await rc._get_with_retry("key")
            assert result == {"data": "test"}

    @pytest.mark.asyncio
    async def test_get_with_retry_none_value(self):
        from ecommerce_ops.memory.cache import RedisCache
        rc = RedisCache()
        mock_client = AsyncMock()
        mock_client.get = AsyncMock(return_value=None)
        with patch.object(rc, "get_client", new_callable=AsyncMock, return_value=mock_client):
            result = await rc._get_with_retry("key")
            assert result is None

    @pytest.mark.asyncio
    async def test_set_with_retry_success(self):
        from ecommerce_ops.memory.cache import RedisCache
        rc = RedisCache()
        mock_client = AsyncMock()
        mock_client.set = AsyncMock()
        with patch.object(rc, "get_client", new_callable=AsyncMock, return_value=mock_client):
            result = await rc._set_with_retry("key", {"data": 1}, 60)
            assert result is True
            mock_client.set.assert_called_once()

    @pytest.mark.asyncio
    async def test_get_circuit_breaker_open(self):
        from ecommerce_ops.infra.circuit_breaker import CircuitBreakerOpenError
        from ecommerce_ops.memory.cache import RedisCache
        rc = RedisCache()
        with patch.object(rc._circuit_breaker, "call", new_callable=AsyncMock, side_effect=CircuitBreakerOpenError("open")):
            result = await rc.get("key")
            assert result is None

    @pytest.mark.asyncio
    async def test_set_circuit_breaker_open(self):
        from ecommerce_ops.infra.circuit_breaker import CircuitBreakerOpenError
        from ecommerce_ops.memory.cache import RedisCache
        rc = RedisCache()
        with patch.object(rc._circuit_breaker, "call", new_callable=AsyncMock, side_effect=CircuitBreakerOpenError("open")):
            result = await rc.set("key", "value")
            assert result is False


class TestAgentMemory:
    @pytest.mark.asyncio
    async def test_store_decision_memory_no_client(self):
        from ecommerce_ops.memory.agent_memory import store_decision_memory
        with patch("ecommerce_ops.memory.agent_memory.cache") as mock_cache:
            mock_cache.get_client = AsyncMock(return_value=None)
            await store_decision_memory("agent1", {"action_type": "TEST"})

    @pytest.mark.asyncio
    async def test_store_decision_memory_success(self):
        from ecommerce_ops.memory.agent_memory import store_decision_memory
        with patch("ecommerce_ops.memory.agent_memory.cache") as mock_cache:
            mock_client = AsyncMock()
            mock_client.lpush = AsyncMock()
            mock_client.ltrim = AsyncMock()
            mock_client.expire = AsyncMock()
            mock_cache.get_client = AsyncMock(return_value=mock_client)
            await store_decision_memory("agent1", {"action_type": "TEST", "confidence_score": 0.8, "reasoning": "test"})
            mock_client.lpush.assert_called_once()

    @pytest.mark.asyncio
    async def test_store_decision_memory_exception(self):
        from ecommerce_ops.memory.agent_memory import store_decision_memory
        with patch("ecommerce_ops.memory.agent_memory.cache") as mock_cache:
            mock_cache.get_client = AsyncMock(side_effect=Exception("Redis error"))
            await store_decision_memory("agent1", {"action_type": "TEST"})

    @pytest.mark.asyncio
    async def test_get_recent_memories_no_client(self):
        from ecommerce_ops.memory.agent_memory import get_recent_memories
        with patch("ecommerce_ops.memory.agent_memory.cache") as mock_cache:
            mock_cache.get_client = AsyncMock(return_value=None)
            result = await get_recent_memories("agent1")
            assert result == []

    @pytest.mark.asyncio
    async def test_get_recent_memories_success(self):
        import json

        from ecommerce_ops.memory.agent_memory import get_recent_memories
        with patch("ecommerce_ops.memory.agent_memory.cache") as mock_cache:
            mock_client = AsyncMock()
            mock_client.lrange = AsyncMock(return_value=[json.dumps({"action_type": "TEST"})])
            mock_cache.get_client = AsyncMock(return_value=mock_client)
            result = await get_recent_memories("agent1")
            assert len(result) == 1

    @pytest.mark.asyncio
    async def test_get_recent_memories_exception(self):
        from ecommerce_ops.memory.agent_memory import get_recent_memories
        with patch("ecommerce_ops.memory.agent_memory.cache") as mock_cache:
            mock_cache.get_client = AsyncMock(side_effect=Exception("error"))
            result = await get_recent_memories("agent1")
            assert result == []

    @pytest.mark.asyncio
    async def test_get_pattern_insight_insufficient_data(self):
        from ecommerce_ops.memory.agent_memory import get_pattern_insight
        with patch("ecommerce_ops.memory.agent_memory.get_recent_memories", new_callable=AsyncMock) as mock_get:
            mock_get.return_value = [{"requires_approval": True, "confidence": 0.5}] * 3
            result = await get_pattern_insight("agent1")
            assert result is None

    @pytest.mark.asyncio
    async def test_get_pattern_insight_high_confidence(self):
        from ecommerce_ops.memory.agent_memory import get_pattern_insight
        with patch("ecommerce_ops.memory.agent_memory.get_recent_memories", new_callable=AsyncMock) as mock_get:
            memories = [{"requires_approval": False, "confidence": 0.9} for _ in range(10)]
            mock_get.return_value = memories
            result = await get_pattern_insight("agent1")
            assert "high-confidence" in result

    @pytest.mark.asyncio
    async def test_get_pattern_insight_mixed(self):
        from ecommerce_ops.memory.agent_memory import get_pattern_insight
        with patch("ecommerce_ops.memory.agent_memory.get_recent_memories", new_callable=AsyncMock) as mock_get:
            memories = [{"requires_approval": True, "confidence": 0.5} for _ in range(10)]
            mock_get.return_value = memories
            result = await get_pattern_insight("agent1")
            assert "Mix" in result

