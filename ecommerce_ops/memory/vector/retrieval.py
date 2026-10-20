"""
Memory Retrieval and Consolidation
High-level memory operations with consolidation.
"""

import logging
import uuid
from datetime import timedelta
from typing import Any, Dict, List, Optional

from ecommerce_ops.memory.vector.models import (
    MemoryConsolidation,
    MemoryEntry,
    MemoryImportance,
    MemoryQuery,
    MemorySearchResult,
    MemoryType,
)
from ecommerce_ops.memory.vector.persistent_store import PersistentVectorStore, vector_store
from ecommerce_ops.utils import utc_now

logger = logging.getLogger("ecommerce_ops.memory.vector.retrieval")


class MemoryRetrievalService:
    """High-level memory operations with retrieval and consolidation."""

    def __init__(
        self,
        store: PersistentVectorStore = None,
        consolidation_threshold: int = 50,
    ):
        self.store = store or vector_store
        self.consolidation_threshold = consolidation_threshold
        self._consolidations: Dict[str, MemoryConsolidation] = {}

    async def remember(
        self,
        content: str,
        memory_type: MemoryType = MemoryType.EPISODIC,
        importance: MemoryImportance = MemoryImportance.MEDIUM,
        agent_name: Optional[str] = None,
        session_id: Optional[str] = None,
        user_id: Optional[str] = None,
        tags: Optional[List[str]] = None,
        metadata: Optional[Dict[str, Any]] = None,
        source: Optional[str] = None,
    ) -> MemoryEntry:
        """Store a new memory."""
        entry = MemoryEntry(
            id=str(uuid.uuid4()),
            memory_type=memory_type,
            content=content,
            importance=importance,
            agent_name=agent_name,
            session_id=session_id,
            user_id=user_id,
            tags=tags or [],
            metadata=metadata or {},
            source=source,
        )

        await self.store.add(entry)

        logger.debug(
            "Stored memory %s (type=%s, agent=%s)",
            entry.id,
            memory_type.value,
            agent_name,
        )

        return entry

    async def recall(
        self,
        query: str,
        memory_type: Optional[MemoryType] = None,
        agent_name: Optional[str] = None,
        session_id: Optional[str] = None,
        user_id: Optional[str] = None,
        max_results: int = 10,
        min_similarity: float = 0.7,
    ) -> List[MemorySearchResult]:
        """Recall memories matching a query."""
        memory_query = MemoryQuery(
            query=query,
            memory_type=memory_type,
            agent_name=agent_name,
            session_id=session_id,
            user_id=user_id,
            max_results=max_results,
            min_similarity=min_similarity,
        )

        results = await self.store.search(memory_query)

        logger.debug(
            "Recalled %d memories for query: %s",
            len(results),
            query[:50],
        )

        return results

    async def recall_recent(
        self,
        agent_name: Optional[str] = None,
        session_id: Optional[str] = None,
        hours: int = 24,
        max_results: int = 10,
    ) -> List[MemorySearchResult]:
        """Recall recent memories."""
        memory_query = MemoryQuery(
            query="",  # No semantic query, just time-based
            agent_name=agent_name,
            session_id=session_id,
            time_window_hours=hours,
            max_results=max_results,
            min_similarity=0.0,  # Skip similarity check
        )

        # Get recent memories sorted by creation time
        candidates = await self.store._filter_memories(memory_query)
        candidates.sort(key=lambda e: e.created_at, reverse=True)

        results = []
        for entry in candidates[:max_results]:
            results.append(
                MemorySearchResult(
                    entry=entry,
                    similarity=1.0,
                    rank=len(results) + 1,
                    score=entry.recency_score,
                    explanation=f"recent memory from {entry.created_at.isoformat()}",
                )
            )

        return results

    async def recall_by_importance(
        self,
        min_importance: MemoryImportance = MemoryImportance.HIGH,
        memory_type: Optional[MemoryType] = None,
        agent_name: Optional[str] = None,
        max_results: int = 10,
    ) -> List[MemorySearchResult]:
        """Recall memories by importance."""
        memory_query = MemoryQuery(
            query="",
            memory_type=memory_type,
            agent_name=agent_name,
            min_importance=min_importance,
            max_results=max_results,
            min_similarity=0.0,
        )

        candidates = await self.store._filter_memories(memory_query)
        candidates.sort(key=lambda e: e.importance_weight, reverse=True)

        results = []
        for entry in candidates[:max_results]:
            results.append(
                MemorySearchResult(
                    entry=entry,
                    similarity=1.0,
                    rank=len(results) + 1,
                    score=entry.importance_weight,
                    explanation=f"importance={entry.importance.value}",
                )
            )

        return results

    async def get_context_window(
        self,
        query: str,
        agent_name: Optional[str] = None,
        session_id: Optional[str] = None,
        max_tokens: int = 4000,
    ) -> str:
        """Get a context window of relevant memories for LLM input."""
        # Recall relevant memories
        results = await self.recall(
            query=query,
            agent_name=agent_name,
            session_id=session_id,
            max_results=20,
            min_similarity=0.6,
        )

        # Build context window
        context_parts = []
        current_tokens = 0

        for result in results:
            # Rough token estimation (1 token ≈ 4 chars)
            content_tokens = len(result.entry.content) // 4

            if current_tokens + content_tokens > max_tokens:
                break

            # Format memory
            memory_text = f"[{result.entry.memory_type.value}] {result.entry.content}"
            context_parts.append(memory_text)
            current_tokens += content_tokens

        return "\n".join(context_parts)

    async def consolidate_memories(
        self,
        memories: List[MemoryEntry],
        agent_name: Optional[str] = None,
    ) -> MemoryConsolidation:
        """Consolidate multiple memories into a summary."""
        if not memories:
            raise ValueError("No memories to consolidate")

        # Build consolidation
        contents = [m.content for m in memories]
        summary = self._create_summary(contents)
        key_points = self._extract_key_points(contents)

        consolidation = MemoryConsolidation(
            id=str(uuid.uuid4()),
            original_memories=[m.id for m in memories],
            consolidated_content="\n".join(contents),
            summary=summary,
            key_points=key_points,
            memory_type=MemoryType.SEMANTIC,
            importance=MemoryImportance.HIGH,
        )

        # Store consolidation
        self._consolidations[consolidation.id] = consolidation

        # Create consolidated memory entry
        await self.remember(
            content=f"Consolidated: {summary}",
            memory_type=MemoryType.SEMANTIC,
            importance=MemoryImportance.HIGH,
            agent_name=agent_name,
            tags=["consolidated"],
            metadata={
                "consolidation_id": consolidation.id,
                "original_count": len(memories),
                "key_points": key_points,
            },
        )

        # Mark original memories as compressed
        for memory in memories:
            memory.is_compressed = True
            memory.parent_id = consolidation.id
            await self.store.update(memory)

        logger.info(
            "Consolidated %d memories into %s",
            len(memories),
            consolidation.id,
        )

        return consolidation

    async def auto_consolidate(
        self,
        agent_name: Optional[str] = None,
        memory_type: Optional[MemoryType] = None,
    ) -> Optional[MemoryConsolidation]:
        """Automatically consolidate memories if threshold is reached."""
        # Get memories that haven't been consolidated
        query = MemoryQuery(
            query="",
            agent_name=agent_name,
            memory_type=memory_type,
            max_results=1000,
            min_similarity=0.0,
            include_expired=False,
        )

        candidates = await self.store._filter_memories(query)
        candidates = [m for m in candidates if not m.is_compressed]

        if len(candidates) < self.consolidation_threshold:
            return None

        # Sort by age (oldest first)
        candidates.sort(key=lambda m: m.created_at)

        # Consolidate oldest memories
        to_consolidate = candidates[: self.consolidation_threshold]

        return await self.consolidate_memories(to_consolidate, agent_name)

    async def forget(
        self,
        memory_id: str,
    ) -> bool:
        """Delete a memory."""
        return await self.store.delete(memory_id)

    async def forget_by_criteria(
        self,
        agent_name: Optional[str] = None,
        memory_type: Optional[MemoryType] = None,
        older_than_days: Optional[int] = None,
        importance_below: Optional[MemoryImportance] = None,
    ) -> int:
        """Delete memories by criteria."""
        query = MemoryQuery(
            query="",
            agent_name=agent_name,
            memory_type=memory_type,
            max_results=10000,
            min_similarity=0.0,
        )

        candidates = await self.store._filter_memories(query)

        # Apply additional filters
        if older_than_days:
            cutoff = utc_now() - timedelta(days=older_than_days)
            candidates = [m for m in candidates if m.created_at < cutoff]

        if importance_below:
            importance_order = [
                MemoryImportance.LOW,
                MemoryImportance.MEDIUM,
                MemoryImportance.HIGH,
                MemoryImportance.CRITICAL,
            ]
            max_idx = importance_order.index(importance_below)
            candidates = [m for m in candidates if importance_order.index(m.importance) < max_idx]

        # Delete
        for memory in candidates:
            await self.store.delete(memory.id)

        logger.info("Forgot %d memories", len(candidates))
        return len(candidates)

    def _create_summary(self, contents: List[str]) -> str:
        """Create a summary from multiple contents."""
        # Simple extractive summary
        if len(contents) == 1:
            return contents[0]

        # Take first sentence from each content
        sentences = []
        for content in contents:
            # Simple sentence extraction
            for sentence in content.split("."):
                sentence = sentence.strip()
                if sentence and len(sentence) > 10:
                    sentences.append(sentence)
                    break

        return ". ".join(sentences[:3]) + "."

    def _extract_key_points(self, contents: List[str]) -> List[str]:
        """Extract key points from contents."""
        key_points = []

        for content in contents:
            # Look for numbered lists or bullet points
            lines = content.split("\n")
            for line in lines:
                line = line.strip()
                if line.startswith(("-", "•", "*")) or (len(line) > 0 and line[0].isdigit()):
                    key_points.append(line.lstrip("-•*0123456789. "))

        # If no structured points, take first sentence of each
        if not key_points:
            for content in contents[:3]:
                sentences = content.split(".")
                if sentences:
                    key_points.append(sentences[0].strip())

        return key_points[:5]

    async def get_stats(self) -> Dict[str, Any]:
        """Get retrieval service statistics."""
        store_stats = await self.store.get_stats()
        return {
            **store_stats.model_dump(),
            "total_consolidations": len(self._consolidations),
        }


# Singleton
memory_retrieval = MemoryRetrievalService()
