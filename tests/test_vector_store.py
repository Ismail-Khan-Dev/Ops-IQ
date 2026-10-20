import os

os.environ["ENV"] = "testing"
os.environ["DATABASE_URL"] = "sqlite+aiosqlite://"
os.environ["API_KEY"] = "test-key"
os.environ["DEEPSEEK_API_KEY"] = "sk-test-key"

import math
import uuid
from datetime import timedelta

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from ecommerce_ops.memory.vector.models import (
    MemoryEntry,
    MemoryImportance,
    MemoryQuery,
    MemoryType,
)
from ecommerce_ops.memory.vector.persistent_store import PersistentVectorStore, VectorMemory
from ecommerce_ops.models import Base
from ecommerce_ops.utils import utc_now


class TokenEmbedder:
    """Deterministic bag-of-words embedder: overlapping tokens yield high cosine.

    Unlike the production MockEmbeddingProvider (random vectors), this one is
    semantically coherent so search tests can assert real ranking.
    """

    DIM = 1536

    async def embed(self, text: str) -> list[float]:
        import hashlib

        vec = [0.0] * self.DIM
        for token in text.lower().split():
            idx = int(hashlib.sha256(token.encode()).hexdigest(), 16) % self.DIM
            vec[idx] += 1.0
        norm = math.sqrt(sum(v * v for v in vec))
        return [v / norm for v in vec] if norm else vec


