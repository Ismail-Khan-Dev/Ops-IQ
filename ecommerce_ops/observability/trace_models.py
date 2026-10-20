"""
Trace Storage Models
Models for local trace storage and retrieval.
"""

from datetime import datetime
from enum import StrEnum
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field

from ecommerce_ops.utils import utc_now


class TraceStatus(StrEnum):
    """Trace execution status."""

    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    TIMEOUT = "timeout"


class SpanType(StrEnum):
    """Types of spans."""

    AGENT = "agent"
    LLM = "llm"
    TOOL = "tool"
    RETRIEVAL = "retrieval"
    EMBEDDING = "embedding"
    PIPELINE = "pipeline"
    CUSTOM = "custom"


class StoredSpan(BaseModel):
    """A stored span within a trace."""

    id: str
    trace_id: str
    parent_span_id: Optional[str] = None
    name: str
    span_type: SpanType = SpanType.CUSTOM
    input: Any = None
    output: Any = None
    metadata: Dict[str, Any] = Field(default_factory=dict)
    start_time: datetime = Field(default_factory=utc_now)
    end_time: Optional[datetime] = None
    duration_ms: Optional[float] = None
    status: TraceStatus = TraceStatus.COMPLETED
    error: Optional[str] = None
    model: Optional[str] = None
    tokens_used: Optional[int] = None
    cost_usd: Optional[float] = None

    class Config:
        extra = "allow"

    @property
    def is_successful(self) -> bool:
        return self.status == TraceStatus.COMPLETED


class StoredScore(BaseModel):
    """A stored evaluation score."""

    id: str
    trace_id: str
    span_id: Optional[str] = None
    name: str
    value: float
    comment: Optional[str] = None
    evaluator: Optional[str] = None
    created_at: datetime = Field(default_factory=utc_now)
    metadata: Dict[str, Any] = Field(default_factory=dict)

    class Config:
        extra = "allow"


class StoredTrace(BaseModel):
    """A stored trace."""

    id: str
    name: str
    status: TraceStatus = TraceStatus.RUNNING
    user_id: Optional[str] = None
    session_id: Optional[str] = None
    tags: List[str] = Field(default_factory=list)
    metadata: Dict[str, Any] = Field(default_factory=dict)
    input: Any = None
    output: Any = None
    error: Optional[str] = None
    start_time: datetime = Field(default_factory=utc_now)
    end_time: Optional[datetime] = None
    duration_ms: Optional[float] = None
    spans: List[StoredSpan] = Field(default_factory=list)
    scores: List[StoredScore] = Field(default_factory=list)
    total_tokens: int = 0
    total_cost_usd: float = 0.0

    class Config:
        extra = "allow"

    @property
    def is_successful(self) -> bool:
        return self.status == TraceStatus.COMPLETED

    @property
    def span_count(self) -> int:
        return len(self.spans)

    @property
    def average_score(self) -> float:
        if not self.scores:
            return 0.0
        return sum(s.value for s in self.scores) / len(self.scores)

    @property
    def llm_spans(self) -> List[StoredSpan]:
        return [s for s in self.spans if s.span_type == SpanType.LLM]

    @property
    def tool_spans(self) -> List[StoredSpan]:
        return [s for s in self.spans if s.span_type == SpanType.TOOL]

    def get_summary(self) -> Dict[str, Any]:
        """Get trace summary."""
        return {
            "id": self.id,
            "name": self.name,
            "status": self.status.value,
            "duration_ms": self.duration_ms,
            "span_count": self.span_count,
            "average_score": round(self.average_score, 3),
            "total_tokens": self.total_tokens,
            "total_cost_usd": round(self.total_cost_usd, 4),
            "tags": self.tags,
            "start_time": self.start_time.isoformat(),
        }


class TraceFilter(BaseModel):
    """Filter criteria for trace queries."""

    name: Optional[str] = None
    status: Optional[TraceStatus] = None
    user_id: Optional[str] = None
    session_id: Optional[str] = None
    tags: Optional[List[str]] = None
    min_duration_ms: Optional[float] = None
    max_duration_ms: Optional[float] = None
    min_score: Optional[float] = None
    start_time_after: Optional[datetime] = None
    start_time_before: Optional[datetime] = None
    limit: int = 100
    offset: int = 0


class TraceAggregation(BaseModel):
    """Aggregated trace metrics."""

    total_traces: int = 0
    successful_traces: int = 0
    failed_traces: int = 0
    avg_duration_ms: float = 0.0
    p50_duration_ms: float = 0.0
    p95_duration_ms: float = 0.0
    p99_duration_ms: float = 0.0
    total_tokens: int = 0
    total_cost_usd: float = 0.0
    avg_score: float = 0.0
    traces_by_status: Dict[str, int] = Field(default_factory=dict)
    traces_by_name: Dict[str, int] = Field(default_factory=dict)
    cost_by_model: Dict[str, float] = Field(default_factory=dict)
    daily_volume: List[Dict[str, Any]] = Field(default_factory=list)


class EvaluationReport(BaseModel):
    """Evaluation report for a set of traces."""

    period_start: datetime
    period_end: datetime
    total_evaluations: int = 0
    pass_rate: float = 0.0
    avg_score: float = 0.0
    dimension_scores: Dict[str, float] = Field(default_factory=dict)
    agent_performance: Dict[str, Dict[str, Any]] = Field(default_factory=dict)
    recommendations: List[str] = Field(default_factory=list)
    trend: str = "stable"  # improving, stable, declining
