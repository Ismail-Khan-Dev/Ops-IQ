"""
Agent Message Bus - Inter-agent communication system.
Enables agents to share insights, coordinate actions, and collaborate.

SCOPE LIMITATION: this bus is IN-PROCESS ONLY — purely asyncio/in-memory with
no Redis or queue backing. Agents coordinate only with other agents running in
the same Python process. If the API/worker is ever scaled to multiple replicas,
messages will NOT fan out across processes; a Redis pub/sub (or equivalent)
backing must be added before running >1 replica. This is a documented scaling
ceiling, not a distributed messaging system.
"""

import asyncio
import logging
import uuid
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Callable, Coroutine, Dict, List, Optional

from ecommerce_ops.utils import utc_now

logger = logging.getLogger("ecommerce_ops.agents.message_bus")


@dataclass
class AgentMessage:
    """Message between agents."""

    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    sender: str = ""
    recipient: Optional[str] = None  # None = broadcast
    message_type: str = "info"  # info, alert, request, response, command
    topic: str = ""
    payload: Dict[str, Any] = field(default_factory=dict)
    priority: int = 0  # Higher = more urgent
    timestamp: datetime = field(default_factory=utc_now)
    requires_response: bool = False
    response_timeout_seconds: float = 30.0
    correlation_id: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "sender": self.sender,
            "recipient": self.recipient,
            "message_type": self.message_type,
            "topic": self.topic,
            "payload": self.payload,
            "priority": self.priority,
            "timestamp": self.timestamp.isoformat(),
            "requires_response": self.requires_response,
            "correlation_id": self.correlation_id,
        }


