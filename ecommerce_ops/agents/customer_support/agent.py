"""
Customer Support Agent
Handles customer inquiries, generates responses, and manages ticket lifecycle.
"""

import logging
import time
from datetime import datetime
from typing import Any, Dict, Optional

from ecommerce_ops.agents._base import BaseAgent
from ecommerce_ops.agents.customer_support.models import (
    ResponseSuggestion,
    SupportTicket,
    TicketCategory,
    TicketChannel,
    TicketPriority,
    TicketStatus,
)
from ecommerce_ops.agents.customer_support.response_engine import ResponseGenerationEngine
from ecommerce_ops.agents.customer_support.ticket_router import TicketClassifier
from ecommerce_ops.graph.state import AgentDecision
from ecommerce_ops.utils import utc_now

logger = logging.getLogger("ecommerce_ops.agents.customer_support")


class CustomerSupportAgent(BaseAgent):
    """Agent that handles customer support tickets."""

    def __init__(self):
        super().__init__(agent_name="CustomerSupportAgent")
        self.response_engine = ResponseGenerationEngine()
        self.classifier = TicketClassifier()

    async def run(self, state: Dict[str, Any]) -> Dict[str, Any]:
        """Run the customer support analysis."""
        start_time = time.time()

        # Get tickets from state
        tickets = state.get("support_tickets", [])
        if not tickets:
            logger.info("No support tickets to process")
            return {
                "decisions": [],
                "tickets_processed": 0,
                "tickets_escalated": 0,
                "avg_confidence": 0.0,
            }

        decisions = []
        tickets_escalated = 0
        total_confidence = 0.0

        for ticket_data in tickets:
            try:
                # Parse ticket
                ticket = self._parse_ticket(ticket_data)

                # Process ticket
                decision = await self._process_ticket(ticket)
                if decision:
                    decisions.append(decision)
                    total_confidence += decision.confidence_score

                    if decision.action_data.get("requires_human_review"):
                        tickets_escalated += 1

            except Exception as e:
                logger.error(
                    "Failed to process ticket %s: %s",
                    ticket_data.get("id", "unknown"),
                    e,
                )
                continue

        processing_time = (time.time() - start_time) * 1000
        avg_confidence = total_confidence / len(decisions) if decisions else 0

        # Store decisions in memory
        for decision in decisions:
            await self.persist_decision(decision)

        return {
            "decisions": decisions,
            "tickets_processed": len(tickets),
            "tickets_escalated": tickets_escalated,
            "tickets_resolved": len(tickets) - tickets_escalated,
            "avg_confidence": round(avg_confidence, 3),
            "processing_time_ms": round(processing_time, 2),
        }

    async def _process_ticket(self, ticket: SupportTicket) -> Optional[AgentDecision]:
        """Process a single support ticket."""
        # Classify ticket
        classification = self.classifier.classify_ticket(
            ticket,
            customer_value=ticket.metadata.get("total_spent", 0),
        )

        # Generate response suggestion
        suggestion = self.response_engine.generate_suggestion(
            ticket,
            customer_context=ticket.metadata,
        )

        # Determine action
        requires_human = suggestion.requires_human_review
        confidence = suggestion.confidence

        # Create decision
        action_data = {
            "ticket_id": ticket.id,
            "shop_domain": ticket.shop_domain,
            "customer_email": ticket.customer_email,
            "customer_name": ticket.customer_name,
            "subject": ticket.subject,
            "category": classification["category"],
            "priority": classification["priority"],
            "sla_target_hours": classification["sla_target_hours"],
            "routing": classification["routing"],
            "suggested_response": suggestion.suggested_response,
            "response_confidence": confidence,
            "response_reasoning": suggestion.reasoning,
            "template_used": suggestion.template_used,
            "requires_human_review": requires_human,
            "follow_up_questions": suggestion.follow_up_questions,
            "estimated_resolution_time": suggestion.estimated_resolution_time,
            "sentiment": ticket.sentiment.value if ticket.sentiment else None,
            "channel": ticket.channel.value,
        }

        # Determine reasoning
        reasoning = self._build_reasoning(ticket, classification, suggestion, requires_human)

        # Create decision
        decision = self.create_decision(
            action_type="respond_to_ticket",
            reasoning=reasoning,
            data=action_data,
            confidence=confidence,
            requires_approval=requires_human,
        )

        # Store response suggestion
        await self._store_response_suggestion(ticket.id, suggestion)

        return decision

    def _parse_ticket(self, ticket_data: Dict[str, Any]) -> SupportTicket:
        """Parse raw ticket data into SupportTicket model."""
        # Parse timestamps
        created_at = ticket_data.get("created_at")
        if isinstance(created_at, str):
            created_at = datetime.fromisoformat(created_at.replace("Z", "+00:00"))

        return SupportTicket(
            id=ticket_data.get("id", "unknown"),
            shop_domain=ticket_data.get("shop_domain", "unknown"),
            customer_email=ticket_data.get("customer_email"),
            customer_name=ticket_data.get("customer_name"),
            customer_id=ticket_data.get("customer_id"),
            subject=ticket_data.get("subject", "No Subject"),
            body=ticket_data.get("body", ""),
            category=TicketCategory(ticket_data.get("category", "other")),
            priority=TicketPriority(ticket_data.get("priority", "normal")),
            status=TicketStatus(ticket_data.get("status", "open")),
            channel=TicketChannel(ticket_data.get("channel", "email")),
            order_id=ticket_data.get("order_id"),
            product_id=ticket_data.get("product_id"),
            tags=ticket_data.get("tags", []),
            metadata=ticket_data.get("metadata", {}),
            created_at=created_at or utc_now(),
        )

    def _build_reasoning(
        self,
        ticket: SupportTicket,
        classification: Dict[str, Any],
        suggestion: ResponseSuggestion,
        requires_human: bool,
    ) -> str:
        """Build human-readable reasoning."""
        parts = []

        parts.append(f"Ticket from {ticket.customer_name or ticket.customer_email}")
        parts.append(f"Category: {classification['category']}")
        parts.append(
            f"Priority: {classification['priority']} (SLA: {classification['sla_target_hours']}h)"
        )

        if ticket.sentiment:
            parts.append(f"Sentiment: {ticket.sentiment.value}")

        parts.append(f"Response confidence: {suggestion.confidence:.1%}")

        if suggestion.template_used:
            parts.append(f"Template: {suggestion.template_used}")

        if requires_human:
            parts.append("Requires human review")
        else:
            parts.append("Auto-response recommended")

        return ". ".join(parts)

    async def _store_response_suggestion(self, ticket_id: str, suggestion: ResponseSuggestion):
        """Store response suggestion for later retrieval."""
        # In production, store in database
        logger.debug(
            "Stored response suggestion for ticket %s: confidence=%.2f",
            ticket_id,
            suggestion.confidence,
        )

    async def get_ticket_summary(self, ticket_id: str) -> Dict[str, Any]:
        """Get summary of ticket processing."""
        # In production, query database
        return {
            "ticket_id": ticket_id,
            "status": "processed",
            "category": "general",
            "priority": "normal",
            "response_generated": True,
            "requires_human": False,
        }

    async def update_ticket_status(
        self,
        ticket_id: str,
        status: TicketStatus,
        resolution_notes: Optional[str] = None,
    ) -> bool:
        """Update ticket status."""
        # In production, update database
        logger.info(
            "Ticket %s status updated to %s",
            ticket_id,
            status.value,
        )
        return True

    async def get_support_metrics(self, days: int = 7) -> Dict[str, Any]:
        """Get support metrics for the given period."""
        # In production, query database
        return {
            "period_days": days,
            "total_tickets": 150,
            "resolved_tickets": 120,
            "avg_response_time_hours": 2.5,
            "avg_resolution_time_hours": 8.3,
            "satisfaction_score": 4.2,
            "first_contact_resolution_rate": 0.65,
            "escalation_rate": 0.15,
            "category_breakdown": {
                "order_status": 45,
                "shipping": 30,
                "returns": 25,
                "product_question": 20,
                "technical": 15,
                "other": 15,
            },
        }
