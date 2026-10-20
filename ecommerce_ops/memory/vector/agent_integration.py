"""
Agent Memory Integration
Integrates vector memory with agent operations.
"""

import logging
from typing import Any, Dict, List, Optional

from ecommerce_ops.memory.vector.models import (
    MemoryEntry,
    MemoryImportance,
    MemoryType,
)
from ecommerce_ops.memory.vector.retrieval import MemoryRetrievalService, memory_retrieval
from ecommerce_ops.memory.vector.sessions import SessionManager

logger = logging.getLogger("ecommerce_ops.memory.vector.agent_integration")


class AgentMemoryManager:
    """Manages memory operations for agents."""

    def __init__(
        self,
        retrieval_service: MemoryRetrievalService = None,
        session_manager: SessionManager = None,
    ):
        self.retrieval = retrieval_service or memory_retrieval
        self.sessions = session_manager or session_manager
        self._agent_sessions: Dict[str, str] = {}  # agent_name -> session_id

    async def start_agent_session(
        self,
        agent_name: str,
        user_id: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> str:
        """Start a new session for an agent."""
        session = self.sessions.create_session(
            user_id=user_id,
            agent_name=agent_name,
            metadata=metadata or {},
        )
        self._agent_sessions[agent_name] = session.session_id
        logger.info("Started session %s for agent %s", session.session_id, agent_name)
        return session.session_id

    async def end_agent_session(self, agent_name: str) -> bool:
        """End an agent's session."""
        session_id = self._agent_sessions.get(agent_name)
        if session_id:
            self.sessions.end_session(session_id)
            del self._agent_sessions[agent_name]
            logger.info("Ended session for agent %s", agent_name)
            return True
        return False

    async def store_decision(
        self,
        agent_name: str,
        decision_type: str,
        reasoning: str,
        outcome: Optional[str] = None,
        confidence: float = 0.0,
        session_id: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> MemoryEntry:
        """Store an agent decision as memory."""
        content = f"Decision: {decision_type}. Reasoning: {reasoning}"
        if outcome:
            content += f". Outcome: {outcome}"

        importance = MemoryImportance.HIGH if confidence > 0.8 else MemoryImportance.MEDIUM

        entry = await self.retrieval.remember(
            content=content,
            memory_type=MemoryType.DECISION,
            importance=importance,
            agent_name=agent_name,
            session_id=session_id or self._agent_sessions.get(agent_name),
            tags=[decision_type, "decision"],
            metadata={
                "decision_type": decision_type,
                "confidence": confidence,
                "outcome": outcome,
                **(metadata or {}),
            },
        )

        # Update session activity
        if session_id or agent_name in self._agent_sessions:
            sid = session_id or self._agent_sessions[agent_name]
            self.sessions.update_activity(sid, memories_created=1)

        return entry

    async def store_interaction(
        self,
        agent_name: str,
        user_message: str,
        agent_response: str,
        session_id: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> MemoryEntry:
        """Store a user-agent interaction."""
        content = f"User: {user_message}\nAgent: {agent_response}"

        entry = await self.retrieval.remember(
            content=content,
            memory_type=MemoryType.CONVERSATIONAL,
            importance=MemoryImportance.MEDIUM,
            agent_name=agent_name,
            session_id=session_id or self._agent_sessions.get(agent_name),
            tags=["interaction", "conversation"],
            metadata=metadata or {},
        )

        return entry

    async def store_learning(
        self,
        agent_name: str,
        lesson: str,
        context: Optional[str] = None,
        confidence: float = 0.0,
        session_id: Optional[str] = None,
    ) -> MemoryEntry:
        """Store a learning/experience."""
        content = f"Lesson: {lesson}"
        if context:
            content = f"Context: {context}\n{content}"

        importance = MemoryImportance.HIGH if confidence > 0.9 else MemoryImportance.MEDIUM

        entry = await self.retrieval.remember(
            content=content,
            memory_type=MemoryType.PROCEDURAL,
            importance=importance,
            agent_name=agent_name,
            session_id=session_id or self._agent_sessions.get(agent_name),
            tags=["learning", "experience"],
            metadata={"confidence": confidence},
        )

        return entry

    async def store_fact(
        self,
        agent_name: str,
        fact: str,
        source: Optional[str] = None,
        confidence: float = 1.0,
        session_id: Optional[str] = None,
    ) -> MemoryEntry:
        """Store a factual piece of information."""
        importance = MemoryImportance.HIGH if confidence > 0.9 else MemoryImportance.MEDIUM

        entry = await self.retrieval.remember(
            content=fact,
            memory_type=MemoryType.SEMANTIC,
            importance=importance,
            agent_name=agent_name,
            session_id=session_id or self._agent_sessions.get(agent_name),
            source=source,
            tags=["fact", "knowledge"],
            metadata={"confidence": confidence},
        )

        return entry

    async def get_agent_context(
        self,
        agent_name: str,
        query: str,
        max_tokens: int = 4000,
    ) -> str:
        """Get relevant context for an agent."""
        session_id = self._agent_sessions.get(agent_name)

        # Get semantic context
        semantic_context = await self.retrieval.get_context_window(
            query=query,
            session_id=session_id,
            max_tokens=max_tokens // 2,
        )

        # Get recent memories
        recent_memories = await self.retrieval.recall_recent(
            agent_name=agent_name,
            session_id=session_id,
            hours=24,
            max_results=5,
        )

        # Combine contexts
        context_parts = []

        if semantic_context:
            context_parts.append("Relevant knowledge:\n" + semantic_context)

        if recent_memories:
            recent_text = "\n".join([f"- {m.entry.content[:100]}" for m in recent_memories])
            context_parts.append("Recent activity:\n" + recent_text)

        return "\n\n".join(context_parts) if context_parts else ""

    async def get_similar_decisions(
        self,
        agent_name: str,
        decision_type: str,
        max_results: int = 5,
    ) -> List[Dict[str, Any]]:
        """Get similar past decisions for an agent."""
        results = await self.retrieval.recall(
            query=f"decision {decision_type}",
            agent_name=agent_name,
            memory_type=MemoryType.DECISION,
            max_results=max_results,
            min_similarity=0.6,
        )

        return [
            {
                "content": r.entry.content,
                "similarity": r.similarity,
                "metadata": r.entry.metadata,
                "created_at": r.entry.created_at.isoformat(),
            }
            for r in results
        ]

    async def reflect_on_decision(
        self,
        agent_name: str,
        decision_type: str,
        reasoning: str,
    ) -> Dict[str, Any]:
        """Reflect on a decision using past experiences."""
        # Get similar past decisions
        similar_decisions = await self.get_similar_decisions(
            agent_name,
            decision_type,
            max_results=3,
        )

        # Analyze patterns
        successful = []
        unsuccessful = []

        for decision in similar_decisions:
            outcome = decision.get("metadata", {}).get("outcome")
            if outcome == "success":
                successful.append(decision)
            elif outcome == "failure":
                unsuccessful.append(decision)

        # Generate reflection
        reflection = {
            "similar_decisions_count": len(similar_decisions),
            "successful_count": len(successful),
            "unsuccessful_count": len(unsuccessful),
            "recommendation": self._generate_recommendation(successful, unsuccessful, reasoning),
        }

        return reflection

    def _generate_recommendation(
        self,
        successful: List[Dict],
        unsuccessful: List[Dict],
        current_reasoning: str,
    ) -> str:
        """Generate recommendation based on past decisions."""
        if not successful and not unsuccessful:
            return "No similar past decisions found. Proceed with caution."

        if len(successful) > len(unsuccessful):
            return f"Based on {len(successful)} similar successful decisions, this approach appears sound."
        elif len(unsuccessful) > len(successful):
            return f"Warning: {len(unsuccessful)} similar decisions failed. Consider alternative approach."
        else:
            return "Mixed results from similar decisions. Review carefully."

    async def get_agent_memory_stats(self, agent_name: str) -> Dict[str, Any]:
        """Get memory statistics for an agent."""
        stats = await self.retrieval.get_stats()

        # Filter by agent
        agent_memories = stats.get("memories_by_agent", {}).get(agent_name, 0)

        return {
            "agent_name": agent_name,
            "total_memories": agent_memories,
            "session_id": self._agent_sessions.get(agent_name),
        }


# Singleton
agent_memory_manager = AgentMemoryManager()
