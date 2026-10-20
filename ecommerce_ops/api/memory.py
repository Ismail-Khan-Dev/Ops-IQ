"""
Memory and Session API Routes
Endpoints for vector memory and session management.
"""

import logging
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel

from ecommerce_ops.memory.vector.agent_integration import agent_memory_manager
from ecommerce_ops.memory.vector.models import (
    MemoryImportance,
    MemoryType,
)
from ecommerce_ops.memory.vector.persistent_store import vector_store
from ecommerce_ops.memory.vector.retrieval import memory_retrieval
from ecommerce_ops.memory.vector.sessions import session_manager
from ecommerce_ops.security.auth import require_permission
from ecommerce_ops.security.models import Permission, User
from ecommerce_ops.utils import utc_now

logger = logging.getLogger("ecommerce_ops.api.memory")

router = APIRouter(prefix="/memory", tags=["memory"])


class MemoryCreateRequest(BaseModel):
    content: str
    memory_type: MemoryType = MemoryType.EPISODIC
    importance: MemoryImportance = MemoryImportance.MEDIUM
    agent_name: Optional[str] = None
    session_id: Optional[str] = None
    user_id: Optional[str] = None
    tags: Optional[List[str]] = None
    metadata: Optional[Dict[str, Any]] = None
    source: Optional[str] = None


class MemorySearchRequest(BaseModel):
    query: str
    memory_type: Optional[MemoryType] = None
    agent_name: Optional[str] = None
    session_id: Optional[str] = None
    max_results: int = 10
    min_similarity: float = 0.7


class SessionCreateRequest(BaseModel):
    user_id: Optional[str] = None
    agent_name: Optional[str] = None
    metadata: Optional[Dict[str, Any]] = None


# ── Memory Operations ──────────────────────────────────────


@router.post("/memories")
async def create_memory(
    req: MemoryCreateRequest,
    _: User = Depends(require_permission(Permission.MEMORY_EDIT)),
):
    """Create a new memory entry."""
    entry = await memory_retrieval.remember(
        content=req.content,
        memory_type=req.memory_type,
        importance=req.importance,
        agent_name=req.agent_name,
        session_id=req.session_id,
        user_id=req.user_id,
        tags=req.tags,
        metadata=req.metadata,
        source=req.source,
    )

    return {
        "id": entry.id,
        "memory_type": entry.memory_type.value,
        "importance": entry.importance.value,
        "created_at": entry.created_at.isoformat(),
    }


@router.post("/memories/search")
async def search_memories(
    req: MemorySearchRequest,
    _: User = Depends(require_permission(Permission.MEMORY_VIEW)),
):
    """Search memories using semantic similarity."""
    results = await memory_retrieval.recall(
        query=req.query,
        memory_type=req.memory_type,
        agent_name=req.agent_name,
        session_id=req.session_id,
        max_results=req.max_results,
        min_similarity=req.min_similarity,
    )

    return {
        "query": req.query,
        "results": [
            {
                "id": r.entry.id,
                "content": r.entry.content,
                "memory_type": r.entry.memory_type.value,
                "importance": r.entry.importance.value,
                "similarity": round(r.similarity, 3),
                "score": round(r.score, 3),
                "created_at": r.entry.created_at.isoformat(),
            }
            for r in results
        ],
        "total": len(results),
    }


@router.get("/memories/{memory_id}")
async def get_memory(
    memory_id: str,
    _: User = Depends(require_permission(Permission.MEMORY_VIEW)),
):
    """Get a memory by ID."""
    entry = await vector_store.get(memory_id)
    if not entry:
        raise HTTPException(status_code=404, detail="Memory not found")

    return {
        "id": entry.id,
        "content": entry.content,
        "memory_type": entry.memory_type.value,
        "importance": entry.importance.value,
        "agent_name": entry.agent_name,
        "session_id": entry.session_id,
        "tags": entry.tags,
        "created_at": entry.created_at.isoformat(),
        "access_count": entry.access_count,
    }


@router.delete("/memories/{memory_id}")
async def delete_memory(
    memory_id: str,
    _: User = Depends(require_permission(Permission.MEMORY_DELETE)),
):
    """Delete a memory."""
    success = await vector_store.delete(memory_id)
    return {"deleted": success}


@router.get("/memories")
async def list_memories(
    memory_type: Optional[MemoryType] = None,
    agent_name: Optional[str] = None,
    limit: int = Query(50, ge=1, le=200),
    _: User = Depends(require_permission(Permission.MEMORY_VIEW)),
):
    """List memories with filters."""
    from ecommerce_ops.memory.vector.models import MemoryQuery

    query = MemoryQuery(
        query="",
        memory_type=memory_type,
        agent_name=agent_name,
        max_results=limit,
        min_similarity=0.0,
    )

    candidates = await vector_store._filter_memories(query)
    candidates.sort(key=lambda e: e.created_at, reverse=True)

    return {
        "memories": [
            {
                "id": e.id,
                "content": e.content[:200],
                "memory_type": e.memory_type.value,
                "importance": e.importance.value,
                "agent_name": e.agent_name,
                "created_at": e.created_at.isoformat(),
            }
            for e in candidates[:limit]
        ],
        "total": len(candidates),
    }


# ── Memory Stats ───────────────────────────────────────────