class AgentMessageBus:
    """
    In-process message bus for inter-agent communication.
    Supports pub/sub, request/response, and direct messaging.
    """

    def __init__(self):
        self._subscribers: Dict[str, List[Callable]] = defaultdict(list)
        self._agent_subscribers: Dict[str, List[Callable]] = defaultdict(list)
        self._message_history: List[AgentMessage] = []
        self._pending_responses: Dict[str, asyncio.Future] = {}
        self._max_history = 1000

    def subscribe(self, topic: str, callback: Callable[[AgentMessage], Coroutine]):
        """Subscribe to a topic."""
        self._subscribers[topic].append(callback)
        logger.debug(f"Subscribed to topic: {topic}")

    def unsubscribe(self, topic: str, callback: Callable):
        """Unsubscribe from a topic."""
        if topic in self._subscribers:
            self._subscribers[topic] = [cb for cb in self._subscribers[topic] if cb != callback]

    def subscribe_agent(self, agent_id: str, callback: Callable[[AgentMessage], Coroutine]):
        """Subscribe to messages for a specific agent."""
        self._agent_subscribers[agent_id].append(callback)
        logger.debug(f"Agent {agent_id} subscribed to direct messages")

    async def publish(self, message: AgentMessage):
        """Publish a message to the bus."""
        self._message_history.append(message)
        if len(self._message_history) > self._max_history:
            self._message_history = self._message_history[-self._max_history :]

        logger.info(
            f"Message published: {message.sender} -> "
            f"{message.recipient or 'broadcast'} [{message.message_type}] "
            f"topic={message.topic}"
        )

        # Deliver to direct recipient
        if message.recipient and message.recipient in self._agent_subscribers:
            for callback in self._agent_subscribers[message.recipient]:
                try:
                    await callback(message)
                except Exception as e:
                    logger.error(f"Error delivering to agent {message.recipient}: {e}")

        # Deliver to topic subscribers
        if message.topic in self._subscribers:
            for callback in self._subscribers[message.topic]:
                try:
                    await callback(message)
                except Exception as e:
                    logger.error(f"Error delivering to topic {message.topic}: {e}")

        # Handle response waiting
        if (
            message.correlation_id
            and message.message_type == "response"
            and message.correlation_id in self._pending_responses
        ):
            future = self._pending_responses[message.correlation_id]
            if not future.done():
                future.set_result(message)

    async def send_direct(
        self,
        sender: str,
        recipient: str,
        payload: Dict[str, Any],
        message_type: str = "info",
        topic: str = "direct",
    ):
        """Send a direct message to a specific agent."""
        message = AgentMessage(
            sender=sender,
            recipient=recipient,
            message_type=message_type,
            topic=topic,
            payload=payload,
        )
        await self.publish(message)

    async def broadcast(
        self,
        sender: str,
        payload: Dict[str, Any],
        message_type: str = "info",
        topic: str = "broadcast",
    ):
        """Broadcast a message to all agents."""
        message = AgentMessage(
            sender=sender,
            recipient=None,
            message_type=message_type,
            topic=topic,
            payload=payload,
        )
        await self.publish(message)

    async def request(
        self, sender: str, recipient: str, payload: Dict[str, Any], timeout: float = 30.0
    ) -> Optional[AgentMessage]:
        """Send a request and wait for response."""
        correlation_id = str(uuid.uuid4())
        future = asyncio.get_running_loop().create_future()
        self._pending_responses[correlation_id] = future

        message = AgentMessage(
            sender=sender,
            recipient=recipient,
            message_type="request",
            topic="request",
            payload=payload,
            requires_response=True,
            response_timeout_seconds=timeout,
            correlation_id=correlation_id,
        )

        await self.publish(message)

        try:
            response = await asyncio.wait_for(future, timeout=timeout)
            return response
        except TimeoutError:
            logger.warning(f"Request from {sender} to {recipient} timed out after {timeout}s")
            return None
        finally:
            self._pending_responses.pop(correlation_id, None)

    def get_history(
        self, agent_id: Optional[str] = None, topic: Optional[str] = None, limit: int = 50
    ) -> List[AgentMessage]:
        """Get message history with optional filters."""
        messages = self._message_history

        if agent_id:
            messages = [m for m in messages if m.sender == agent_id or m.recipient == agent_id]
        if topic:
            messages = [m for m in messages if m.topic == topic]

        return messages[-limit:]

    def get_agent_conversations(self, agent_id: str) -> List[Dict[str, Any]]:
        """Get all conversations involving an agent."""
        messages = [
            m for m in self._message_history if m.sender == agent_id or m.recipient == agent_id
        ]

        conversations = []
        for msg in messages:
            conversations.append(
                {
                    "id": msg.id,
                    "with": msg.recipient if msg.sender == agent_id else msg.sender,
                    "direction": "sent" if msg.sender == agent_id else "received",
                    "type": msg.message_type,
                    "topic": msg.topic,
                    "payload": msg.payload,
                    "timestamp": msg.timestamp.isoformat(),
                }
            )

        return conversations

    def get_stats(self) -> Dict[str, Any]:
        """Get message bus statistics."""
        if not self._message_history:
            return {"total_messages": 0}

        by_type = defaultdict(int)
        by_sender = defaultdict(int)
        by_topic = defaultdict(int)

        for msg in self._message_history:
            by_type[msg.message_type] += 1
            by_sender[msg.sender] += 1
            by_topic[msg.topic] += 1

        return {
            "total_messages": len(self._message_history),
            "by_type": dict(by_type),
            "by_sender": dict(by_sender),
            "by_topic": dict(by_topic),
            "pending_requests": len(self._pending_responses),
            "subscribers": {
                topic: len(callbacks) for topic, callbacks in self._subscribers.items()
            },
        }


# ── Pre-defined Message Topics ────────────────────────────


class MessageTopics:
    """Standard message topics for agent communication."""

    FRAUD_ALERT = "fraud.alert"
    FRAUD_APPROVED = "fraud.approved"
    FRAUD_REJECTED = "fraud.rejected"
    INVENTORY_LOW = "inventory.low"
    INVENTORY_REORDER = "inventory.reorder"
    PRICE_CHANGED = "price.changed"
    PRICE_REVIEW = "price.review"
    REVIEW_RECEIVED = "review.received"
    REVIEW_RESPONSE_NEEDED = "review.response_needed"
    CAMPAIGN_CREATED = "campaign.created"
    CART_ABANDONED = "cart.abandoned"
    CART_RECOVERED = "cart.recovered"
    TICKET_CREATED = "ticket.created"
    TICKET_ESCALATED = "ticket.escalated"
    ORDER_PLACED = "order.placed"
    ORDER_SHIPPED = "order.shipped"
    CUSTOMER_COMPLAINT = "customer.complaint"
    SYSTEM_ALERT = "system.alert"


# Singleton
message_bus = AgentMessageBus()
