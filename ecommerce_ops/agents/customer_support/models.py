"""
Customer Support Data Models
Pydantic models for support tickets, responses, and analytics.
"""

from datetime import datetime
from enum import StrEnum
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field

from ecommerce_ops.utils import utc_now


class TicketStatus(StrEnum):
    OPEN = "open"
    IN_PROGRESS = "in_progress"
    WAITING_CUSTOMER = "waiting_customer"
    WAITING_INTERNAL = "waiting_internal"
    RESOLVED = "resolved"
    CLOSED = "closed"
    ESCALATED = "escalated"


class TicketPriority(StrEnum):
    LOW = "low"
    NORMAL = "normal"
    HIGH = "high"
    URGENT = "urgent"
    CRITICAL = "critical"


class TicketCategory(StrEnum):
    ORDER_STATUS = "order_status"
    SHIPPING = "shipping"
    RETURNS = "returns"
    REFUNDS = "refunds"
    PRODUCT_QUESTION = "product_question"
    COMPLAINT = "complaint"
    TECHNICAL = "technical"
    ACCOUNT = "account"
    BILLING = "billing"
    OTHER = "other"


class TicketChannel(StrEnum):
    EMAIL = "email"
    CHAT = "chat"
    PHONE = "phone"
    SOCIAL = "social"
    API = "api"


class SentimentType(StrEnum):
    VERY_NEGATIVE = "very_negative"
    NEGATIVE = "negative"
    NEUTRAL = "neutral"
    POSITIVE = "positive"
    VERY_POSITIVE = "very_positive"


class CustomerSatisfaction(StrEnum):
    VERY_DISSATISFIED = "very_dissatisfied"
    DISSATISFIED = "dissatisfied"
    NEUTRAL = "neutral"
    SATISFIED = "satisfied"
    VERY_SATISFIED = "very_satisfied"


class ResponseTemplate(BaseModel):
    id: str
    name: str
    category: TicketCategory
    subject_template: str
    body_template: str
    variables: List[str] = Field(default_factory=list)
    language: str = "en"
    is_active: bool = True


class SupportTicket(BaseModel):
    id: str
    shop_domain: str
    customer_email: Optional[str] = None
    customer_name: Optional[str] = None
    customer_id: Optional[int] = None
    subject: str
    body: str
    category: TicketCategory = TicketCategory.OTHER
    priority: TicketPriority = TicketPriority.NORMAL
    status: TicketStatus = TicketStatus.OPEN
    channel: TicketChannel = TicketChannel.EMAIL
    sentiment: Optional[SentimentType] = None
    language: str = "en"
    order_id: Optional[str] = None
    product_id: Optional[str] = None
    tags: List[str] = Field(default_factory=list)
    metadata: Dict[str, Any] = Field(default_factory=dict)
    created_at: datetime = Field(default_factory=utc_now)
    updated_at: Optional[datetime] = None
    first_response_at: Optional[datetime] = None
    resolved_at: Optional[datetime] = None
    assigned_to: Optional[str] = None
    assigned_agent: Optional[str] = None
    satisfaction: Optional[CustomerSatisfaction] = None
    resolution_notes: Optional[str] = None

    class Config:
        extra = "allow"

    @property
    def is_escalated(self) -> bool:
        return self.status == TicketStatus.ESCALATED

    @property
    def response_time_hours(self) -> Optional[float]:
        if self.first_response_at and self.created_at:
            delta = self.first_response_at - self.created_at
            return delta.total_seconds() / 3600
        return None

    @property
    def resolution_time_hours(self) -> Optional[float]:
        if self.resolved_at and self.created_at:
            delta = self.resolved_at - self.created_at
            return delta.total_seconds() / 3600
        return None


class TicketMessage(BaseModel):
    id: str
    ticket_id: str
    sender_type: str  # "customer", "agent", "system"
    sender_id: Optional[str] = None
    sender_name: Optional[str] = None
    content: str
    is_internal: bool = False
    attachments: List[Dict[str, str]] = Field(default_factory=list)
    created_at: datetime = Field(default_factory=utc_now)
    metadata: Dict[str, Any] = Field(default_factory=dict)

    class Config:
        extra = "allow"


class ResponseSuggestion(BaseModel):
    ticket_id: str
    suggested_response: str
    confidence: float
    reasoning: str
    template_used: Optional[str] = None
    requires_human_review: bool = False
    follow_up_questions: List[str] = Field(default_factory=list)
    estimated_resolution_time: Optional[float] = None


class SupportAgentMetrics(BaseModel):
    agent_id: str
    agent_name: str
    tickets_handled: int = 0
    tickets_resolved: int = 0
    avg_response_time_hours: float = 0.0
    avg_resolution_time_hours: float = 0.0
    avg_satisfaction: float = 0.0
    first_contact_resolution_rate: float = 0.0
    escalation_rate: float = 0.0
    customer_satisfaction_score: float = 0.0

    class Config:
        extra = "allow"


class SupportAnalytics(BaseModel):
    total_tickets: int = 0
    open_tickets: int = 0
    avg_response_time_hours: float = 0.0
    avg_resolution_time_hours: float = 0.0
    satisfaction_score: float = 0.0
    first_contact_resolution_rate: float = 0.0
    escalation_rate: float = 0.0
    category_breakdown: Dict[str, int] = Field(default_factory=dict)
    priority_breakdown: Dict[str, int] = Field(default_factory=dict)
    channel_breakdown: Dict[str, int] = Field(default_factory=dict)
    sentiment_distribution: Dict[str, int] = Field(default_factory=dict)
    hourly_volume: List[Dict[str, Any]] = Field(default_factory=list)
    top_issues: List[Dict[str, Any]] = Field(default_factory=list)
    agent_performance: List[SupportAgentMetrics] = Field(default_factory=list)


class EscalationRule(BaseModel):
    id: str
    name: str
    conditions: Dict[str, Any]
    action: str  # "escalate", "priority_boost", "assign_specialist"
    target_queue: Optional[str] = None
    target_agent: Optional[str] = None
    notification_channels: List[str] = Field(default_factory=list)
    is_active: bool = True


class KnowledgeArticle(BaseModel):
    id: str
    title: str
    content: str
    category: TicketCategory
    tags: List[str] = Field(default_factory=list)
    helpful_count: int = 0
    not_helpful_count: int = 0
    last_updated: datetime = Field(default_factory=utc_now)
    is_published: bool = True

    class Config:
        extra = "allow"

    @property
    def helpfulness_ratio(self) -> float:
        total = self.helpful_count + self.not_helpful_count
        if total == 0:
            return 0.0
        return self.helpful_count / total
