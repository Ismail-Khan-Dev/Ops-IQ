import os

os.environ["ENV"] = "testing"
os.environ["DATABASE_URL"] = "sqlite+aiosqlite://"
os.environ["API_KEY"] = "test-key"
os.environ["DEEPSEEK_API_KEY"] = "sk-test-key"

from unittest.mock import AsyncMock

import pytest


class TestCosineSimilarity:
    def test_identical_vectors(self):
        from ecommerce_ops.memory.llm_cache import cosine_similarity
        assert cosine_similarity([1, 0, 0], [1, 0, 0]) == 1.0

    def test_orthogonal_vectors(self):
        from ecommerce_ops.memory.llm_cache import cosine_similarity
        assert cosine_similarity([1, 0, 0], [0, 1, 0]) == 0.0

    def test_opposite_vectors(self):
        from ecommerce_ops.memory.llm_cache import cosine_similarity
        assert cosine_similarity([1, 0, 0], [-1, 0, 0]) == -1.0

    def test_zero_vector_returns_zero(self):
        from ecommerce_ops.memory.llm_cache import cosine_similarity
        assert cosine_similarity([0, 0, 0], [1, 0, 0]) == 0.0

    def test_mismatched_lengths_return_zero(self):
        from ecommerce_ops.memory.llm_cache import cosine_similarity
        assert cosine_similarity([1, 0], [1, 0, 0]) == 0.0

    def test_partial_similarity(self):
        from ecommerce_ops.memory.llm_cache import cosine_similarity
        sim = cosine_similarity([1, 0, 0], [1, 1, 0])
        assert 0.5 < sim < 1.0


class TestNormalize:
    def test_normalize_collapses_whitespace(self):
        from ecommerce_ops.memory.llm_cache import SemanticLLMCache
        assert SemanticLLMCache._normalize("  a\n  b  ") == "a b"

    def test_normalize_handles_non_string(self):
        from ecommerce_ops.memory.llm_cache import SemanticLLMCache
        assert SemanticLLMCache._normalize(42) == "42"


class TestSemanticLLMCache:
    @pytest.mark.asyncio
    async def test_exact_match_hit(self):
        from ecommerce_ops.memory.llm_cache import SemanticLLMCache

        backend = AsyncMock()
        backend.get = AsyncMock(return_value={"response": {"decision": "approve"}})
        cache = SemanticLLMCache(backend=backend)
        result = await cache.get("same prompt", namespace="test")
        assert result == {"decision": "approve"}

    @pytest.mark.asyncio
    async def test_exact_miss_falls_back_to_semantic(self):
        from ecommerce_ops.memory.llm_cache import SemanticLLMCache

        backend = AsyncMock()
        backend.get = AsyncMock(return_value=None)
        embedder = AsyncMock()
        embedder.embed = AsyncMock(return_value=[1.0, 0.0, 0.0])

        cache = SemanticLLMCache(backend=backend, embedder=embedder, threshold=0.5)
        result = await cache.get("new prompt", namespace="test")
        assert result is None

    @pytest.mark.asyncio
    async def test_semantic_match_returns_best_entry(self):
        from ecommerce_ops.memory.llm_cache import SemanticLLMCache

        def fake_get(key):
            if key == "llm_semantic:index":
                return ["hash1"]
            if key == "llm_semantic:test:hash1":
                return {"response": {"decision": "approve"}, "embedding": [0.99, 0.0, 0.01]}
            return None

        backend = AsyncMock()
        backend.get = AsyncMock(side_effect=fake_get)
        embedder = AsyncMock()
        embedder.embed = AsyncMock(return_value=[1.0, 0.0, 0.0])

        cache = SemanticLLMCache(backend=backend, embedder=embedder, threshold=0.5)
        result = await cache.get("similar prompt", namespace="test")
        assert result == {"decision": "approve"}

    @pytest.mark.asyncio
    async def test_semantic_below_threshold_returns_none(self):
        from ecommerce_ops.memory.llm_cache import SemanticLLMCache

        def fake_get(key):
            if key == "llm_semantic:index":
                return ["hash1"]
            if key == "llm_semantic:test:hash1":
                return {"response": {"decision": "reject"}, "embedding": [0.0, 0.0, 1.0]}
            return None

        backend = AsyncMock()
        backend.get = AsyncMock(side_effect=fake_get)
        embedder = AsyncMock()
        embedder.embed = AsyncMock(return_value=[1.0, 0.0, 0.0])

        cache = SemanticLLMCache(backend=backend, embedder=embedder, threshold=0.95)
        result = await cache.get("different prompt", namespace="test")
        assert result is None

    @pytest.mark.asyncio
    async def test_embedding_failure_returns_none(self):
        from ecommerce_ops.memory.llm_cache import SemanticLLMCache

        backend = AsyncMock()
        backend.get = AsyncMock(return_value=None)
        embedder = AsyncMock()
        embedder.embed = AsyncMock(side_effect=RuntimeError("no embedder"))

        cache = SemanticLLMCache(backend=backend, embedder=embedder)
        result = await cache.get("prompt", namespace="test")
        assert result is None

    @pytest.mark.asyncio
    async def test_set_writes_exact_and_index(self):
        from ecommerce_ops.memory.llm_cache import SemanticLLMCache

        backend = AsyncMock()
        backend.get = AsyncMock(return_value=None)
        backend.set = AsyncMock(return_value=True)
        embedder = AsyncMock()
        embedder.embed = AsyncMock(return_value=[1.0, 0.0, 0.0])

        cache = SemanticLLMCache(backend=backend, embedder=embedder)
        await cache.set("some prompt", {"decision": "approve"}, namespace="test")
        assert backend.set.await_count == 2

    @pytest.mark.asyncio
    async def test_set_embedding_failure_is_noop(self):
        from ecommerce_ops.memory.llm_cache import SemanticLLMCache

        backend = AsyncMock()
        backend.set = AsyncMock()
        embedder = AsyncMock()
        embedder.embed = AsyncMock(side_effect=RuntimeError("no embedder"))

        cache = SemanticLLMCache(backend=backend, embedder=embedder)
        await cache.set("some prompt", {"decision": "approve"}, namespace="test")
        backend.set.assert_not_called()

    @pytest.mark.asyncio
    async def test_index_bounded_to_max_entries(self):
        from ecommerce_ops.memory.llm_cache import SemanticLLMCache

        class StatefulBackend:
            def __init__(self):
                self.store = {}

            async def get(self, key):
                return self.store.get(key)

            async def set(self, key, value, ttl=3600):
                self.store[key] = value
                return True

        backend = StatefulBackend()
        embedder = AsyncMock()
        embedder.embed = AsyncMock(return_value=[1.0, 0.0, 0.0])

        cache = SemanticLLMCache(backend=backend, embedder=embedder, max_entries=5)
        for i in range(10):
            await cache.set(f"prompt-{i}", {"i": i}, namespace="test")

        index = await backend.get("llm_semantic:index")
        assert len(index) == 5
