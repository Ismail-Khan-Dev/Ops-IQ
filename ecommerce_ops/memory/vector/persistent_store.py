"""
Persistent Vector Store
PostgreSQL/pgvector-backed ORM store for agent memory, acting as the
canonical ``VectorStore`` implementation.

Design notes:
- Embeddings are persisted as JSON in the ``embedding`` text column so
  retrieval behaves identically on PostgreSQL and SQLite (tests run on
  SQLite, production on pgvector/Postgres). The ``embedding_vec`` pgvector
  column is maintained for a future native-ANN path; cosine ranking happens
  in Python over a bounded, filtered candidate set.
- Importance is stored as the float weight used by ``MemoryEntry``
  (LOW=0.25, MEDIUM=0.5, HIGH=0.75, CRITICAL=1.0) — no schema change was
  needed; it round-trips to the enum on read.
- Fields with no dedicated column (tags, user_id, source, expiry,
  compression, parent_id) are carried inside ``metadata_json`` under
  reserved keys so the existing schema is reused as-is.
"""

import json
import logging
import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

import numpy as np
import sqlalchemy as sa
from pgvector.sqlalchemy import Vector
from sqlalchemy import JSON, Column, DateTime, Float, Index, String, Text, Uuid
from sqlalchemy.dialects.postgresql import JSONB

from ecommerce_ops.memory.vector.embeddings import EmbeddingService, embedding_service
from ecommerce_ops.memory.vector.models import (
    MemoryEntry,
    MemoryImportance,
    MemoryQuery,
    MemorySearchResult,
    MemoryStats,
    MemoryType,
)
from ecommerce_ops.models import Base, async_session_factory
from ecommerce_ops.utils import utc_now

logger = logging.getLogger("ecommerce_ops.memory.vector.persistent")

# Default embedding dimension matching the vector provider (see embeddings.py).
EMBEDDING_DIMENSIONS = 1536

_IMPORTANCE_WEIGHT: Dict[MemoryImportance, float] = {
    MemoryImportance.LOW: 0.25,
    MemoryImportance.MEDIUM: 0.5,
    MemoryImportance.HIGH: 0.75,
    MemoryImportance.CRITICAL: 1.0,
}
_WEIGHT_TO_IMPORTANCE: Dict[float, MemoryImportance] = {
    weight: level for level, weight in _IMPORTANCE_WEIGHT.items()
}

_METADATA_EXTRA_KEYS = (
    "tags",
    "user_id",
    "source",
    "expiry",
    "compressed",
    "parent_id",
)

SIMILARITY_WEIGHT = 0.6
RECENCY_WEIGHT = 0.2
IMPORTANCE_WEIGHT_FACTOR = 0.2


class VectorMemory(Base):
    """Persistent vector memory entry in PostgreSQL with pgvector."""

    __tablename__ = "vector_memories"

    id = Column(Uuid, primary_key=True, default=uuid.uuid4)
    content = Column(Text, nullable=False)
    memory_type = Column(String(50), nullable=False, index=True)
    importance = Column(Float, default=0.5, nullable=False)
    embedding = Column(Text, nullable=True)  # JSON-serialized list (portable fallback)
    embedding_vec = Column(
        Vector(EMBEDDING_DIMENSIONS).with_variant(Text(), "sqlite"),
        nullable=True,
    )
    metadata_json = Column(JSONB().with_variant(JSON(), "sqlite"), default=dict)
    session_id = Column(String(100), index=True, nullable=True)
    agent_id = Column(String(100), index=True, nullable=True)
    created_at = Column(DateTime, default=utc_now, nullable=False)
    accessed_at = Column(DateTime, default=utc_now, nullable=False)
    access_count = Column(Float, default=0)
    last_decay_at = Column(DateTime, default=utc_now)

    __table_args__ = (
        Index("idx_vector_memories_importance", "importance"),
        Index("idx_vector_memories_created", "created_at"),
        Index("idx_vector_memories_agent", "agent_id"),
        Index(
            "ix_vector_memories_embedding_vec",
            "embedding_vec",
            postgresql_using="ivfflat",
            postgresql_ops={"embedding_vec": "vector_cosine_ops"},
        ),
    )

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": str(self.id),
            "content": self.content,
            "memory_type": self.memory_type,
            "importance": self.importance,
            "metadata": self.metadata_json or {},
            "session_id": self.session_id,
            "agent_id": self.agent_id,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "accessed_at": self.accessed_at.isoformat() if self.accessed_at else None,
            "access_count": self.access_count,
        }


