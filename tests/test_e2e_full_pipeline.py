import os

os.environ.setdefault("ENV", "testing")
os.environ.setdefault("API_KEY", "opsiq-dev-key-2024")
os.environ.setdefault("DATABASE_URL", "sqlite+aiosqlite://")
os.environ.setdefault("DEEPSEEK_API_KEY", "sk-test-key")

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient

from ecommerce_ops.api.app import app

AUTH = {"Authorization": "Bearer opsiq-dev-key-2024"}


@pytest_asyncio.fixture(autouse=True)
async def _patch_auth_and_db():
    from sqlalchemy import select
    from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

    from ecommerce_ops.api.auth import verify_auth
    from ecommerce_ops.models.db import (
        StoreSettings,
        engine,
    )
    from ecommerce_ops.security.auth import require_admin, require_auth, role_manager

    mock_admin = MagicMock()
    mock_admin.id = "admin-1"
    mock_admin.is_active = True
    mock_admin.role = MagicMock(value="super_admin")

    original_validate = role_manager.validate_api_key
    role_manager.validate_api_key = AsyncMock(return_value=None)

    app.dependency_overrides[verify_auth] = lambda: "test_operator"
    app.dependency_overrides[require_auth] = lambda: mock_admin
    app.dependency_overrides[require_admin] = lambda: mock_admin

    sf = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)
    async with sf() as session:
        result = await session.execute(select(StoreSettings).where(StoreSettings.id == 1))
        if not result.scalar_one_or_none():
            session.add(StoreSettings(
                id=1, shadow_mode=True, fraud_threshold=70,
                po_limit=1000.0, pricing_limit=5.0, reviews_rating_threshold=4,
            ))
            await session.commit()

    yield

    app.dependency_overrides.pop(verify_auth, None)
    app.dependency_overrides.pop(require_auth, None)
    app.dependency_overrides.pop(require_admin, None)
    role_manager.validate_api_key = original_validate


@pytest.fixture
def transport():
    from ecommerce_ops.api.app import app
    return ASGITransport(app=app)


@pytest.fixture
def client(transport):
    return AsyncClient(
        transport=transport,
        base_url="http://test",
        follow_redirects=True,
        headers=AUTH,
    )


@pytest.mark.asyncio
async def test_full_fraud_pipeline(client):
    from ecommerce_ops.models.db import AsyncSession, async_sessionmaker, engine, get_db_session

    async def override_get_db():
        sf = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)
        async with sf() as session:
            yield session

    app.dependency_overrides[get_db_session] = override_get_db

    with patch("ecommerce_ops.api.app.ws_manager") as mock_ws:
        mock_ws.broadcast = AsyncMock()
        with patch("ecommerce_ops.api.app.task_queue") as mock_tq:
            mock_tq.enqueue = AsyncMock(return_value="task-1")
            resp = await client.post("/api/run")
            assert resp.status_code == 200
            data = resp.json()
            assert "run_id" in data
            assert "task_id" in data

    app.dependency_overrides.pop(get_db_session, None)

    with patch("ecommerce_ops.api.app.get_db_session"):
        resp = await client.get("/api/approvals")
        assert resp.status_code == 200

    with patch("ecommerce_ops.api.app.get_db_session"):
        resp = await client.get("/api/approvals?status=pending&agent=FraudAgent")
        assert resp.status_code == 200


