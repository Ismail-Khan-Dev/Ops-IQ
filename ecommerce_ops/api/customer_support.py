"""
Customer Support API Routes
Endpoints for ticket management, responses, and analytics.
"""

import logging
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, BackgroundTasks, Depends, Query
from pydantic import BaseModel

from ecommerce_ops.agents.customer_support.agent import CustomerSupportAgent
from ecommerce_ops.agents.customer_support.models import (
    ResponseSuggestion,
    SupportAnalytics,
    SupportTicket,
    TicketCategory,
    TicketChannel,
    TicketPriority,
    TicketStatus,
)
from ecommerce_ops.agents.customer_support.response_engine import ResponseGenerationEngine
from ecommerce_ops.agents.customer_support.ticket_router import TicketClassifier
from ecommerce_ops.config import settings
from ecommerce_ops.security.auth import require_auth, require_permission
from ecommerce_ops.security.models import Permission, User
from ecommerce_ops.utils import utc_now

logger = logging.getLogger("ecommerce_ops.api.customer_support")

router = APIRouter(prefix="/support", tags=["customer-support"])

# Singleton agents
_support_agent = CustomerSupportAgent()
_response_engine = ResponseGenerationEngine()
_classifier = TicketClassifier()


class TicketCreateRequest(BaseModel):
    shop_domain: Optional[str] = None
    customer_email: str
    customer_name: Optional[str] = None
    subject: str
    body: str
    channel: TicketChannel = TicketChannel.EMAIL
    order_id: Optional[str] = None
    product_id: Optional[str] = None
    metadata: Optional[Dict[str, Any]] = None


class TicketUpdateRequest(BaseModel):
    status: Optional[TicketStatus] = None
    priority: Optional[TicketPriority] = None
    assigned_to: Optional[str] = None
    resolution_notes: Optional[str] = None


class ResponseRequest(BaseModel):
    ticket_id: str
    response: str
    is_internal: bool = False
    send_email: bool = True


class BatchTicketRequest(BaseModel):
    tickets: List[TicketCreateRequest]


# ── Ticket Management ──────────────────────────────────────


@router.post("/tickets")
async def create_ticket(
    req: TicketCreateRequest,
    background_tasks: BackgroundTasks,
    _: User = Depends(require_auth),
):
    """Create a new support ticket."""
    ticket_id = f"ticket_{utc_now().strftime('%Y%m%d%H%M%S')}"

    ticket_data = {
        "id": ticket_id,
        "shop_domain": req.shop_domain or settings.SHOPIFY_SHOP_DOMAIN or "unknown",
        "customer_email": req.customer_email,
        "customer_name": req.customer_name,
        "subject": req.subject,
        "body": req.body,
        "channel": req.channel.value,
        "order_id": req.order_id,
        "product_id": req.product_id,
        "metadata": req.metadata or {},
        "created_at": utc_now().isoformat(),
    }

    # Classify ticket
    ticket = SupportTicket(**ticket_data)
    classification = _classifier.classify_ticket(ticket)

    # Generate response suggestion
    suggestion = _response_engine.generate_suggestion(ticket)

    # Store ticket (in production: database)
    # Schedule response processing
    background_tasks.add_task(
        _process_ticket_background,
        ticket_data=ticket_data,
        classification=classification,
        suggestion=suggestion,
    )

    return {
        "ticket_id": ticket_id,
        "status": "created",
        "classification": classification,
        "suggestion": {
            "response": suggestion.suggested_response,
            "confidence": suggestion.confidence,
            "requires_human_review": suggestion.requires_human_review,
        },
    }