@router.get("/memories/stats/summary")
async def get_memory_stats(
    _: User = Depends(require_permission(Permission.MEMORY_VIEW)),
):
    """Get memory system statistics."""
    stats = await vector_store.get_stats()
    return stats.model_dump()


# ── Session Operations ─────────────────────────────────────


@router.post("/sessions")
async def create_session(
    req: SessionCreateRequest,
    _: User = Depends(require_permission(Permission.MEMORY_EDIT)),
):
    """Create a new session."""
    session = session_manager.create_session(
        user_id=req.user_id,
        agent_name=req.agent_name,
        metadata=req.metadata,
    )

    return {
        "session_id": session.session_id,
        "user_id": session.user_id,
        "agent_name": session.agent_name,
        "created_at": session.start_time.isoformat(),
    }


@router.get("/sessions")
async def list_sessions(
    active_only: bool = Query(True),
    user_id: Optional[str] = None,
    agent_name: Optional[str] = None,
    _: User = Depends(require_permission(Permission.MEMORY_VIEW)),
):
    """List sessions with filters."""
    if user_id:
        sessions = session_manager.get_user_sessions(user_id, active_only)
    elif agent_name:
        sessions = session_manager.get_agent_sessions(agent_name, active_only)
    elif active_only:
        sessions = session_manager.get_active_sessions()
    else:
        sessions = list(session_manager._sessions.values())

    return {
        "sessions": [
            {
                "session_id": s.session_id,
                "user_id": s.user_id,
                "agent_name": s.agent_name,
                "is_active": s.is_active,
                "duration_minutes": round(s.duration_minutes, 2),
                "conversation_turns": s.conversation_turns,
                "created_at": s.start_time.isoformat(),
            }
            for s in sessions
        ],
        "total": len(sessions),
    }


@router.get("/sessions/{session_id}")
async def get_session(
    session_id: str,
    _: User = Depends(require_permission(Permission.MEMORY_VIEW)),
):
    """Get session details."""
    session = session_manager.get_session(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")

    return {
        "session_id": session.session_id,
        "user_id": session.user_id,
        "agent_name": session.agent_name,
        "is_active": session.is_active,
        "duration_minutes": round(session.duration_minutes, 2),
        "conversation_turns": session.conversation_turns,
        "memories_created": session.memories_created,
        "memories_accessed": session.memories_accessed,
        "metadata": session.metadata,
        "created_at": session.start_time.isoformat(),
        "last_activity": session.last_activity.isoformat(),
    }


@router.delete("/sessions/{session_id}")
async def end_session(
    session_id: str,
    _: User = Depends(require_permission(Permission.MEMORY_EDIT)),
):
    """End a session."""
    success = session_manager.end_session(session_id)
    return {"ended": success}


@router.get("/sessions/stats/summary")
async def get_session_stats(
    _: User = Depends(require_permission(Permission.MEMORY_VIEW)),
):
    """Get session statistics."""
    return session_manager.get_stats()


# ── Agent Memory Operations ────────────────────────────────


@router.post("/agent/{agent_name}/context")
async def get_agent_context(
    agent_name: str,
    query: str,
    max_tokens: int = Query(4000, ge=100, le=10000),
    _: User = Depends(require_permission(Permission.MEMORY_VIEW)),
):
    """Get memory context for an agent."""
    context = await agent_memory_manager.get_agent_context(
        agent_name=agent_name,
        query=query,
        max_tokens=max_tokens,
    )

    return {
        "agent_name": agent_name,
        "context": context,
        "token_count": len(context) // 4,
    }


@router.post("/agent/{agent_name}/decision")
async def store_agent_decision(
    agent_name: str,
    decision_type: str,
    reasoning: str,
    outcome: Optional[str] = None,
    confidence: float = 0.0,
    _: User = Depends(require_permission(Permission.MEMORY_EDIT)),
):
    """Store an agent decision."""
    entry = await agent_memory_manager.store_decision(
        agent_name=agent_name,
        decision_type=decision_type,
        reasoning=reasoning,
        outcome=outcome,
        confidence=confidence,
    )

    return {
        "id": entry.id,
        "stored": True,
    }


@router.post("/agent/{agent_name}/reflect")
async def reflect_on_decision(
    agent_name: str,
    decision_type: str,
    reasoning: str,
    _: User = Depends(require_permission(Permission.MEMORY_EDIT)),
):
    """Reflect on a decision using past experiences."""
    reflection = await agent_memory_manager.reflect_on_decision(
        agent_name=agent_name,
        decision_type=decision_type,
        reasoning=reasoning,
    )

    return reflection


@router.get("/agent/{agent_name}/stats")
async def get_agent_memory_stats(
    agent_name: str,
    _: User = Depends(require_permission(Permission.MEMORY_VIEW)),
):
    """Get memory stats for an agent."""
    return await agent_memory_manager.get_agent_memory_stats(agent_name)


# ── Health ─────────────────────────────────────────────────


@router.get("/health")
async def memory_health():
    """Health check for memory service."""
    stats = await vector_store.get_stats()
    session_stats = session_manager.get_stats()

    return {
        "status": "healthy",
        "total_memories": stats.total_memories,
        "total_sessions": session_stats["total_sessions"],
        "active_sessions": session_stats["active_sessions"],
        "timestamp": utc_now().isoformat(),
    }
