"""
Ticket Priority and Routing Engine
Automatically classifies, prioritizes, and routes support tickets.
"""

import logging
from typing import Any, ClassVar, Dict, List, Optional

from ecommerce_ops.agents.customer_support.models import (
    EscalationRule,
    SentimentType,
    SupportTicket,
    TicketCategory,
    TicketPriority,
)

logger = logging.getLogger("ecommerce_ops.agents.customer_support.routing")


class CategoryClassifier:
    """Classifies tickets into categories based on content."""

    CATEGORY_KEYWORDS: ClassVar[Dict[TicketCategory, List[str]]] = {
        TicketCategory.ORDER_STATUS: [
            "order",
            "status",
            "tracking",
            "where is",
            "when will",
            "delivery",
            "shipped",
            "processing",
            "confirmed",
        ],
        TicketCategory.SHIPPING: [
            "shipping",
            "delivery",
            "carrier",
            "usps",
            "ups",
            "fedex",
            "tracking number",
            "package",
            "lost",
            "delayed",
        ],
        TicketCategory.RETURNS: [
            "return",
            "send back",
            "exchange",
            "wrong size",
            "wrong item",
            "doesn't fit",
            "not as described",
            "defective",
        ],
        TicketCategory.REFUNDS: [
            "refund",
            "money back",
            "charge",
            "credit",
            "reimbursement",
            "overcharged",
            "double charged",
            "billing error",
        ],
        TicketCategory.PRODUCT_QUESTION: [
            "question",
            "how to",
            "what is",
            "specification",
            "compatible",
            "size",
            "color",
            "material",
            "dimensions",
            "features",
        ],
        TicketCategory.COMPLAINT: [
            "complaint",
            "unhappy",
            "terrible",
            "worst",
            "never again",
            "disappointed",
            "frustrated",
            "angry",
            "unacceptable",
        ],
        TicketCategory.TECHNICAL: [
            "error",
            "bug",
            "crash",
            "not working",
            "broken",
            "issue",
            "problem",
            "trouble",
            "help",
            "support",
            "technical",
        ],
        TicketCategory.ACCOUNT: [
            "account",
            "login",
            "password",
            "email",
            "profile",
            "settings",
            "unsubscribe",
            "delete account",
        ],
        TicketCategory.BILLING: [
            "billing",
            "invoice",
            "payment",
            "charge",
            "subscription",
            "cancel",
            "plan",
            "price",
            "discount",
        ],
    }

    def classify(self, ticket: SupportTicket) -> TicketCategory:
        """Classify ticket into category based on content."""
        text = f"{ticket.subject} {ticket.body}".lower()

        # Score each category
        scores = {}
        for category, keywords in self.CATEGORY_KEYWORDS.items():
            score = sum(1 for kw in keywords if kw in text)
            if score > 0:
                scores[category] = score

        if not scores:
            return TicketCategory.OTHER

        # Return highest scoring category
        return max(scores, key=scores.get)