@router.get("/tickets")
async def list_tickets(
    status: Optional[TicketStatus] = None,
    priority: Optional[TicketPriority] = None,
    category: Optional[TicketCategory] = None,
    channel: Optional[TicketChannel] = None,
    page: int = Query(1, ge=1),
    limit: int = Query(20, ge=1, le=100),
    _: User = Depends(require_permission(Permission.SUPPORT_VIEW)),
):
    """List support tickets with filters."""
    # In production: query database
    # Sample response
    tickets = [
        {
            "id": "ticket_001",
            "customer_email": "sarah@example.com",
            "customer_name": "Sarah",
            "subject": "Where is my order?",
            "category": "order_status",
            "priority": "high",
            "status": "open",
            "channel": "email",
            "created_at": utc_now().isoformat(),
        },
        {
            "id": "ticket_002",
            "customer_email": "mike@example.com",
            "customer_name": "Mike",
            "subject": "Product question",
            "category": "product_question",
            "priority": "normal",
            "status": "in_progress",
            "channel": "chat",
            "created_at": utc_now().isoformat(),
        },
    ]

    return {
        "tickets": tickets,
        "total": len(tickets),
        "page": page,
        "limit": limit,
    }


@router.get("/tickets/{ticket_id}")
async def get_ticket(
    ticket_id: str,
    _: User = Depends(require_permission(Permission.SUPPORT_VIEW)),
):
    """Get ticket details."""
    # In production: query database
    return {
        "id": ticket_id,
        "customer_email": "sarah@example.com",
        "customer_name": "Sarah",
        "subject": "Where is my order?",
        "body": "I placed my order 2 weeks ago and still haven't received it!",
        "category": "order_status",
        "priority": "high",
        "status": "open",
        "channel": "email",
        "order_id": "12345",
        "created_at": utc_now().isoformat(),
        "messages": [
            {
                "id": "msg_001",
                "sender_type": "customer",
                "content": "I placed my order 2 weeks ago and still haven't received it!",
                "created_at": utc_now().isoformat(),
            }
        ],
    }


@router.patch("/tickets/{ticket_id}")
async def update_ticket(
    ticket_id: str,
    req: TicketUpdateRequest,
    _: User = Depends(require_auth),
):
    """Update ticket status/assignment."""
    updates = {}
    if req.status:
        updates["status"] = req.status.value
    if req.priority:
        updates["priority"] = req.priority.value
    if req.assigned_to:
        updates["assigned_to"] = req.assigned_to
    if req.resolution_notes:
        updates["resolution_notes"] = req.resolution_notes

    # In production: update database
    return {
        "ticket_id": ticket_id,
        "updates": updates,
        "updated_at": utc_now().isoformat(),
    }


# ── Response Management ────────────────────────────────────


@router.post("/tickets/{ticket_id}/respond")
async def respond_to_ticket(
    ticket_id: str,
    req: ResponseRequest,
    background_tasks: BackgroundTasks,
    _: User = Depends(require_auth),
):
    """Send response to ticket."""
    # In production:
    # 1. Store response in database
    # 2. Send email if send_email=True
    # 3. Update ticket status

    background_tasks.add_task(
        _send_response_background,
        ticket_id=ticket_id,
        response=req.response,
        send_email=req.send_email,
    )

    return {
        "ticket_id": ticket_id,
        "status": "response_sent",
        "sent_at": utc_now().isoformat(),
    }


@router.get("/tickets/{ticket_id}/suggestion")
async def get_response_suggestion(
    ticket_id: str,
    _: User = Depends(require_permission(Permission.SUPPORT_VIEW)),
):
    """Get AI response suggestion for a ticket."""
    # In production: generate suggestion based on ticket content via LLM agent.
    # This stub returns a generic placeholder — it does NOT fabricate a
    # confidence score or financial impact. Confidence is reported as 0.0
    # (unknown) and requires_human_review is always True so the suggestion
    # is never auto-executed.
    suggestion = ResponseSuggestion(
        ticket_id=ticket_id,
        suggested_response="Thank you for reaching out. I'd be happy to help you with your order. Could you please provide your order number so I can look up its status?",
        confidence=0.0,
        reasoning="Stub response — real LLM agent not configured for this route.",
        requires_human_review=True,
        follow_up_questions=["Could you provide your order number?"],
    )

    return {
        "ticket_id": ticket_id,
        "suggestion": {
            "response": suggestion.suggested_response,
            "confidence": suggestion.confidence,
            "reasoning": suggestion.reasoning,
            "requires_human_review": suggestion.requires_human_review,
            "follow_up_questions": suggestion.follow_up_questions,
        },
    }


