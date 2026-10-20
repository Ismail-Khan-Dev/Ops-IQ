"""Tests for agents/message_bus.py."""
import pytest

from ecommerce_ops.agents.message_bus import (
    AgentMessage,
    AgentMessageBus,
    MessageTopics,
)


class TestAgentMessage:
    def test_default_values(self):
        msg = AgentMessage()
        assert msg.id is not None
        assert msg.sender == ""
        assert msg.recipient is None
        assert msg.message_type == "info"
        assert msg.priority == 0
        assert msg.requires_response is False

    def test_to_dict(self):
        msg = AgentMessage(sender="agent1", recipient="agent2", topic="test")
        d = msg.to_dict()
        assert d["sender"] == "agent1"
        assert d["recipient"] == "agent2"
        assert d["topic"] == "test"
        assert "timestamp" in d

    def test_custom_values(self):
        msg = AgentMessage(
            sender="a", recipient="b", message_type="alert",
            topic="fraud", priority=10, requires_response=True,
        )
        assert msg.message_type == "alert"
        assert msg.priority == 10
        assert msg.requires_response is True


class TestAgentMessageBus:
    @pytest.fixture
    def bus(self):
        return AgentMessageBus()

    @pytest.mark.asyncio
    async def test_publish_stores_history(self, bus):
        msg = AgentMessage(sender="a", topic="test")
        await bus.publish(msg)
        assert len(bus._message_history) == 1
        assert bus._message_history[0].sender == "a"

    @pytest.mark.asyncio
    async def test_publish_delivers_to_topic_subscribers(self, bus):
        received = []

        async def handler(msg):
            received.append(msg)

        bus.subscribe("fraud.alert", handler)
        msg = AgentMessage(sender="agent1", topic="fraud.alert", message_type="alert")
        await bus.publish(msg)
        assert len(received) == 1
        assert received[0].topic == "fraud.alert"

    @pytest.mark.asyncio
    async def test_publish_delivers_to_direct_recipient(self, bus):
        received = []

        async def handler(msg):
            received.append(msg)

        bus.subscribe_agent("agent2", handler)
        msg = AgentMessage(sender="agent1", recipient="agent2", topic="direct")
        await bus.publish(msg)
        assert len(received) == 1

    @pytest.mark.asyncio
    async def test_unsubscribe(self, bus):
        received = []

        async def handler(msg):
            received.append(msg)

        bus.subscribe("topic1", handler)
        bus.unsubscribe("topic1", handler)
        msg = AgentMessage(sender="a", topic="topic1")
        await bus.publish(msg)
        assert len(received) == 0

    @pytest.mark.asyncio
    async def test_send_direct(self, bus):
        received = []

        async def handler(msg):
            received.append(msg)

        bus.subscribe_agent("target", handler)
        await bus.send_direct("sender", "target", {"key": "value"})
        assert len(received) == 1
        assert received[0].payload == {"key": "value"}

    @pytest.mark.asyncio
    async def test_broadcast(self, bus):
        received_a = []
        received_b = []

        async def handler_a(msg):
            received_a.append(msg)

        async def handler_b(msg):
            received_b.append(msg)

        bus.subscribe("broadcast", handler_a)
        bus.subscribe("broadcast", handler_b)
        await bus.broadcast("sender", {"data": 1})
        assert len(received_a) == 1
        assert len(received_b) == 1

    @pytest.mark.asyncio
    async def test_request_response(self, bus):
        async def responder(msg):
            response = AgentMessage(
                sender=msg.recipient,
                recipient=msg.sender,
                message_type="response",
                topic="response",
                payload={"answer": 42},
                correlation_id=msg.correlation_id,
            )
            await bus.publish(response)

        bus.subscribe_agent("responder", responder)
        response = await bus.request("requester", "responder", {"question": "what?"}, timeout=5.0)
        assert response is not None
        assert response.payload == {"answer": 42}

    @pytest.mark.asyncio
    async def test_request_timeout(self, bus):
        response = await bus.request("a", "nonexistent", {}, timeout=0.1)
        assert response is None

    def test_get_history_empty(self, bus):
        assert bus.get_history() == []

    def test_get_history_with_filter(self, bus):
        bus._message_history = [
            AgentMessage(sender="a", topic="t1"),
            AgentMessage(sender="b", topic="t2"),
            AgentMessage(sender="a", topic="t1"),
        ]
        by_sender = bus.get_history(agent_id="a")
        assert len(by_sender) == 2
        by_topic = bus.get_history(topic="t2")
        assert len(by_topic) == 1

    def test_get_history_limit(self, bus):
        bus._message_history = [AgentMessage(sender="a") for _ in range(100)]
        result = bus.get_history(limit=10)
        assert len(result) == 10

    def test_get_agent_conversations(self, bus):
        bus._message_history = [
            AgentMessage(sender="a", recipient="b", topic="t1"),
            AgentMessage(sender="c", recipient="a", topic="t2"),
        ]
        convos = bus.get_agent_conversations("a")
        assert len(convos) == 2
        assert convos[0]["direction"] == "sent"
        assert convos[1]["direction"] == "received"

    def test_get_stats_empty(self, bus):
        stats = bus.get_stats()
        assert stats["total_messages"] == 0

    def test_get_stats_with_messages(self, bus):
        bus._message_history = [
            AgentMessage(sender="a", message_type="info", topic="t1"),
            AgentMessage(sender="a", message_type="alert", topic="t1"),
            AgentMessage(sender="b", message_type="info", topic="t2"),
        ]
        stats = bus.get_stats()
        assert stats["total_messages"] == 3
        assert stats["by_type"]["info"] == 2
        assert stats["by_sender"]["a"] == 2

    @pytest.mark.asyncio
    async def test_history_max_limit(self, bus):
        bus._max_history = 5
        for i in range(10):
            bus._message_history.append(AgentMessage(sender=f"agent{i}"))
        # Publishing triggers trimming
        await bus.publish(AgentMessage(sender="overflow"))
        assert len(bus._message_history) <= 6  # 5 + the new one


class TestMessageTopics:
    def test_topics_exist(self):
        assert MessageTopics.FRAUD_ALERT == "fraud.alert"
        assert MessageTopics.CART_ABANDONED == "cart.abandoned"
        assert MessageTopics.SYSTEM_ALERT == "system.alert"