class PriorityAssigner:
    """Assigns priority based on multiple factors."""

    # SLA targets in hours
    SLA_TARGETS: ClassVar[Dict[TicketPriority, int]] = {
        TicketPriority.CRITICAL: 1,
        TicketPriority.URGENT: 4,
        TicketPriority.HIGH: 8,
        TicketPriority.NORMAL: 24,
        TicketPriority.LOW: 48,
    }

    # Category base priorities
    CATEGORY_BASE_PRIORITY: ClassVar[Dict[TicketCategory, TicketPriority]] = {
        TicketCategory.COMPLAINT: TicketPriority.HIGH,
        TicketCategory.REFUNDS: TicketPriority.HIGH,
        TicketCategory.TECHNICAL: TicketPriority.NORMAL,
        TicketCategory.ORDER_STATUS: TicketPriority.NORMAL,
        TicketCategory.SHIPPING: TicketPriority.NORMAL,
        TicketCategory.RETURNS: TicketPriority.NORMAL,
        TicketCategory.PRODUCT_QUESTION: TicketPriority.LOW,
        TicketCategory.ACCOUNT: TicketPriority.NORMAL,
        TicketCategory.BILLING: TicketPriority.HIGH,
        TicketCategory.OTHER: TicketPriority.NORMAL,
    }

    def assign_priority(
        self,
        ticket: SupportTicket,
        sentiment: Optional[SentimentType] = None,
        customer_value: float = 0.0,
    ) -> TicketPriority:
        """Assign priority based on multiple factors."""
        base_priority = self.CATEGORY_BASE_PRIORITY.get(ticket.category, TicketPriority.NORMAL)

        # Boost priority based on sentiment
        if sentiment in (SentimentType.VERY_NEGATIVE, SentimentType.NEGATIVE):
            base_priority = self._boost_priority(base_priority, 1)

        # Boost for VIP/high-value customers
        if customer_value > 500:
            base_priority = self._boost_priority(base_priority, 2)
        elif customer_value > 100:
            base_priority = self._boost_priority(base_priority, 1)

        # Check for urgency keywords
        urgency_words = ["urgent", "asap", "immediately", "emergency", "critical"]
        text = f"{ticket.subject} {ticket.body}".lower()
        if any(w in text for w in urgency_words):
            base_priority = self._boost_priority(base_priority, 1)

        # Check for legal/threats
        threat_words = ["legal", "attorney", "lawsuit", "media", "social media"]
        if any(w in text for w in threat_words):
            base_priority = TicketPriority.CRITICAL

        return base_priority

    def get_sla_target(self, priority: TicketPriority) -> int:
        """Get SLA target hours for priority."""
        return self.SLA_TARGETS.get(priority, 24)

    def _boost_priority(self, current: TicketPriority, levels: int) -> TicketPriority:
        """Boost priority by number of levels."""
        priorities = [
            TicketPriority.LOW,
            TicketPriority.NORMAL,
            TicketPriority.HIGH,
            TicketPriority.URGENT,
            TicketPriority.CRITICAL,
        ]
        current_idx = priorities.index(current)
        new_idx = min(current_idx + levels, len(priorities) - 1)
        return priorities[new_idx]