@pytest_asyncio.fixture
async def store():
    """Fresh SQLite engine + store with a deterministic test embedder."""
    engine = create_async_engine("sqlite+aiosqlite://", echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    session_factory = async_sessionmaker(engine, expire_on_commit=False)

    vs = PersistentVectorStore(session_factory=session_factory, embedding_service_=TokenEmbedder())
    yield vs
    await engine.dispose()


def make_entry(
    content="A product recommendation based on past purchases",
    memory_type=MemoryType.EPISODIC,
    importance=MemoryImportance.MEDIUM,
    agent_name="ReviewsAgent",
    tags=None,
    **kwargs,
) -> MemoryEntry:
    return MemoryEntry(
        id=str(uuid.uuid4()),
        memory_type=memory_type,
        content=content,
        importance=importance,
        agent_name=agent_name,
        session_id=kwargs.pop("session_id", None),
        user_id=kwargs.pop("user_id", None),
        tags=tags or [],
        metadata=kwargs.pop("metadata", {}),
        source=kwargs.pop("source", None),
        expiry=kwargs.pop("expiry", None),
        created_at=kwargs.pop("created_at", utc_now()),
        **kwargs,
    )


class TestPersistentVectorStoreWrites:
    @pytest.mark.asyncio
    async def test_add_persists_and_returns_id(self, store):
        entry = make_entry(content="Persist this memory")
        entry_id = await store.add(entry)

        assert entry_id == entry.id
        got = await store.get(entry_id)
        assert got is not None
        assert got.content == "Persist this memory"
        assert got.embedding is not None

    @pytest.mark.asyncio
    async def test_add_accepts_custom_id(self, store):
        custom = str(uuid.uuid4())
        entry = make_entry(content="Custom id memory", session_id="sess")
        entry.id = custom
        await store.add(entry)
        got = await store.get(custom)
        assert got.id == custom

    @pytest.mark.asyncio
    async def test_add_roundtrips_extra_fields(self, store):
        entry = make_entry(
            content="Memory with extras",
            user_id="user-1",
            tags=["learned", "knowledge"],
            source="pipeline",
            expiry=utc_now() + timedelta(hours=5),
            metadata={"confidence": 0.9},
        )
        entry.is_compressed = True
        entry.parent_id = "consol-1"
        await store.add(entry)

        got = await store.get(entry.id)
        assert got.user_id == "user-1"
        assert set(got.tags) == {"learned", "knowledge"}
        assert got.source == "pipeline"
        assert got.is_compressed is True
        assert got.parent_id == "consol-1"
        assert got.metadata["confidence"] == 0.9

    @pytest.mark.asyncio
    async def test_update_content_and_reembed(self, store):
        entry = make_entry(content="Original content")
        await store.add(entry)
        entry.content = "Updated content"
        ok = await store.update(entry)
        assert ok is True

        got = await store.get(entry.id)
        assert got.content == "Updated content"
        assert got.embedding is not None

    @pytest.mark.asyncio
    async def test_update_missing_returns_false(self, store):
        entry = make_entry(content="nope")
        entry.id = str(uuid.uuid4())
        ok = await store.update(entry)
        assert ok is False

    @pytest.mark.asyncio
    async def test_delete_memory(self, store):
        entry = make_entry(content="Delete me")
        await store.add(entry)
        assert await store.delete(entry.id) is True
        assert await store.get(entry.id) is None
        assert await store.delete(entry.id) is False

    @pytest.mark.asyncio
    async def test_delete_expired(self, store):
        expired = make_entry(content="expired", expiry=utc_now() - timedelta(minutes=5))
        fresh = make_entry(content="fresh", expiry=utc_now() + timedelta(days=1))
        no_ttl = make_entry(content="no TTL")
        await store.add(expired)
        await store.add(fresh)
        await store.add(no_ttl)

        assert await store.delete_expired() == 1
        assert await store.get(expired.id) is None
        assert await store.get(fresh.id) is not None
        assert await store.get(no_ttl.id) is not None


class TestPersistentVectorStoreReads:
    @pytest.mark.asyncio
    async def test_get_nonexistent_returns_none(self, store):
        assert await store.get("missing-id") is None
        assert await store.get(str(uuid.uuid4())) is None

    @pytest.mark.asyncio
    async def test_get_increments_access(self, store):
        entry = make_entry(content="tracked")
        await store.add(entry)
        await store.get(entry.id)
        got = await store.get(entry.id)
        assert got.access_count == 2

    @pytest.mark.asyncio
    async def test_search_returns_similar(self, store):
        await store.add(
            make_entry(
                content="happy customer loves fast shipping",
                agent_name="ReviewsAgent",
                tags=["review"],
            )
        )
        await store.add(
            make_entry(content="unrelated weather forecast", agent_name="OtherAgent", tags=["misc"])
        )
        results = await store.search(
            MemoryQuery(query="happy shipping review", max_results=5, min_similarity=0.1)
        )
        assert len(results) >= 1
        assert results[0].entry.content == "happy customer loves fast shipping"
        assert results[0].rank == 1

    @pytest.mark.asyncio
    async def test_search_filters_by_agent(self, store):
        await store.add(make_entry(content="inventory restock needed", agent_name="InventoryAgent"))
        await store.add(
            make_entry(content="inventory forecast is bright", agent_name="MarketingAgent")
        )
        results = await store.search(
            MemoryQuery(
                query="inventory",
                agent_name="InventoryAgent",
                max_results=5,
                min_similarity=0.0,
            )
        )
        assert all(r.entry.agent_name == "InventoryAgent" for r in results)
        assert len(results) == 1

    @pytest.mark.asyncio
    async def test_search_filters_by_tags_and_user(self, store):
        await store.add(
            make_entry(
                content="pricing experiment result",
                tags=["pricing"],
                user_id="u1",
                agent_name="PricingAgent",
            )
        )
        await store.add(
            make_entry(
                content="pricing experiment result",
                tags=["pricing"],
                user_id="u2",
                agent_name="PricingAgent",
            )
        )
        results = await store.search(
            MemoryQuery(
                query="pricing",
                tags=["pricing"],
                user_id="u1",
                max_results=5,
                min_similarity=0.0,
            )
        )
        assert len(results) == 1
        assert results[0].entry.user_id == "u1"

    @pytest.mark.asyncio
    async def test_search_excludes_expired_by_default(self, store):
        await store.add(
            make_entry(content="expired memory content", expiry=utc_now() - timedelta(minutes=1))
        )
        results = await store.search(
            MemoryQuery(query="expired", max_results=5, min_similarity=0.0)
        )
        assert len(results) == 0

        results = await store.search(
            MemoryQuery(query="expired", max_results=5, min_similarity=0.0, include_expired=True)
        )
        assert len(results) == 1

    @pytest.mark.asyncio
    async def test_get_similar_memories_excludes_self(self, store):
        base = make_entry(content="fraud flag on high value order", agent_name="FraudAgent")
        other = make_entry(content="fraud pattern: rapid reorder", agent_name="FraudAgent")
        await store.add(base)
        await store.add(other)
        results = await store.get_similar_memories(base.id, max_results=5, min_similarity=0.0)
        assert len(results) == 1
        assert results[0].entry.id == other.id
        assert results[0].entry.id != base.id


class TestPersistentVectorStoreStats:
    @pytest.mark.asyncio
    async def test_get_stats_empty(self, store):
        stats = await store.get_stats()
        assert stats.total_memories == 0
        assert stats.memories_by_type == {}
        assert stats.memories_by_importance == {}

    @pytest.mark.asyncio
    async def test_get_stats_aggregates(self, store):
        await store.add(
            make_entry(
                content="episodic A",
                memory_type=MemoryType.EPISODIC,
                importance=MemoryImportance.HIGH,
                agent_name="FraudAgent",
            )
        )
        await store.add(
            make_entry(
                content="episodic B",
                memory_type=MemoryType.EPISODIC,
                importance=MemoryImportance.HIGH,
                agent_name="FraudAgent",
            )
        )
        await store.add(
            make_entry(
                content="semantic C",
                memory_type=MemoryType.SEMANTIC,
                importance=MemoryImportance.LOW,
                agent_name="InventoryAgent",
            )
        )

        stats = await store.get_stats()
        assert stats.total_memories == 3
        assert stats.memories_by_type == {"episodic": 2, "semantic": 1}
        assert stats.memories_by_importance == {"high": 2, "low": 1}
        assert stats.memories_by_agent == {"FraudAgent": 2, "InventoryAgent": 1}
        assert stats.total_embeddings == 3

    @pytest.mark.asyncio
    async def test_filter_memories_min_importance(self, store):
        await store.add(make_entry(content="low", importance=MemoryImportance.LOW))
        await store.add(make_entry(content="high", importance=MemoryImportance.HIGH))
        entries = await store._filter_memories(
            MemoryQuery(query="", min_importance=MemoryImportance.HIGH)
        )
        assert len(entries) == 1
        assert entries[0].content == "high"


def test_model_table_exists():
    assert VectorMemory.__tablename__ == "vector_memories"
