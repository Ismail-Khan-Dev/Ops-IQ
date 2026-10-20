"""
Vector Store with Semantic Search
In-memory vector store with cosine similarity search.
"""

import logging
from datetime import timedelta
from typing import Any, Dict, List, Optional

import numpy as np

from ecommerce_ops.memory.vector.embeddings import EmbeddingService
from ecommerce_ops.memory.vector.models import (
    MemoryEntry,
    MemoryImportance,
    MemoryQuery,
    MemorySearchResult,
    MemoryStats,
)
from ecommerce_ops.utils import utc_now

logger = logging.getLogger("ecommerce_ops.memory.vector.store")


class VectorStore:
    """In-memory vector store with semantic search."""

    def __init__(
        self,
        embedding_service: EmbeddingService = None,
        max_memories: int = 10000,
    ):
        self.embedding_service = embedding_service or embedding_service
        self.max_memories = max_memories
        self._memories: Dict[str, MemoryEntry] = {}
        self._embeddings: Dict[str, np.ndarray] = {}
        self._index: Optional[Any] = None  # FAISS index if available

    async def add(self, entry: MemoryEntry) -> str:
        """Add a memory entry to the store."""
        # Generate embedding if not provided
        if entry.embedding is None:
            embedding = await self.embedding_service.embed(entry.content)
            entry.embedding = embedding

        # Store
        self._memories[entry.id] = entry
        self._embeddings[entry.id] = np.array(entry.embedding, dtype=np.float32)

        # Update index
        self._rebuild_index()

        logger.debug("Added memory %s (type=%s)", entry.id, entry.memory_type)
        return entry.id

    async def add_batch(self, entries: List[MemoryEntry]) -> List[str]:
        """Add multiple memory entries."""
        ids = []
        for entry in entries:
            entry_id = await self.add(entry)
            ids.append(entry_id)
        return ids

    async def search(
        self,
        query: MemoryQuery,
    ) -> List[MemorySearchResult]:
        """Search for similar memories using semantic similarity."""
        # Generate query embedding
        if query.query_embedding is None:
            query_embedding = await self.embedding_service.embed(query.query)
        else:
            query_embedding = np.array(query.query_embedding, dtype=np.float32)

        # Filter memories
        candidates = self._filter_memories(query)

        if not candidates:
            return []

        # Calculate similarities
        results = []
        for entry in candidates:
            if entry.id not in self._embeddings:
                continue

            memory_embedding = self._embeddings[entry.id]
            similarity = self._cosine_similarity(query_embedding, memory_embedding)

            if similarity >= query.min_similarity:
                # Calculate combined score
                score = self._calculate_score(entry, similarity)

                results.append(
                    MemorySearchResult(
                        entry=entry,
                        similarity=similarity,
                        rank=0,  # Will be set after sorting
                        score=score,
                        explanation=f"similarity={similarity:.3f}, recency={entry.recency_score:.3f}",
                    )
                )

        # Sort by score
        results.sort(key=lambda x: x.score, reverse=True)

        # Set ranks and limit
        for i, result in enumerate(results[: query.max_results]):
            result.rank = i + 1

        return results[: query.max_results]

    async def get(self, memory_id: str) -> Optional[MemoryEntry]:
        """Get a memory by ID."""
        entry = self._memories.get(memory_id)
        if entry:
            entry.last_accessed = utc_now()
            entry.access_count += 1
        return entry

    async def update(self, entry: MemoryEntry) -> bool:
        """Update an existing memory entry."""
        if entry.id not in self._memories:
            return False

        # Regenerate embedding if content changed
        old_entry = self._memories[entry.id]
        if old_entry.content != entry.content:
            embedding = await self.embedding_service.embed(entry.content)
            entry.embedding = embedding
            self._embeddings[entry.id] = np.array(embedding, dtype=np.float32)

        self._memories[entry.id] = entry
        self._rebuild_index()
        return True

    async def delete(self, memory_id: str) -> bool:
        """Delete a memory entry."""
        if memory_id not in self._memories:
            return False

        del self._memories[memory_id]
        if memory_id in self._embeddings:
            del self._embeddings[memory_id]

        self._rebuild_index()
        return True

    async def delete_expired(self) -> int:
        """Delete expired memories."""
        expired_ids = [id for id, entry in self._memories.items() if entry.is_expired]

        for id in expired_ids:
            await self.delete(id)

        logger.info("Deleted %d expired memories", len(expired_ids))
        return len(expired_ids)

    def get_stats(self) -> MemoryStats:
        """Get memory store statistics."""
        memories = list(self._memories.values())

        # Count by type
        by_type: Dict[str, int] = {}
        for entry in memories:
            type_name = entry.memory_type.value
            by_type[type_name] = by_type.get(type_name, 0) + 1

        # Count by importance
        by_importance: Dict[str, int] = {}
        for entry in memories:
            imp_name = entry.importance.value
            by_importance[imp_name] = by_importance.get(imp_name, 0) + 1

        # Count by agent
        by_agent: Dict[str, int] = {}
        for entry in memories:
            if entry.agent_name:
                by_agent[entry.agent_name] = by_agent.get(entry.agent_name, 0) + 1

        # Average access count
        avg_access = sum(e.access_count for e in memories) / len(memories) if memories else 0

        return MemoryStats(
            total_memories=len(memories),
            memories_by_type=by_type,
            memories_by_importance=by_importance,
            memories_by_agent=by_agent,
            avg_access_count=avg_access,
            total_embeddings=len(self._embeddings),
        )

    def _filter_memories(self, query: MemoryQuery) -> List[MemoryEntry]:
        """Filter memories based on query criteria."""
        candidates = list(self._memories.values())

        # Filter by memory type
        if query.memory_type:
            candidates = [e for e in candidates if e.memory_type == query.memory_type]

        # Filter by agent
        if query.agent_name:
            candidates = [e for e in candidates if e.agent_name == query.agent_name]

        # Filter by session
        if query.session_id:
            candidates = [e for e in candidates if e.session_id == query.session_id]

        # Filter by user
        if query.user_id:
            candidates = [e for e in candidates if e.user_id == query.user_id]

        # Filter by tags
        if query.tags:
            candidates = [e for e in candidates if any(tag in e.tags for tag in query.tags)]

        # Filter by importance
        if query.min_importance:
            importance_order = [
                MemoryImportance.LOW,
                MemoryImportance.MEDIUM,
                MemoryImportance.HIGH,
                MemoryImportance.CRITICAL,
            ]
            min_idx = importance_order.index(query.min_importance)
            candidates = [e for e in candidates if importance_order.index(e.importance) >= min_idx]

        # Filter by expiry
        if not query.include_expired:
            candidates = [e for e in candidates if not e.is_expired]

        # Filter by time window
        if query.time_window_hours:
            cutoff = utc_now() - timedelta(hours=query.time_window_hours)
            candidates = [e for e in candidates if e.created_at >= cutoff]

        return candidates

    def _calculate_score(self, entry: MemoryEntry, similarity: float) -> float:
        """Calculate combined score for ranking."""
        # Weights
        SIMILARITY_WEIGHT = 0.6
        RECENCY_WEIGHT = 0.2
        IMPORTANCE_WEIGHT = 0.2

        score = (
            similarity * SIMILARITY_WEIGHT
            + entry.recency_score * RECENCY_WEIGHT
            + entry.importance_weight * IMPORTANCE_WEIGHT
        )

        return score

    def _cosine_similarity(self, a: np.ndarray, b: np.ndarray) -> float:
        """Calculate cosine similarity between two vectors."""
        dot_product = np.dot(a, b)
        norm_a = np.linalg.norm(a)
        norm_b = np.linalg.norm(b)

        if norm_a == 0 or norm_b == 0:
            return 0.0

        return float(dot_product / (norm_a * norm_b))

    def _rebuild_index(self):
        """Rebuild vector index."""
        # Simple linear scan for now
        # In production, use FAISS or similar
        pass

    async def get_similar_memories(
        self,
        memory_id: str,
        max_results: int = 5,
        min_similarity: float = 0.5,
    ) -> List[MemorySearchResult]:
        """Get memories similar to a given memory."""
        entry = self._memories.get(memory_id)
        if not entry or entry.embedding is None:
            return []

        query = MemoryQuery(
            query=entry.content,
            query_embedding=entry.embedding,
            max_results=max_results + 1,  # +1 to exclude self
            min_similarity=min_similarity,
        )

        results = await self.search(query)
        return [r for r in results if r.entry.id != memory_id][:max_results]


# Singleton
vector_store = VectorStore()