class TicketRouter:
    """Routes tickets to appropriate agents/queues."""

    def __init__(self):
        self._queues: Dict[str, List[str]] = {}
        self._agent_workload: Dict[str, int] = {}
        self._escalation_rules: List[EscalationRule] = []

    def route_ticket(
        self,
        ticket: SupportTicket,
        available_agents: List[Dict[str, Any]] | None = None,
    ) -> Dict[str, Any]:
        """Route ticket to appropriate queue/agent."""
        # Check escalation rules
        escalation = self._check_escalation_rules(ticket)
        if escalation:
            return {
                "action": escalation["action"],
                "target_queue": escalation.get("target_queue"),
                "target_agent": escalation.get("target_agent"),
                "reason": f"Matched escalation rule: {escalation['name']}",
            }

        # Route based on category
        queue = self._get_queue_for_category(ticket.category)

        # Select best agent if available
        agent = None
        if available_agents:
            agent = self._select_best_agent(ticket, available_agents)

        return {
            "action": "route",
            "target_queue": queue,
            "target_agent": agent["id"] if agent else None,
            "reason": f"Routed to {queue} queue"
            + (f", assigned to {agent['name']}" if agent else ""),
        }

    def add_escalation_rule(self, rule: EscalationRule):
        """Add an escalation rule."""
        self._escalation_rules.append(rule)

    def get_queue_depth(self, queue: str) -> int:
        """Get number of tickets in a queue."""
        return len(self._queues.get(queue, []))

    def add_to_queue(self, queue: str, ticket_id: str):
        """Add ticket to queue."""
        if queue not in self._queues:
            self._queues[queue] = []
        self._queues[queue].append(ticket_id)

    def remove_from_queue(self, queue: str, ticket_id: str):
        """Remove ticket from queue."""
        if queue in self._queues:
            self._queues[queue] = [t for t in self._queues[queue] if t != ticket_id]

    def get_agent_workload(self, agent_id: str) -> int:
        """Get agent's current workload."""
        return self._agent_workload.get(agent_id, 0)

    def update_agent_workload(self, agent_id: str, delta: int):
        """Update agent workload."""
        current = self._agent_workload.get(agent_id, 0)
        self._agent_workload[agent_id] = max(0, current + delta)

    def _check_escalation_rules(self, ticket: SupportTicket) -> Optional[Dict[str, Any]]:
        """Check if any escalation rules match."""
        for rule in self._escalation_rules:
            if not rule.is_active:
                continue

            if self._rule_matches(ticket, rule):
                return {
                    "name": rule.name,
                    "action": rule.action,
                    "target_queue": rule.target_queue,
                    "target_agent": rule.target_agent,
                }
        return None

    def _rule_matches(self, ticket: SupportTicket, rule: EscalationRule) -> bool:
        """Check if ticket matches escalation rule conditions."""
        conditions = rule.conditions

        # Check priority
        if "min_priority" in conditions:
            priority_order = [
                TicketPriority.LOW,
                TicketPriority.NORMAL,
                TicketPriority.HIGH,
                TicketPriority.URGENT,
                TicketPriority.CRITICAL,
            ]
            min_prio = TicketPriority(conditions["min_priority"])
            if priority_order.index(ticket.priority) < priority_order.index(min_prio):
                return False

        # Check category
        if "categories" in conditions and ticket.category.value not in conditions["categories"]:
            return False

        # Check sentiment
        if "sentiment" in conditions and (
            ticket.sentiment and ticket.sentiment.value != conditions["sentiment"]
        ):
            return False

        # Check keywords
        if "keywords" in conditions:
            text = f"{ticket.subject} {ticket.body}".lower()
            if not any(kw.lower() in text for kw in conditions["keywords"]):
                return False

        return True

    def _get_queue_for_category(self, category: TicketCategory) -> str:
        """Map category to queue name."""
        queue_map = {
            TicketCategory.ORDER_STATUS: "orders",
            TicketCategory.SHIPPING: "shipping",
            TicketCategory.RETURNS: "returns",
            TicketCategory.REFUNDS: "refunds",
            TicketCategory.PRODUCT_QUESTION: "general",
            TicketCategory.COMPLAINT: "escalated",
            TicketCategory.TECHNICAL: "technical",
            TicketCategory.ACCOUNT: "account",
            TicketCategory.BILLING: "billing",
            TicketCategory.OTHER: "general",
        }
        return queue_map.get(category, "general")

    def _select_best_agent(
        self,
        ticket: SupportTicket,
        available_agents: List[Dict[str, Any]],
    ) -> Optional[Dict[str, Any]]:
        """Select best agent based on workload and expertise."""
        if not available_agents:
            return None

        # Filter by expertise
        category_expertise = {
            TicketCategory.TECHNICAL: "technical",
            TicketCategory.BILLING: "billing",
            TicketCategory.RETURNS: "returns",
            TicketCategory.REFUNDS: "refunds",
        }

        required_expertise = category_expertise.get(ticket.category)

        # Score agents
        scored_agents = []
        for agent in available_agents:
            score = 0

            # Expertise match
            if required_expertise and required_expertise in agent.get("skills", []):
                score += 10

            # Workload (lower is better)
            workload = self._agent_workload.get(agent["id"], 0)
            score -= workload

            # Rating (higher is better)
            score += agent.get("rating", 0) * 2

            scored_agents.append((score, agent))

        # Return highest scoring agent
        scored_agents.sort(key=lambda x: x[0], reverse=True)
        return scored_agents[0][1] if scored_agents else None


class TicketClassifier:
    """Combined classifier for category, priority, and routing."""

    def __init__(self):
        self.category_classifier = CategoryClassifier()
        self.priority_assigner = PriorityAssigner()
        self.router = TicketRouter()

    def classify_ticket(
        self,
        ticket: SupportTicket,
        customer_value: float = 0.0,
        available_agents: List[Dict[str, Any]] | None = None,
    ) -> Dict[str, Any]:
        """Full ticket classification pipeline."""
        # Classify category
        category = self.category_classifier.classify(ticket)
        ticket.category = category

        # Assign priority
        priority = self.priority_assigner.assign_priority(ticket, ticket.sentiment, customer_value)
        ticket.priority = priority

        # Get SLA target
        sla_hours = self.priority_assigner.get_sla_target(priority)

        # Route ticket
        routing = self.router.route_ticket(ticket, available_agents)

        return {
            "category": category.value,
            "priority": priority.value,
            "sla_target_hours": sla_hours,
            "routing": routing,
        }
