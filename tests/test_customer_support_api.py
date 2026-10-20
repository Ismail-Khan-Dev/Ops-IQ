"""Tests for customer_support API routes."""
import os

import pytest
from httpx import ASGITransport, AsyncClient

os.environ.setdefault("ENV", "testing")
os.environ.setdefault("API_KEY", "opsiq-dev-key-2024")
os.environ.setdefault("DATABASE_URL", "sqlite+aiosqlite://")
os.environ.setdefault("DEEPSEEK_API_KEY", "sk-test-key")

from ecommerce_ops.api.app import app

AUTH = {"Authorization": "Bearer opsiq-dev-key-2024"}


@pytest.fixture
def client():
    transport = ASGITransport(app=app)
    return AsyncClient(transport=transport, base_url="http://test", headers=AUTH)


@pytest.mark.asyncio
async def test_create_ticket(client):
    resp = await client.post(
        "/support/tickets",
        json={
            "customer_email": "test@example.com",
            "subject": "Order issue",
            "body": "My order hasn't arrived.",
            "channel": "email",
        },
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "created"
    assert body["ticket_id"].startswith("ticket_")
    assert "classification" in body
    assert "suggestion" in body
    assert "response" in body["suggestion"]
    assert "confidence" in body["suggestion"]


@pytest.mark.asyncio
async def test_create_ticket_with_order(client):
    resp = await client.post(
        "/support/tickets",
        json={
            "customer_email": "jane@example.com",
            "customer_name": "Jane",
            "subject": "Wrong item",
            "body": "I received the wrong product.",
            "channel": "chat",
            "order_id": "ORD-12345",
            "product_id": "PROD-99",
        },
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "created"
    assert "ticket_id" in body


@pytest.mark.asyncio
async def test_list_tickets(client):
    resp = await client.get("/support/tickets")
    assert resp.status_code == 200
    body = resp.json()
    assert "tickets" in body
    assert "total" in body
    assert "page" in body
    assert "limit" in body
    assert body["total"] == 2


@pytest.mark.asyncio
async def test_list_tickets_with_filters(client):
    resp = await client.get(
        "/support/tickets?status=open&priority=high&page=1&limit=10"
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["page"] == 1
    assert body["limit"] == 10


@pytest.mark.asyncio
async def test_get_ticket(client):
    resp = await client.get("/support/tickets/ticket_001")
    assert resp.status_code == 200
    body = resp.json()
    assert body["id"] == "ticket_001"
    assert "subject" in body
    assert "messages" in body
    assert len(body["messages"]) >= 1


@pytest.mark.asyncio
async def test_update_ticket(client):
    resp = await client.patch(
        "/support/tickets/ticket_001",
        json={"status": "in_progress", "priority": "urgent"},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["ticket_id"] == "ticket_001"
    assert body["updates"]["status"] == "in_progress"
    assert body["updates"]["priority"] == "urgent"
    assert "updated_at" in body


@pytest.mark.asyncio
async def test_update_ticket_assignment(client):
    resp = await client.patch(
        "/support/tickets/ticket_001",
        json={"assigned_to": "agent_alice", "resolution_notes": "Escalated to Tier 2"},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["updates"]["assigned_to"] == "agent_alice"
    assert body["updates"]["resolution_notes"] == "Escalated to Tier 2"


@pytest.mark.asyncio
async def test_respond_to_ticket(client):
    resp = await client.post(
        "/support/tickets/ticket_001/respond",
        json={
            "ticket_id": "ticket_001",
            "response": "Your order has been located and will ship tomorrow.",
            "send_email": True,
        },
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "response_sent"
    assert body["ticket_id"] == "ticket_001"
    assert "sent_at" in body


@pytest.mark.asyncio
async def test_respond_to_ticket_no_email(client):
    resp = await client.post(
        "/support/tickets/ticket_002/respond",
        json={
            "ticket_id": "ticket_002",
            "response": "Internal note: follow up Monday.",
            "send_email": False,
        },
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "response_sent"


@pytest.mark.asyncio
async def test_get_response_suggestion(client):
    resp = await client.get("/support/tickets/ticket_001/suggestion")
    assert resp.status_code == 200
    body = resp.json()
    assert body["ticket_id"] == "ticket_001"
    assert "suggestion" in body
    suggestion = body["suggestion"]
    assert "response" in suggestion
    assert "confidence" in suggestion
    assert "requires_human_review" in suggestion
    assert suggestion["requires_human_review"] is True


@pytest.mark.asyncio
async def test_get_support_analytics(client):
    resp = await client.get("/support/analytics?days=30")
    assert resp.status_code == 200
    body = resp.json()
    assert "total_tickets" in body
    assert "open_tickets" in body
    assert "avg_response_time_hours" in body
    assert "satisfaction_score" in body
    assert "category_breakdown" in body
    assert "channel_breakdown" in body
    assert "sentiment_distribution" in body


@pytest.mark.asyncio
async def test_get_agent_performance(client):
    resp = await client.get("/support/analytics/agents")
    assert resp.status_code == 200
    body = resp.json()
    assert "agents" in body
    assert len(body["agents"]) == 2
    assert "team_avg" in body
    agent = body["agents"][0]
    assert "tickets_handled" in agent
    assert "satisfaction_score" in agent


@pytest.mark.asyncio
async def test_customer_support_health(client):
    resp = await client.get("/support/health")
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "healthy"
    assert body["agent"] == "CustomerSupportAgent"
    assert "timestamp" in body