@dataclass
class _ExtraFields:
    tags: List[str]
    user_id: Optional[str]
    source: Optional[str]
    expiry: Optional[datetime]
    is_compressed: bool
    parent_id: Optional[str]


def _split_metadata(metadata: Dict[str, Any]) -> tuple[Dict[str, Any], _ExtraFields]:
    """Separate reserved extra fields from the free-form metadata dict."""
    data = dict(metadata)
    return (
        data,
        _ExtraFields(
            tags=list(data.pop("tags", []) or []),
            user_id=data.pop("user_id", None),
            source=data.pop("source", None),
            expiry=data.pop("expiry", None),
            is_compressed=bool(data.pop("compressed", False)),
            parent_id=data.pop("parent_id", None),
        ),
    )


def _merge_metadata(metadata: Dict[str, Any], entry: MemoryEntry) -> Dict[str, Any]:
    """Fold MemoryEntry extra fields back into the metadata dict."""
    data = dict(metadata)
    if entry.tags:
        data["tags"] = list(entry.tags)
    if entry.user_id:
        data["user_id"] = entry.user_id
    if entry.source:
        data["source"] = entry.source
    if entry.expiry:
        data["expiry"] = entry.expiry.isoformat()
    if entry.is_compressed:
        data["compressed"] = True
    if entry.parent_id:
        data["parent_id"] = entry.parent_id
    return data


def _parse_uuid(value: str) -> Optional[uuid.UUID]:
    try:
        return uuid.UUID(str(value))
    except (ValueError, AttributeError, TypeError):
        return None


def _serialize_embedding(embedding: Optional[List[float]]) -> Optional[str]:
    if embedding is None:
        return None
    return json.dumps(embedding)


def _deserialize_embedding(raw: Optional[str]) -> Optional[List[float]]:
    if not raw:
        return None
    try:
        return json.loads(raw)
    except (ValueError, TypeError):
        return None


def _importance_to_weight(importance: MemoryImportance) -> float:
    return _IMPORTANCE_WEIGHT.get(importance, 0.5)


def _weight_to_importance(weight: float) -> MemoryImportance:
    closest = min(_WEIGHT_TO_IMPORTANCE, key=lambda w: abs(w - weight))
    return _WEIGHT_TO_IMPORTANCE[closest]


def _cosine_similarity(a: List[float], b: List[float]) -> float:
    if not a or not b or len(a) != len(b):
        return 0.0
    va = np.asarray(a, dtype=np.float64)
    vb = np.asarray(b, dtype=np.float64)
    dot = float(np.dot(va, vb))
    norm_a = float(np.linalg.norm(va))
    norm_b = float(np.linalg.norm(vb))
    if norm_a == 0 or norm_b == 0:
        return 0.0
    return dot / (norm_a * norm_b)


def _calculate_score(entry: MemoryEntry, similarity: float) -> float:
    return (
        similarity * SIMILARITY_WEIGHT
        + entry.recency_score * RECENCY_WEIGHT
        + entry.importance_weight * IMPORTANCE_WEIGHT_FACTOR
    )


def _row_to_entry(row: VectorMemory) -> MemoryEntry:
    metadata, extra = _split_metadata(row.metadata_json or {})
    try:
        memory_type = MemoryType(row.memory_type)
    except ValueError:
        memory_type = MemoryType.EPISODIC
    return MemoryEntry(
        id=str(row.id),
        memory_type=memory_type,
        content=row.content,
        embedding=_deserialize_embedding(row.embedding),
        metadata=metadata,
        importance=_weight_to_importance(row.importance),
        agent_name=row.agent_id,
        session_id=row.session_id,
        user_id=extra.user_id,
        tags=extra.tags,
        source=extra.source,
        created_at=row.created_at or utc_now(),
        last_accessed=row.accessed_at,
        access_count=int(row.access_count or 0),
        expiry=extra.expiry,
        is_compressed=extra.is_compressed,
        parent_id=extra.parent_id,
    )


