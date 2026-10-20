"""Tests for Memory API endpoints."""


from ecommerce_ops.api.memory import (
    MemoryCreateRequest,
    MemorySearchRequest,
    SessionCreateRequest,
)
from ecommerce_ops.memory.vector.models import MemoryImportance, MemoryType

# ── Request Model Tests ───────────────────────────────────


def test_memory_create_request_defaults():
    req = MemoryCreateRequest(content="test memory")
    assert req.memory_type == MemoryType.EPISODIC
    assert req.importance == MemoryImportance.MEDIUM
    assert req.agent_name is None
    assert req.session_id is None


def test_memory_create_request_custom():
    req = MemoryCreateRequest(
        content="important event",
        memory_type=MemoryType.SEMANTIC,
        importance=MemoryImportance.HIGH,
        agent_name="fraud_agent",
        tags=["fraud", "high_priority"],
    )
    assert req.memory_type == MemoryType.SEMANTIC
    assert req.importance == MemoryImportance.HIGH
    assert req.agent_name == "fraud_agent"


def test_memory_search_request_defaults():
    req = MemorySearchRequest(query="test query")
    assert req.max_results == 10
    assert req.min_similarity == 0.7


def test_session_create_request_defaults():
    req = SessionCreateRequest()
    assert req.user_id is None
    assert req.agent_name is None


def test_session_create_request_custom():
    req = SessionCreateRequest(user_id="u1", agent_name="fraud")
    assert req.user_id == "u1"
    assert req.agent_name == "fraud"


# ── Memory Type Tests ─────────────────────────────────────


def test_memory_types_exist():
    assert MemoryType.EPISODIC.value == "episodic"
    assert MemoryType.SEMANTIC.value == "semantic"
    assert MemoryType.PROCEDURAL.value == "procedural"


def test_memory_importance_levels():
    assert MemoryImportance.LOW.value == "low"
    assert MemoryImportance.MEDIUM.value == "medium"
    assert MemoryImportance.HIGH.value == "high"
    assert MemoryImportance.CRITICAL.value == "critical"