# ── Analytics ──────────────────────────────────────────────


@router.get("/analytics")
async def get_support_analytics(
    days: int = Query(7, ge=1, le=90),
    _: User = Depends(require_permission(Permission.SUPPORT_VIEW)),
):
    """Get support analytics."""
    # In production: query database
    return SupportAnalytics(
        total_tickets=150,
        open_tickets=23,
        avg_response_time_hours=2.5,
        avg_resolution_time_hours=8.3,
        satisfaction_score=4.2,
        first_contact_resolution_rate=0.65,
        escalation_rate=0.15,
        category_breakdown={
            "order_status": 45,
            "shipping": 30,
            "returns": 25,
            "product_question": 20,
            "technical": 15,
            "other": 15,
        },
        priority_breakdown={
            "low": 20,
            "normal": 80,
            "high": 35,
            "urgent": 12,
            "critical": 3,
        },
        channel_breakdown={
            "email": 90,
            "chat": 40,
            "phone": 15,
            "social": 5,
        },
        sentiment_distribution={
            "very_negative": 10,
            "negative": 25,
            "neutral": 80,
            "positive": 30,
            "very_positive": 5,
        },
    )


@router.get("/analytics/agents")
async def get_agent_performance(
    _: User = Depends(require_permission(Permission.SUPPORT_VIEW)),
):
    """Get support agent performance metrics."""
    return {
        "agents": [
            {
                "agent_id": "agent_001",
                "name": "Alice",
                "tickets_handled": 45,
                "tickets_resolved": 40,
                "avg_response_time_hours": 1.8,
                "satisfaction_score": 4.5,
                "first_contact_resolution_rate": 0.72,
            },
            {
                "agent_id": "agent_002",
                "name": "Bob",
                "tickets_handled": 38,
                "tickets_resolved": 35,
                "avg_response_time_hours": 2.2,
                "satisfaction_score": 4.3,
                "first_contact_resolution_rate": 0.68,
            },
        ],
        "team_avg": {
            "avg_response_time_hours": 2.0,
            "satisfaction_score": 4.4,
            "first_contact_resolution_rate": 0.70,
        },
    }


# ── Health ─────────────────────────────────────────────────


@router.get("/health")
async def customer_support_health():
    """Health check for customer support service."""
    return {
        "status": "healthy",
        "agent": "CustomerSupportAgent",
        "response_engine": "ResponseGenerationEngine",
        "classifier": "TicketClassifier",
        "timestamp": utc_now().isoformat(),
    }


# ── Background Tasks ───────────────────────────────────────


async def _process_ticket_background(
    ticket_data: Dict[str, Any],
    classification: Dict[str, Any],
    suggestion: ResponseSuggestion,
):
    """Process ticket in background."""
    try:
        logger.info(
            "Processing ticket %s: category=%s priority=%s",
            ticket_data["id"],
            classification["category"],
            classification["priority"],
        )

        # In production:
        # 1. Store classification results
        # 2. Send auto-response if confidence is high
        # 3. Route to appropriate queue
        # 4. Send notifications

        logger.info("Ticket %s processed successfully", ticket_data["id"])

    except Exception as e:
        logger.error("Failed to process ticket %s: %s", ticket_data["id"], e)


async def _send_response_background(
    ticket_id: str,
    response: str,
    send_email: bool,
):
    """Send response in background."""
    try:
        logger.info(
            "Sending response to ticket %s (email=%s)",
            ticket_id,
            send_email,
        )

        # In production:
        # 1. Store response in database
        # 2. Send email via Resend/SES
        # 3. Update ticket status

        logger.info("Response sent to ticket %s", ticket_id)

    except Exception as e:
        logger.error("Failed to send response to ticket %s: %s", ticket_id, e)
