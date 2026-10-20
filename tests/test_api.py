import os
from unittest.mock import AsyncMock, patch

import pytest
from httpx import ASGITransport, AsyncClient

# Set test env before importing app
os.environ.setdefault("ENV", "testing")
os.environ.setdefault("API_KEY", "opsiq-dev-key-2024")
os.environ.setdefault("DATABASE_URL", "sqlite+aiosqlite://")
os.environ.setdefault("DEEPSEEK_API_KEY", "sk-test-key")

from ecommerce_ops.api.app import app


@pytest.fixture
def client():
    transport = ASGITransport(app=app)
    return AsyncClient(
        transport=transport,
        base_url="http://test",
        headers={"Authorization": "Bearer opsiq-dev-key-2024"},
    )


@pytest.mark.asyncio
async def test_health_endpoint(client):
    with patch("ecommerce_ops.api.app.get_db_session"):
        response = await client.get("/health")
        assert response.status_code in (200, 503)
        data = response.json()
        assert "status" in data
        assert "dependencies" in data


@pytest.mark.asyncio
async def test_metrics_endpoint(client):
    response = await client.get("/metrics")
    assert response.status_code == 200
    assert "text/plain" in response.headers.get("content-type", "")


@pytest.mark.asyncio
async def test_approvals_endpoint(client):
    with patch("ecommerce_ops.api.app.get_db_session"):
        response = await client.get("/api/approvals")
        assert response.status_code == 200


@pytest.mark.asyncio
async def test_agents_status_endpoint(client):
    with patch("ecommerce_ops.api.app.get_db_session"):
        response = await client.get("/api/agents/status")
        assert response.status_code == 200


@pytest.mark.asyncio
async def test_analytics_endpoint(client):
    with patch("ecommerce_ops.api.app.get_db_session"):
        response = await client.get("/api/analytics")
        assert response.status_code == 200


@pytest.mark.asyncio
async def test_audit_endpoint(client):
    with patch("ecommerce_ops.api.app.get_db_session"):
        response = await client.get("/api/audit")
        assert response.status_code == 200


@pytest.mark.asyncio
async def test_settings_endpoint(client):
    with patch("ecommerce_ops.api.app.get_db_session"):
        response = await client.get("/api/settings")
        assert response.status_code == 200


@pytest.mark.asyncio
async def test_run_endpoint(client):
    from sqlalchemy import select

    from ecommerce_ops.models.db import (
        AsyncSession,
        StoreSettings,
        async_sessionmaker,
        engine,
        get_db_session,
    )

    async def override_get_db():
        sf = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)
        async with sf() as session:
            result = await session.execute(select(StoreSettings).where(StoreSettings.id == 1))
            if not result.scalar_one_or_none():
                session.add(StoreSettings(
                    id=1, shadow_mode=True, fraud_threshold=70,
                    po_limit=1000.0, pricing_limit=5.0, reviews_rating_threshold=4,
                ))
                await session.commit()
            yield session

    from ecommerce_ops.api.auth import verify_auth
    app.dependency_overrides[get_db_session] = override_get_db
    app.dependency_overrides[verify_auth] = lambda: "test_operator"

    with patch("ecommerce_ops.api.app.ws_manager") as mock_ws:
        mock_ws.broadcast = AsyncMock()
        with patch("ecommerce_ops.api.app.task_queue") as mock_tq:
            mock_tq.enqueue = AsyncMock(return_value="task-1")
            response = await client.post("/api/run")
            assert response.status_code == 200
            data = response.json()
            assert "run_id" in data

    app.dependency_overrides.pop(get_db_session, None)
    app.dependency_overrides.pop(verify_auth, None)
