"""
Vector Memory Storage Models
Models for vector-based memory storage and retrieval.
"""

from datetime import datetime
from enum import StrEnum
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field

from ecommerce_ops.utils import utc_now


class MemoryType(StrEnum):
    """Types of memory entries."""

    EPISODIC = "episodic"  # Specific events/interactions
    SEMANTIC = "semantic"  # Facts and knowledge
    PROCEDURAL = "procedural"  # How to do things
    CONVERSATIONAL = "conversational"  # Conversation history
    DECISION = "decision"  # Past decisions and outcomes


class MemoryImportance(StrEnum):
    """Importance levels for memory entries."""

    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class MemoryEntry(BaseModel):
    """A single memory entry with vector embedding."""

    id: str
    memory_type: MemoryType
    content: str
    embedding: Optional[List[float]] = None
    metadata: Dict[str, Any] = Field(default_factory=dict)
    importance: MemoryImportance = MemoryImportance.MEDIUM
    agent_name: Optional[str] = None
    session_id: Optional[str] = None
    user_id: Optional[str] = None
    tags: List[str] = Field(default_factory=list)
    source: Optional[str] = None
    created_at: datetime = Field(default_factory=utc_now)
    last_accessed: Optional[datetime] = None
    access_count: int = 0
    expiry: Optional[datetime] = None
    is_compressed: bool = False
    parent_id: Optional[str] = None  # For hierarchical memory

    class Config:
        extra = "allow"

    @property
    def is_expired(self) -> bool:
        if self.expiry:
            return utc_now() > self.expiry
        return False

    @property
    def recency_score(self) -> float:
        """Calculate recency score (0-1, higher is more recent)."""
        if not self.last_accessed:
            return 0.5
        hours_since = (utc_now() - self.last_accessed).total_seconds() / 3600
        # Decay over 7 days
        return max(0, 1.0 - (hours_since / 168))

    @property
    def importance_weight(self) -> float:
        """Get importance weight for scoring."""
        weights = {
            MemoryImportance.LOW: 0.25,
            MemoryImportance.MEDIUM: 0.5,
            MemoryImportance.HIGH: 0.75,
            MemoryImportance.CRITICAL: 1.0,
        }
        return weights.get(self.importance, 0.5)


class MemoryQuery(BaseModel):
    """Query for memory retrieval."""

    query: str
    query_embedding: Optional[List[float]] = None
    memory_type: Optional[MemoryType] = None
    agent_name: Optional[str] = None
    session_id: Optional[str] = None
    user_id: Optional[str] = None
    tags: Optional[List[str]] = None
    min_importance: Optional[MemoryImportance] = None
    max_results: int = 10
    min_similarity: float = 0.7
    include_expired: bool = False
    time_window_hours: Optional[int] = None


class MemorySearchResult(BaseModel):
    """Result from memory search."""

    entry: MemoryEntry
    similarity: float
    rank: int
    score: float  # Combined score (similarity + recency + importance)
    explanation: Optional[str] = None


class MemoryConsolidation(BaseModel):
    """Result of memory consolidation."""

    id: str
    original_memories: List[str]  # IDs of memories that were consolidated
    consolidated_content: str
    summary: str
    key_points: List[str] = Field(default_factory=list)
    created_at: datetime = Field(default_factory=utc_now)
    memory_type: MemoryType = MemoryType.SEMANTIC
    importance: MemoryImportance = MemoryImportance.HIGH


class SessionContext(BaseModel):
    """Context for a memory session."""

    session_id: str
    user_id: Optional[str] = None
    agent_name: Optional[str] = None
    start_time: datetime = Field(default_factory=utc_now)
    last_activity: datetime = Field(default_factory=utc_now)
    conversation_turns: int = 0
    memories_created: int = 0
    memories_accessed: int = 0
    metadata: Dict[str, Any] = Field(default_factory=dict)
    is_active: bool = True

    class Config:
        extra = "allow"

    @property
    def duration_minutes(self) -> float:
        return (self.last_activity - self.start_time).total_seconds() / 60


class MemoryStats(BaseModel):
    """Statistics for memory system."""

    total_memories: int = 0
    memories_by_type: Dict[str, int] = Field(default_factory=dict)
    memories_by_importance: Dict[str, int] = Field(default_factory=dict)
    memories_by_agent: Dict[str, int] = Field(default_factory=dict)
    avg_access_count: float = 0.0
    total_sessions: int = 0
    active_sessions: int = 0
    avg_session_duration_minutes: float = 0.0
    total_embeddings: int = 0
    storage_size_mb: float = 0.0


class MemoryConfig(BaseModel):
    """Configuration for memory system."""

    max_memories: int = 10000
    max_memories_per_agent: int = 1000
    max_session_duration_hours: int = 24
    consolidation_threshold: int = 50  # Consolidate after N memories
    similarity_threshold: float = 0.7
    importance_decay_days: int = 30
    enable_compression: bool = True
    embedding_model: str = "text-embedding-3-small"
    embedding_dimensions: int = 1536
