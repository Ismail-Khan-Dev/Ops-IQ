from datetime import datetime
from typing import Any, Dict, List, Optional, TypedDict

from pydantic import BaseModel, Field

from ecommerce_ops.utils import utc_now


class AgentDecision(BaseModel):
    agent_id: str
    action_type: str
    reasoning: str
    action_data: Dict = Field(default_factory=dict)
    requires_approval: bool = True
    confidence_score: float
    timestamp: datetime = Field(default_factory=utc_now)


class ReflectionFeedback(BaseModel):
    agent_id: str
    decision_index: int
    passed: bool
    issues: List[str]
    adjusted_confidence: Optional[float] = None


class ExecutionPlan(BaseModel):
    agents_to_run: List[str]
    rationale: str


class OverallState(TypedDict):
    inventory_data: List[Dict]
    pricing_data: List[Dict]
    reviews_data: List[Dict]
    active_orders: List[Dict]
    fraud_alerts: List[Dict]
    decisions: List[AgentDecision]
    hitl_queue: List[Dict]
    messages: List
    errors: List[Dict]
    run_id: str
    timestamp: Optional[str]
    execution_plan: Optional[ExecutionPlan]
    reflection_feedback: List[ReflectionFeedback]
    memory_context: Dict[str, Any]
    step_index: int