@pytest.mark.asyncio
async def test_shopify_webhook_order_created(client):
    payload = {
        "id": "order-1001",
        "email": "buyer@example.com",
        "total_price": "149.99",
        "currency": "USD",
        "line_items": [
            {"product_id": 1, "title": "Test Product", "quantity": 2, "price": "25.00"}
        ],
        "customer": {"email": "buyer@example.com", "first_name": "Test"},
    }
    with patch("ecommerce_ops.api.shopify.webhook_router.handle_webhook", new_callable=AsyncMock) as mock_handle:
        mock_handle.return_value = {"status": "processed"}
        resp = await client.post(
            "/shopify/webhooks/orders/create",
            json=payload,
            headers={**AUTH, "x-shopify-shop-domain": "test-store.myshopify.com"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "received"
        mock_handle.assert_called_once()


@pytest.mark.asyncio
async def test_fraud_agent_analyze_endpoint():
    from ecommerce_ops.agents.fraud import FraudAgent

    agent = FraudAgent()
    state = {
        "active_orders": [
            {"id": "o_suspicious", "customer": {"email": "suspicious@example.com"}},
            {"id": "o_normal", "customer": {"email": "safe@example.com"}},
        ],
        "decisions": [],
    }
    result = await agent.run(state)
    assert "decisions" in result
    decisions = result["decisions"]
    assert len(decisions) >= 1
    flagged = [d for d in decisions if d.action_type == "HOLD_ORDER"]
    assert len(flagged) >= 1
    for d in flagged:
        assert "risk_score" in d.action_data
        assert "risk_factors" in d.action_data
        assert "order_id" in d.action_data


@pytest.mark.asyncio
async def test_approval_lifecycle(client):
    from datetime import timedelta

    from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

    from ecommerce_ops.models.db import ApprovalAction, engine
    from ecommerce_ops.utils import utc_now

    now = utc_now()
    action_id = "e2e-approval-test-001"

    sf = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)
    async with sf() as session:
        existing = await session.execute(
            __import__("sqlalchemy").select(ApprovalAction).where(ApprovalAction.id == action_id)
        )
        if not existing.scalar_one_or_none():
            session.add(ApprovalAction(
                id=action_id,
                agent="FraudAgent",
                action_type="fraud_hold",
                status="pending",
                risk_level="medium",
                confidence_score=0.80,
                created_at=now,
                expires_at=now + timedelta(hours=23),
                requires_hitl=True,
                shadow_mode=True,
                payload={"order_id": "ORD-TEST-001", "fraud_score": 65, "risk_signals": ["unusual_velocity"]},
                evidence=[{"label": "Risk Score", "value": "65/100", "weight": "primary", "source": "FraudAgent"}],
                impact={"financial_impact": 200.0, "affected_orders": ["ORD-TEST-001"], "reversible": True},
            ))
            await session.commit()

    resp = await client.get(f"/api/approvals/{action_id}")
    assert resp.status_code == 200
    data = resp.json()
    assert data["id"] == action_id
    assert data["status"] == "pending"

    resp = await client.post(f"/api/approvals/{action_id}/approve", json={"notes": "E2E test approval"})
    assert resp.status_code == 200
    approved = resp.json()
    assert approved["id"] == action_id
    assert approved["status"] in ("approved", "executed", "executing")

    resp = await client.get(f"/api/approvals/{action_id}")
    assert resp.status_code == 200
    final = resp.json()
    assert final["status"] != "pending"


@pytest.mark.asyncio
async def test_notification_dispatches_on_high_risk():
    from ecommerce_ops.agents.fraud import FraudAgent

    with patch("ecommerce_ops.agents.fraud.FraudAgent.persist_decision", new_callable=AsyncMock):
        with patch(
            "ecommerce_ops.agents._base.store_decision_memory", new_callable=AsyncMock
        ):
            with patch(
                "ecommerce_ops.agents._base.agent_memory_manager", MagicMock()
            ):
                with patch(
                    "ecommerce_ops.agents._base.memory_retrieval", MagicMock()
                ):
                    with patch(
                        "ecommerce_ops.agents._base.get_recent_memories", new_callable=AsyncMock, return_value=[]
                    ):
                        with patch(
                            "ecommerce_ops.agents._base.get_pattern_insight", new_callable=AsyncMock, return_value=""
                        ):
                            agent = FraudAgent()
                            state = {
                                "active_orders": [
                                    {"id": "o_suspicious", "customer": {"email": "bad@fraud.com"}},
                                ],
                                "decisions": [],
                            }
                            result = await agent.run(state)
                            high_risk = [
                                d for d in result["decisions"]
                                if d.action_data.get("risk_score", 0) >= 70
                            ]
                            assert len(high_risk) >= 1
                            for d in high_risk:
                                assert d.requires_approval is True


@pytest.mark.asyncio
async def test_cart_recovery_analytics_pipeline(client):
    resp = await client.get("/cart-recovery/health")
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "healthy"

    resp = await client.get("/cart-recovery/analytics")
    assert resp.status_code == 200
    data = resp.json()
    assert "total_abandoned" in data
    assert "recovery_rate" in data

    resp = await client.get("/cart-recovery/analytics/strategies")
    assert resp.status_code == 200
    data = resp.json()
    assert "strategies" in data
    assert len(data["strategies"]) > 0


@pytest.mark.asyncio
async def test_support_ticket_lifecycle(client):
    create_resp = await client.post("/support/tickets", json={
        "customer_email": "test@e2e.com",
        "customer_name": "E2E Tester",
        "subject": "E2E integration test ticket",
        "body": "This is an automated e2e test ticket.",
        "channel": "email",
        "order_id": "ORD-E2E-001",
    })
    assert create_resp.status_code == 200
    create_data = create_resp.json()
    assert "ticket_id" in create_data
    assert create_data["status"] == "created"
    ticket_id = create_data["ticket_id"]

    patch_resp = await client.patch(f"/support/tickets/{ticket_id}", json={
        "status": "in_progress",
        "assigned_to": "agent_e2e",
    })
    assert patch_resp.status_code == 200
    patch_data = patch_resp.json()
    assert patch_data["updates"]["status"] == "in_progress"

    respond_resp = await client.post(f"/support/tickets/{ticket_id}/respond", json={
        "ticket_id": ticket_id,
        "response": "This is an automated E2E response.",
        "is_internal": False,
        "send_email": False,
    })
    assert respond_resp.status_code == 200
    respond_data = respond_resp.json()
    assert respond_data["status"] == "response_sent"

    suggest_resp = await client.get(f"/support/tickets/{ticket_id}/suggestion")
    assert suggest_resp.status_code == 200
    suggest_data = suggest_resp.json()
    assert "suggestion" in suggest_data
    assert "response" in suggest_data["suggestion"]
    assert "confidence" in suggest_data["suggestion"]