class PersistentVectorStore:
    """DB-backed implementation of the vector memory store interface."""

    def __init__(
        self,
        session_factory: Any = None,
        embedding_service_: Optional[EmbeddingService] = None,
    ):
        self.session_factory = session_factory or async_session_factory
        self.embedding_service = embedding_service_ or embedding_service

    # ── Write operations ────────────────────────────────────

    async def add(self, entry: MemoryEntry) -> str:
        """Persist a memory entry, generating an embedding if missing."""
        if entry.embedding is None:
            try:
                entry.embedding = await self.embedding_service.embed(entry.content)
            except Exception as e:  # pragma: no cover - no real provider configured
                logger.warning("Embedding unavailable for memory %s: %s", entry.id, e)
                entry.embedding = None

        parsed_id = _parse_uuid(entry.id)
        if parsed_id is None:
            parsed_id = uuid.uuid4()
        row = VectorMemory(
            id=parsed_id,
            content=entry.content,
            memory_type=entry.memory_type.value,
            importance=_importance_to_weight(entry.importance),
            embedding=_serialize_embedding(entry.embedding),
            embedding_vec=None,
            metadata_json=_merge_metadata(dict(entry.metadata or {}), entry),
            session_id=entry.session_id,
            agent_id=entry.agent_name,
            created_at=entry.created_at,
            accessed_at=entry.last_accessed,
            access_count=entry.access_count,
        )
        async with self.session_factory() as session:
            session.add(row)
            await session.commit()

        entry.id = str(row.id)
        logger.debug("Added memory %s (type=%s)", entry.id, entry.memory_type)
        return entry.id

    async def add_batch(self, entries: List[MemoryEntry]) -> List[str]:
        ids = []
        for entry in entries:
            entry_id = await self.add(entry)
            ids.append(entry_id)
        return ids

    async def update(self, entry: MemoryEntry) -> bool:
        parsed_id = _parse_uuid(entry.id)
        if parsed_id is None:
            return False
        async with self.session_factory() as session:
            row = await session.get(VectorMemory, parsed_id)
            if row is None:
                return False
            if row.content != entry.content:
                try:
                    entry.embedding = await self.embedding_service.embed(entry.content)
                except Exception as e:  # pragma: no cover - no real provider configured
                    logger.warning("Embedding unavailable on update %s: %s", entry.id, e)
                    entry.embedding = None
            row.content = entry.content
            row.memory_type = entry.memory_type.value
            row.importance = _importance_to_weight(entry.importance)
            row.embedding = _serialize_embedding(entry.embedding)
            row.embedding_vec = None
            row.metadata_json = _merge_metadata(dict(entry.metadata or {}), entry)
            row.session_id = entry.session_id
            row.agent_id = entry.agent_name
            await session.commit()
        return True

    async def delete(self, memory_id: str) -> bool:
        parsed_id = _parse_uuid(memory_id)
        if parsed_id is None:
            return False
        async with self.session_factory() as session:
            row = await session.get(VectorMemory, parsed_id)
            if row is None:
                return False
            await session.delete(row)
            await session.commit()
        return True

    async def delete_expired(self) -> int:
        now = utc_now()
        entries = await self._filter_memories(MemoryQuery(query="", include_expired=True))
        deleted = 0
        for entry in entries:
            if entry.expiry and entry.expiry < now and await self.delete(entry.id):
                deleted += 1
        if deleted:
            logger.info("Deleted %d expired memories", deleted)
        return deleted

    # ── Read operations ─────────────────────────────────────

    async def get(self, memory_id: str) -> Optional[MemoryEntry]:
        parsed_id = _parse_uuid(memory_id)
        if parsed_id is None:
            return None
        async with self.session_factory() as session:
            row = await session.get(VectorMemory, parsed_id)
            if row is None:
                return None
            row.accessed_at = utc_now()
            row.access_count = (row.access_count or 0) + 1
            await session.commit()
            return _row_to_entry(row)

    async def search(self, query: MemoryQuery) -> List[MemorySearchResult]:
        if query.query_embedding is None and query.query:
            try:
                query.query_embedding = await self.embedding_service.embed(query.query)
            except Exception as e:  # pragma: no cover - no real provider configured
                logger.warning("Embedding unavailable for search: %s", e)

        candidates = await self._filter_memories(query)
        if not candidates:
            return []

        results = []
        for entry in candidates:
            if entry.embedding is None:
                continue
            similarity = _cosine_similarity(query.query_embedding or [], entry.embedding)
            if similarity and similarity >= query.min_similarity:
                results.append(
                    MemorySearchResult(
                        entry=entry,
                        similarity=similarity,
                        rank=0,
                        score=_calculate_score(entry, similarity),
                        explanation=(
                            f"similarity={similarity:.3f}, recency={entry.recency_score:.3f}"
                        ),
                    )
                )

        results.sort(key=lambda r: r.score, reverse=True)
        for i, result in enumerate(results[: query.max_results]):
            result.rank = i + 1
        return results[: query.max_results]

    async def get_similar_memories(
        self,
        memory_id: str,
        max_results: int = 5,
        min_similarity: float = 0.5,
    ) -> List[MemorySearchResult]:
        entry = await self.get(memory_id)
        if not entry or entry.embedding is None:
            return []
        query = MemoryQuery(
            query=entry.content,
            query_embedding=entry.embedding,
            max_results=max_results + 1,
            min_similarity=min_similarity,
        )
        results = await self.search(query)
        return [r for r in results if r.entry.id != memory_id][:max_results]

    async def _filter_memories(self, query: MemoryQuery) -> List[MemoryEntry]:
        """Return stored MemoryEntry objects matching the query filters."""
        stmt = sa.select(VectorMemory)
        if query.memory_type:
            stmt = stmt.where(VectorMemory.memory_type == query.memory_type.value)
        if query.agent_name:
            stmt = stmt.where(VectorMemory.agent_id == query.agent_name)
        if query.session_id:
            stmt = stmt.where(VectorMemory.session_id == query.session_id)
        if query.min_importance:
            stmt = stmt.where(
                VectorMemory.importance >= _importance_to_weight(query.min_importance)
            )
        if query.time_window_hours:
            cutoff = utc_now() - timedelta(hours=query.time_window_hours)
            stmt = stmt.where(VectorMemory.created_at >= cutoff)
        stmt = stmt.order_by(VectorMemory.created_at.desc()).limit(1000)

        async with self.session_factory() as session:
            rows = (await session.execute(stmt)).scalars().all()

        entries = [_row_to_entry(row) for row in rows]

        # Filters that are not column-backed are applied in Python.
        if query.user_id:
            entries = [e for e in entries if e.user_id == query.user_id]
        if query.tags:
            entries = [e for e in entries if any(t in e.tags for t in query.tags)]
        if not query.include_expired:
            entries = [e for e in entries if not e.is_expired]
        return entries

    async def get_stats(self) -> MemoryStats:
        async with self.session_factory() as session:
            total = await session.scalar(sa.select(sa.func.count()).select_from(VectorMemory)) or 0
            type_rows = (
                await session.execute(
                    sa.select(VectorMemory.memory_type, sa.func.count()).group_by(
                        VectorMemory.memory_type
                    )
                )
            ).all()
            importance_rows = (
                await session.execute(
                    sa.select(VectorMemory.importance, sa.func.count()).group_by(
                        VectorMemory.importance
                    )
                )
            ).all()
            agent_rows = (
                await session.execute(
                    sa.select(VectorMemory.agent_id, sa.func.count()).group_by(
                        VectorMemory.agent_id
                    )
                )
            ).all()
            avg_access = (
                await session.scalar(sa.select(sa.func.avg(VectorMemory.access_count))) or 0
            )

        return MemoryStats(
            total_memories=int(total),
            memories_by_type={r[0]: int(r[1]) for r in type_rows if r[0]},
            memories_by_importance={
                _weight_to_importance(r[0]).value: int(r[1])
                for r in importance_rows
                if r[0] is not None
            },
            memories_by_agent={r[0]: int(r[1]) for r in agent_rows if r[0]},
            avg_access_count=round(float(avg_access), 2),
            total_embeddings=int(total),
        )


# Canonical store instance (replaces the in-memory store singleton).
vector_store = PersistentVectorStore()
