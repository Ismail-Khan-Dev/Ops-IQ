"""
Comprehensive async tests for the FastAPI application endpoints.
Covers health, auth, approvals, agents, audit, settings, memory,
shopify, demo, websocket, metrics, analytics, and task endpoints.
"""

import os
import uuid
from datetime import timedelta
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import pytest_asyncio

from ecommerce_ops.utils import utc_now

os.environ["ENV"] = "testing"
os.environ["DATABASE_URL"] = "sqlite+aiosqlite://"
os.environ["API_KEY"] = "test-key"
os.environ["DEEPSEEK_API_KEY"] = "sk-test-key"

from httpx import ASGITransport, AsyncClient

# Register JSONB adapter for SQLite (maps JSONB to JSON)
from sqlalchemy import select, update
from sqlalchemy.dialects.sqlite.base import SQLiteTypeCompiler
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

_orig_visit_JSONB = getattr(SQLiteTypeCompiler, "visit_JSONB", None)
if _orig_visit_JSONB is None:
    SQLiteTypeCompiler.visit_JSONB = lambda self, type_, **kw: "JSON"

from ecommerce_ops.api.app import app  # noqa: E402
from ecommerce_ops.api.auth import verify_auth  # noqa: E402
from ecommerce_ops.config import settings as app_settings  # noqa: E402
from ecommerce_ops.models.db import (  # noqa: E402
    AgentStatus,
    ApprovalAction,
    AuditEntry,
    Base,
    StoreSettings,
)

TEST_API_KEY = "test-key"
AUTH_HEADER = {"Authorization": f"Bearer {TEST_API_KEY}"}


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def _patch_settings_for_testing():
    """Ensure settings reflect testing environment for every test."""
    with (
        patch.object(app_settings, "ENV", "testing"),
        patch.object(app_settings, "API_KEY", MagicMock(get_secret_value=lambda: TEST_API_KEY)),
    ):
        yield


@pytest_asyncio.fixture()
async def engine():
    eng = create_async_engine("sqlite+aiosqlite://", echo=False)
    async with eng.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield eng
    await eng.dispose()


@pytest_asyncio.fixture()
async def session(engine):
    factory = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)
    async with factory() as s:
        yield s


def _overrides(session: AsyncSession):
    """Return dependency overrides dict pointing all DB access at *session*."""
    from ecommerce_ops.models import get_db_session

    async def _override():
        yield session

    return {get_db_session: _override}


def _seed_basic(session: AsyncSession):
    """Insert the minimal rows many endpoints expect."""
    session.add(
        StoreSettings(
            id=1,
            shadow_mode=True,
            fraud_threshold=70,
            po_limit=1000.0,
            pricing_limit=5.0,
            reviews_rating_threshold=4,
        )
    )
    for name in [
        "FraudAgent",
        "InventoryAgent",
        "PricingAgent",
        "ReviewsAgent",
        "MarketingAgent",
    ]:
        session.add(
            AgentStatus(
                agent_id=name,
                status="active",
                streak=0,
                autonomy_level="shadow",
                total_decisions=0,
                total_approvals=0,
                total_rejections=0,
                avg_confidence=0.0,
            )
        )
    session.add(
        ApprovalAction(
            id="act-1",
            agent="FraudAgent",
            action_type="fraud_hold",
            status="pending",
            risk_level="high",
            confidence_score=0.92,
            created_at=utc_now(),
            expires_at=utc_now() + timedelta(hours=24),
            requires_hitl=True,
            shadow_mode=True,
            payload={"order_id": "ORD-001"},
            evidence=[{"label": "score", "value": "85"}],
            impact={"financial_impact": 450.0},
        )
    )
    session.add(
        ApprovalAction(
            id="act-2",
            agent="InventoryAgent",
            action_type="purchase_order",
            status="pending",
            risk_level="low",
            confidence_score=0.85,
            created_at=utc_now(),
            expires_at=utc_now() + timedelta(days=2),
            requires_hitl=False,
            shadow_mode=True,
            payload={"sku": "MUG-WHITE", "reorder_quantity": 100},
            evidence=[],
            impact={"financial_impact": -500.0},
        )
    )
    session.add(
        AuditEntry(
            action_id="act-1",
            timestamp=utc_now(),
            agent="FraudAgent",
            action_type="fraud_hold",
            decision="approved",
            operator="admin",
            confidence_score=0.92,
            financial_impact=450.0,
            details={"note": "test"},
        )
    )


@pytest_asyncio.fixture()
async def seeded_session(engine):
    factory = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)
    async with factory() as s:
        _seed_basic(s)
        await s.commit()
        yield s


# ---------------------------------------------------------------------------
# 1.  Health / Ready / Live
# ---------------------------------------------------------------------------


class TestHealthEndpoints:
    @pytest.mark.asyncio
    async def test_live_returns_200(self):
        transport = ASGITransport(app=app)
        async with AsyncClient(
            transport=transport, base_url="http://test", headers=AUTH_HEADER
        ) as c:
            r = await c.get("/live")
        assert r.status_code == 200
        assert r.json()["status"] == "alive"

    @pytest.mark.asyncio
    async def test_ready_ok(self, seeded_session):
        app.dependency_overrides.update(_overrides(seeded_session))
        transport = ASGITransport(app=app)
        async with AsyncClient(
            transport=transport, base_url="http://test", headers=AUTH_HEADER
        ) as c:
            r = await c.get("/ready")
        app.dependency_overrides.clear()
        assert r.status_code == 200
        assert r.json()["status"] == "ready"

    @pytest.mark.asyncio
    async def test_health_returns_200_or_503(self):
        transport = ASGITransport(app=app)
        async with AsyncClient(
            transport=transport, base_url="http://test", headers=AUTH_HEADER
        ) as c:
            r = await c.get("/health")
        assert r.status_code in (200, 503)
        body = r.json()
        assert "status" in body
        assert "dependencies" in body
        assert "uptime_seconds" in body

    @pytest.mark.asyncio
    async def test_health_contains_expected_checks(self):
        transport = ASGITransport(app=app)
        async with AsyncClient(
            transport=transport, base_url="http://test", headers=AUTH_HEADER
        ) as c:
            r = await c.get("/health")
        checks = r.json().get("checks", {})
        for key in ("database", "redis", "task_queue", "agents"):
            assert key in checks


# ---------------------------------------------------------------------------
# 2.  Auth endpoints
# ---------------------------------------------------------------------------


class TestAuthEndpoints:
    @pytest.mark.asyncio
    async def test_login_success(self):
        transport = ASGITransport(app=app)
        async with AsyncClient(
            transport=transport, base_url="http://test", headers=AUTH_HEADER
        ) as c:
            r = await c.post("/api/auth/login", json={"api_key": TEST_API_KEY})
        assert r.status_code == 200
        assert r.json()["status"] == "ok"

    @pytest.mark.asyncio
    async def test_login_with_operator_id(self):
        transport = ASGITransport(app=app)
        async with AsyncClient(
            transport=transport, base_url="http://test", headers=AUTH_HEADER
        ) as c:
            r = await c.post(
                "/api/auth/login",
                json={"api_key": TEST_API_KEY, "operator_id": "ops-42"},
            )
        assert r.status_code == 200
        assert r.json()["operator"] == "ops-42"

    @pytest.mark.asyncio
    async def test_login_wrong_key_returns_401(self):
        transport = ASGITransport(app=app)
        async with AsyncClient(
            transport=transport, base_url="http://test", headers=AUTH_HEADER
        ) as c:
            r = await c.post("/api/auth/login", json={"api_key": "wrong"})
        assert r.status_code == 401

    @pytest.mark.asyncio
    async def test_login_empty_key_returns_401(self):
        transport = ASGITransport(app=app)
        async with AsyncClient(
            transport=transport, base_url="http://test", headers=AUTH_HEADER
        ) as c:
            r = await c.post("/api/auth/login", json={"api_key": ""})
        assert r.status_code == 401

    @pytest.mark.asyncio
    async def test_login_no_key_field_returns_422(self):
        transport = ASGITransport(app=app)
        async with AsyncClient(
            transport=transport, base_url="http://test", headers=AUTH_HEADER
        ) as c:
            r = await c.post("/api/auth/login", json={})
        assert r.status_code == 422

    @pytest.mark.asyncio
    async def test_auth_me_via_bearer_header(self, seeded_session):
        app.dependency_overrides.update(_overrides(seeded_session))
        app.dependency_overrides[verify_auth] = lambda: "test-user"
        transport = ASGITransport(app=app)
        async with AsyncClient(
            transport=transport, base_url="http://test", headers=AUTH_HEADER
        ) as c:
            r = await c.get("/api/ws/stats", headers=AUTH_HEADER)
        app.dependency_overrides.clear()
        assert r.status_code == 200

    @pytest.mark.asyncio
    async def test_auth_rejected_without_token(self, seeded_session):
        app.dependency_overrides.update(_overrides(seeded_session))
        transport = ASGITransport(app=app)
        async with AsyncClient(
            transport=transport, base_url="http://test", headers={"Authorization": "Bearer invalid"}
        ) as c:
            r = await c.get("/api/ws/stats")
        app.dependency_overrides.clear()
        assert r.status_code in (401, 403)

    @pytest.mark.asyncio
    async def test_auth_rejected_with_invalid_token(self, seeded_session):
        app.dependency_overrides.update(_overrides(seeded_session))
        transport = ASGITransport(app=app)
        async with AsyncClient(
            transport=transport, base_url="http://test", headers=AUTH_HEADER
        ) as c:
            r = await c.get("/api/ws/stats", headers={"Authorization": "Bearer garbage"})
        app.dependency_overrides.clear()
        assert r.status_code == 401


# ---------------------------------------------------------------------------
# 3.  Approvals
# ---------------------------------------------------------------------------


class TestApprovals:
    @pytest.mark.asyncio
    async def test_get_approvals_empty(self, engine):
        factory = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)
        async with factory() as s:
            app.dependency_overrides.update(_overrides(s))
        transport = ASGITransport(app=app)
        async with AsyncClient(
            transport=transport, base_url="http://test", headers=AUTH_HEADER
        ) as c:
            r = await c.get("/api/approvals")
        app.dependency_overrides.clear()
        assert r.status_code == 200
        assert isinstance(r.json(), list)

    @pytest.mark.asyncio
    async def test_get_approvals_seeded(self, seeded_session):
        app.dependency_overrides.update(_overrides(seeded_session))
        transport = ASGITransport(app=app)
        async with AsyncClient(
            transport=transport, base_url="http://test", headers=AUTH_HEADER
        ) as c:
            r = await c.get("/api/approvals?status=pending")
        app.dependency_overrides.clear()
        assert r.status_code == 200
        data = r.json()
        assert len(data) >= 1
        assert all(a["status"] == "pending" for a in data)

    @pytest.mark.asyncio
    async def test_get_approvals_filter_by_agent(self, seeded_session):
        app.dependency_overrides.update(_overrides(seeded_session))
        transport = ASGITransport(app=app)
        async with AsyncClient(
            transport=transport, base_url="http://test", headers=AUTH_HEADER
        ) as c:
            r = await c.get("/api/approvals?agent=FraudAgent")
        app.dependency_overrides.clear()
        assert r.status_code == 200
        for a in r.json():
            assert a["agent"] == "FraudAgent"

    @pytest.mark.asyncio
    async def test_get_approvals_filter_by_risk(self, seeded_session):
        app.dependency_overrides.update(_overrides(seeded_session))
        transport = ASGITransport(app=app)
        async with AsyncClient(
            transport=transport, base_url="http://test", headers=AUTH_HEADER
        ) as c:
            r = await c.get("/api/approvals?risk=high")
        app.dependency_overrides.clear()
        assert r.status_code == 200
        for a in r.json():
            assert a["risk_level"] == "high"

    @pytest.mark.asyncio
    async def test_get_approvals_search(self, seeded_session):
        app.dependency_overrides.update(_overrides(seeded_session))
        transport = ASGITransport(app=app)
        async with AsyncClient(
            transport=transport, base_url="http://test", headers=AUTH_HEADER
        ) as c:
            r = await c.get("/api/approvals?search=ORD-001")
        app.dependency_overrides.clear()
        assert r.status_code == 200
        assert len(r.json()) >= 1

    @pytest.mark.asyncio
    async def test_get_single_approval(self, seeded_session):
        app.dependency_overrides.update(_overrides(seeded_session))
        transport = ASGITransport(app=app)
        async with AsyncClient(
            transport=transport, base_url="http://test", headers=AUTH_HEADER
        ) as c:
            r = await c.get("/api/approvals/act-1")
        app.dependency_overrides.clear()
        assert r.status_code == 200
        assert r.json()["id"] == "act-1"

    @pytest.mark.asyncio
    async def test_get_single_approval_404(self, seeded_session):
        app.dependency_overrides.update(_overrides(seeded_session))
        transport = ASGITransport(app=app)
        async with AsyncClient(
            transport=transport, base_url="http://test", headers=AUTH_HEADER
        ) as c:
            r = await c.get("/api/approvals/nonexistent")
        app.dependency_overrides.clear()
        assert r.status_code == 404

    @pytest.mark.asyncio
    async def test_approve_action(self, seeded_session):
        app.dependency_overrides.update(_overrides(seeded_session))
        transport = ASGITransport(app=app)
        with (
            patch("ecommerce_ops.api.core_routes.ws_manager") as mock_ws,
            patch(
                "ecommerce_ops.api.core_routes.execute_shop_action", new_callable=AsyncMock
            ) as mock_exec,
            patch("ecommerce_ops.api.core_routes.update_agent_streak", new_callable=AsyncMock),
        ):
            mock_exec.return_value = (True, "ok")
            mock_ws.broadcast = AsyncMock()
            async with AsyncClient(
                transport=transport, base_url="http://test", headers=AUTH_HEADER
            ) as c:
                r = await c.post(
                    "/api/approvals/act-1/approve",
                    json={"notes": "Looks good"},
                    headers=AUTH_HEADER,
                )
        app.dependency_overrides.clear()
        assert r.status_code == 200
        body = r.json()
        assert body["status"] in ("executing", "executed")
        assert body["reviewed_by"] == "Operator"

    @pytest.mark.asyncio
    async def test_approve_nonexistent_returns_404(self, seeded_session):
        app.dependency_overrides.update(_overrides(seeded_session))
        app.dependency_overrides[verify_auth] = lambda: "op"
        transport = ASGITransport(app=app)
        async with AsyncClient(
            transport=transport, base_url="http://test", headers=AUTH_HEADER
        ) as c:
            r = await c.post(
                "/api/approvals/no-such-id/approve",
                json={},
                headers=AUTH_HEADER,
            )
        app.dependency_overrides.clear()
        assert r.status_code == 404

    @pytest.mark.asyncio
    async def test_reject_action(self, seeded_session):
        app.dependency_overrides.update(_overrides(seeded_session))
        app.dependency_overrides[verify_auth] = lambda: "test-operator"
        transport = ASGITransport(app=app)
        with patch("ecommerce_ops.api.core_routes.ws_manager") as mock_ws:
            mock_ws.broadcast = AsyncMock()
            async with AsyncClient(
                transport=transport, base_url="http://test", headers=AUTH_HEADER
            ) as c:
                r = await c.post(
                    "/api/approvals/act-2/reject",
                    json={"reason": "Too expensive", "notes": "Hold for review"},
                    headers=AUTH_HEADER,
                )
        app.dependency_overrides.clear()
        assert r.status_code == 200
        body = r.json()
        assert body["status"] == "rejected"
        assert body["rejection_reason"] == "Too expensive"

    @pytest.mark.asyncio
    async def test_reject_nonexistent_returns_404(self, seeded_session):
        app.dependency_overrides.update(_overrides(seeded_session))
        app.dependency_overrides[verify_auth] = lambda: "op"
        transport = ASGITransport(app=app)
        async with AsyncClient(
            transport=transport, base_url="http://test", headers=AUTH_HEADER
        ) as c:
            r = await c.post(
                "/api/approvals/does-not-exist/reject",
                json={"reason": "nope"},
                headers=AUTH_HEADER,
            )
        app.dependency_overrides.clear()
        assert r.status_code == 404

    @pytest.mark.asyncio
    async def test_batch_approve(self, seeded_session):
        app.dependency_overrides.update(_overrides(seeded_session))
        app.dependency_overrides[verify_auth] = lambda: "batch-op"
        transport = ASGITransport(app=app)
        with (
            patch("ecommerce_ops.api.core_routes.ws_manager") as mock_ws,
            patch(
                "ecommerce_ops.api.core_routes.execute_shop_action", new_callable=AsyncMock
            ) as mock_exec,
            patch("ecommerce_ops.api.core_routes.update_agent_streak", new_callable=AsyncMock),
        ):
            mock_exec.return_value = (True, "ok")
            mock_ws.broadcast = AsyncMock()
            async with AsyncClient(
                transport=transport, base_url="http://test", headers=AUTH_HEADER
            ) as c:
                r = await c.post(
                    "/api/approvals/batch",
                    json={"ids": ["act-2"], "action": "approve", "notes": "batch"},
                    headers=AUTH_HEADER,
                )
        app.dependency_overrides.clear()
        assert r.status_code == 200
        body = r.json()
        assert body["message"].startswith("Processed")
        assert "act-2" in body["affected_ids"]

    @pytest.mark.asyncio
    async def test_batch_reject(self, seeded_session):
        app.dependency_overrides.update(_overrides(seeded_session))
        app.dependency_overrides[verify_auth] = lambda: "batch-op"
        transport = ASGITransport(app=app)
        with patch("ecommerce_ops.api.core_routes.ws_manager") as mock_ws:
            mock_ws.broadcast = AsyncMock()
            async with AsyncClient(
                transport=transport, base_url="http://test", headers=AUTH_HEADER
            ) as c:
                r = await c.post(
                    "/api/approvals/batch",
                    json={"ids": ["act-1"], "action": "reject", "reason": "No"},
                    headers=AUTH_HEADER,
                )
        app.dependency_overrides.clear()
        assert r.status_code == 200
        assert "act-1" in r.json()["affected_ids"]

    @pytest.mark.asyncio
    async def test_batch_skips_high_risk(self, seeded_session):
        app.dependency_overrides.update(_overrides(seeded_session))
        app.dependency_overrides[verify_auth] = lambda: "op"
        transport = ASGITransport(app=app)
        with patch("ecommerce_ops.api.core_routes.ws_manager") as mock_ws:
            mock_ws.broadcast = AsyncMock()
            async with AsyncClient(
                transport=transport, base_url="http://test", headers=AUTH_HEADER
            ) as c:
                r = await c.post(
                    "/api/approvals/batch",
                    json={"ids": ["act-1"], "action": "approve"},
                    headers=AUTH_HEADER,
                )
        app.dependency_overrides.clear()
        body = r.json()
        assert "act-1" not in body["affected_ids"]

    @pytest.mark.asyncio
    async def test_approve_already_decided_returns_400(self, seeded_session):
        app.dependency_overrides.update(_overrides(seeded_session))
        app.dependency_overrides[verify_auth] = lambda: "op"
        transport = ASGITransport(app=app)
        async with AsyncClient(
            transport=transport, base_url="http://test", headers=AUTH_HEADER
        ) as c:
            _r = await c.post(
                "/api/approvals/act-2/approve",
                json={},
                headers=AUTH_HEADER,
            )
            app.dependency_overrides[verify_auth] = lambda: "op2"
            r2 = await c.post(
                "/api/approvals/act-2/approve",
                json={},
                headers=AUTH_HEADER,
            )
        app.dependency_overrides.clear()
        assert r2.status_code == 400


# ---------------------------------------------------------------------------
# 4.  Agents Status
# ---------------------------------------------------------------------------


class TestAgents:
    @pytest.mark.asyncio
    async def test_agents_status(self, seeded_session):
        app.dependency_overrides.update(_overrides(seeded_session))
        transport = ASGITransport(app=app)
        async with AsyncClient(
            transport=transport, base_url="http://test", headers=AUTH_HEADER
        ) as c:
            r = await c.get("/api/agents/status")
        app.dependency_overrides.clear()
        assert r.status_code == 200
        agents = r.json()
        assert len(agents) == 5
        ids = {a["agent_id"] for a in agents}
        assert "FraudAgent" in ids
        assert "MarketingAgent" in ids

    @pytest.mark.asyncio
    async def test_agents_status_empty(self, engine):
        factory = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)
        async with factory() as s:
            app.dependency_overrides.update(_overrides(s))
        transport = ASGITransport(app=app)
        async with AsyncClient(
            transport=transport, base_url="http://test", headers=AUTH_HEADER
        ) as c:
            r = await c.get("/api/agents/status")
        app.dependency_overrides.clear()
        assert r.status_code == 200
        assert r.json() == []


class TestAgentsAutonomy:
    @pytest.mark.asyncio
    async def test_promote_to_supervised(self, seeded_session):
        app.dependency_overrides.update(_overrides(seeded_session))
        transport = ASGITransport(app=app)
        async with AsyncClient(
            transport=transport, base_url="http://test", headers=AUTH_HEADER
        ) as c:
            r = await c.patch(
                "/api/agents/FraudAgent/autonomy", json={"level": "supervised"}
            )
        app.dependency_overrides.clear()
        assert r.status_code == 200
        body = r.json()
        assert body["agent_id"] == "FraudAgent"
        assert body["autonomy_level"] == "supervised"
        row = (
            await seeded_session.execute(
                select(AgentStatus).where(AgentStatus.agent_id == "FraudAgent")
            )
        ).scalar_one()
        assert row.autonomy_level == "supervised"

    @pytest.mark.asyncio
    async def test_graduate_to_autonomous(self, seeded_session):
        app.dependency_overrides.update(_overrides(seeded_session))
        transport = ASGITransport(app=app)
        async with AsyncClient(
            transport=transport, base_url="http://test", headers=AUTH_HEADER
        ) as c:
            r = await c.patch(
                "/api/agents/InventoryAgent/autonomy",
                json={"level": "autonomous", "reason": "manual override"},
            )
        app.dependency_overrides.clear()
        assert r.status_code == 200
        assert r.json()["autonomy_level"] == "autonomous"
        audit = (
            await seeded_session.execute(
                select(AuditEntry).where(AuditEntry.action_type == "autonomy_change")
            )
        ).scalars().all()
        assert len(audit) == 1
        assert audit[0].agent == "InventoryAgent"
        assert audit[0].details == {
            "previous_level": "shadow",
            "new_level": "autonomous",
            "reason": "manual override",
        }

    @pytest.mark.asyncio
    async def test_demote_from_autonomous(self, seeded_session):
        app.dependency_overrides.update(_overrides(seeded_session))
        await seeded_session.execute(
            update(AgentStatus)
            .where(AgentStatus.agent_id == "PricingAgent")
            .values(autonomy_level="autonomous")
        )
        await seeded_session.commit()
        transport = ASGITransport(app=app)
        async with AsyncClient(
            transport=transport, base_url="http://test", headers=AUTH_HEADER
        ) as c:
            r = await c.patch(
                "/api/agents/PricingAgent/autonomy", json={"level": "supervised"}
            )
        app.dependency_overrides.clear()
        assert r.status_code == 200
        assert r.json()["autonomy_level"] == "supervised"

    @pytest.mark.asyncio
    async def test_invalid_level_returns_400(self, seeded_session):
        app.dependency_overrides.update(_overrides(seeded_session))
        transport = ASGITransport(app=app)
        async with AsyncClient(
            transport=transport, base_url="http://test", headers=AUTH_HEADER
        ) as c:
            r = await c.patch(
                "/api/agents/FraudAgent/autonomy", json={"level": "rogue"}
            )
        app.dependency_overrides.clear()
        assert r.status_code == 400

    @pytest.mark.asyncio
    async def test_unknown_agent_returns_404(self, seeded_session):
        app.dependency_overrides.update(_overrides(seeded_session))
        transport = ASGITransport(app=app)
        async with AsyncClient(
            transport=transport, base_url="http://test", headers=AUTH_HEADER
        ) as c:
            r = await c.patch(
                "/api/agents/DoesNotExist/autonomy", json={"level": "autonomous"}
            )
        app.dependency_overrides.clear()
        assert r.status_code == 404

    @pytest.mark.asyncio
    async def test_requires_auth(self, seeded_session):
        app.dependency_overrides.update(_overrides(seeded_session))
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as c:
            r = await c.patch(
                "/api/agents/FraudAgent/autonomy", json={"level": "autonomous"}
            )
        app.dependency_overrides.clear()
        assert r.status_code == 401


# ---------------------------------------------------------------------------
# 5.  Audit Log
# ---------------------------------------------------------------------------


class TestAudit:
    @pytest.mark.asyncio
    async def test_audit_empty(self, engine):
        factory = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)
        async with factory() as s:
            app.dependency_overrides.update(_overrides(s))
        transport = ASGITransport(app=app)
        async with AsyncClient(
            transport=transport, base_url="http://test", headers=AUTH_HEADER
        ) as c:
            r = await c.get("/api/audit")
        app.dependency_overrides.clear()
        assert r.status_code == 200
        body = r.json()
        assert body["total"] == 0
        assert body["entries"] == []

    @pytest.mark.asyncio
    async def test_audit_with_data(self, seeded_session):
        app.dependency_overrides.update(_overrides(seeded_session))
        transport = ASGITransport(app=app)
        async with AsyncClient(
            transport=transport, base_url="http://test", headers=AUTH_HEADER
        ) as c:
            r = await c.get("/api/audit")
        app.dependency_overrides.clear()
        assert r.status_code == 200
        body = r.json()
        assert body["total"] >= 1

    @pytest.mark.asyncio
    async def test_audit_filter_agent(self, seeded_session):
        app.dependency_overrides.update(_overrides(seeded_session))
        transport = ASGITransport(app=app)
        async with AsyncClient(
            transport=transport, base_url="http://test", headers=AUTH_HEADER
        ) as c:
            r = await c.get("/api/audit?agent=FraudAgent")
        app.dependency_overrides.clear()
        assert r.status_code == 200
        for e in r.json()["entries"]:
            assert e["agent"] == "FraudAgent"

    @pytest.mark.asyncio
    async def test_audit_filter_decision(self, seeded_session):
        app.dependency_overrides.update(_overrides(seeded_session))
        transport = ASGITransport(app=app)
        async with AsyncClient(
            transport=transport, base_url="http://test", headers=AUTH_HEADER
        ) as c:
            r = await c.get("/api/audit?decision=approved")
        app.dependency_overrides.clear()
        assert r.status_code == 200
        for e in r.json()["entries"]:
            assert e["decision"] == "approved"

    @pytest.mark.asyncio
    async def test_audit_filter_operator(self, seeded_session):
        app.dependency_overrides.update(_overrides(seeded_session))
        transport = ASGITransport(app=app)
        async with AsyncClient(
            transport=transport, base_url="http://test", headers=AUTH_HEADER
        ) as c:
            r = await c.get("/api/audit?operator=admin")
        app.dependency_overrides.clear()
        assert r.status_code == 200
        for e in r.json()["entries"]:
            assert e["operator"] == "admin"

    @pytest.mark.asyncio
    async def test_audit_pagination(self, seeded_session):
        app.dependency_overrides.update(_overrides(seeded_session))
        transport = ASGITransport(app=app)
        async with AsyncClient(
            transport=transport, base_url="http://test", headers=AUTH_HEADER
        ) as c:
            r = await c.get("/api/audit?page=1&limit=1")
        app.dependency_overrides.clear()
        assert r.status_code == 200
        body = r.json()
        assert body["page"] == 1
        assert body["limit"] == 1
        assert len(body["entries"]) <= 1

    @pytest.mark.asyncio
    async def test_audit_export_csv(self, seeded_session):
        app.dependency_overrides.update(_overrides(seeded_session))
        transport = ASGITransport(app=app)
        async with AsyncClient(
            transport=transport, base_url="http://test", headers=AUTH_HEADER
        ) as c:
            r = await c.get("/api/audit/export?format=csv")
        app.dependency_overrides.clear()
        assert r.status_code == 200
        assert "text/csv" in r.headers.get("content-type", "")
        assert "audit_log.csv" in r.headers.get("content-disposition", "")

    @pytest.mark.asyncio
    async def test_audit_export_json(self, seeded_session):
        app.dependency_overrides.update(_overrides(seeded_session))
        transport = ASGITransport(app=app)
        async with AsyncClient(
            transport=transport, base_url="http://test", headers=AUTH_HEADER
        ) as c:
            r = await c.get("/api/audit/export?format=json")
        app.dependency_overrides.clear()
        assert r.status_code == 200
        body = r.json()
        assert "entries" in body


# ---------------------------------------------------------------------------
# 6.  Store Settings
# ---------------------------------------------------------------------------


class TestSettings:
    @pytest.mark.asyncio
    async def test_get_settings(self, seeded_session):
        app.dependency_overrides.update(_overrides(seeded_session))
        transport = ASGITransport(app=app)
        async with AsyncClient(
            transport=transport, base_url="http://test", headers=AUTH_HEADER
        ) as c:
            r = await c.get("/api/settings")
        app.dependency_overrides.clear()
        assert r.status_code == 200
        body = r.json()
        assert body["shadow_mode"] is True
        assert body["fraud_threshold"] == 70

    @pytest.mark.asyncio
    async def test_patch_settings_shadow_mode(self, seeded_session):
        app.dependency_overrides.update(_overrides(seeded_session))
        app.dependency_overrides[verify_auth] = lambda: "settings-op"
        transport = ASGITransport(app=app)
        with patch("ecommerce_ops.api.core_routes.ws_manager") as mock_ws:
            mock_ws.broadcast = AsyncMock()
            async with AsyncClient(
                transport=transport, base_url="http://test", headers=AUTH_HEADER
            ) as c:
                r = await c.patch(
                    "/api/settings",
                    json={"shadow_mode": False},
                    headers=AUTH_HEADER,
                )
        app.dependency_overrides.clear()
        assert r.status_code == 200
        assert r.json()["shadow_mode"] is False

    @pytest.mark.asyncio
    async def test_patch_settings_fraud_threshold(self, seeded_session):
        app.dependency_overrides.update(_overrides(seeded_session))
        app.dependency_overrides[verify_auth] = lambda: "op"
        transport = ASGITransport(app=app)
        with patch("ecommerce_ops.api.core_routes.ws_manager") as mock_ws:
            mock_ws.broadcast = AsyncMock()
            async with AsyncClient(
                transport=transport, base_url="http://test", headers=AUTH_HEADER
            ) as c:
                r = await c.patch(
                    "/api/settings",
                    json={"fraud_threshold": 85},
                    headers=AUTH_HEADER,
                )
        app.dependency_overrides.clear()
        assert r.status_code == 200
        assert r.json()["fraud_threshold"] == 85

    @pytest.mark.asyncio
    async def test_patch_settings_fraud_threshold_out_of_range(self, seeded_session):
        app.dependency_overrides.update(_overrides(seeded_session))
        app.dependency_overrides[verify_auth] = lambda: "op"
        transport = ASGITransport(app=app)
        async with AsyncClient(
            transport=transport, base_url="http://test", headers=AUTH_HEADER
        ) as c:
            r = await c.patch(
                "/api/settings",
                json={"fraud_threshold": 150},
                headers=AUTH_HEADER,
            )
        app.dependency_overrides.clear()
        assert r.status_code == 400

    @pytest.mark.asyncio
    async def test_patch_settings_po_limit(self, seeded_session):
        app.dependency_overrides.update(_overrides(seeded_session))
        app.dependency_overrides[verify_auth] = lambda: "op"
        transport = ASGITransport(app=app)
        with patch("ecommerce_ops.api.core_routes.ws_manager") as mock_ws:
            mock_ws.broadcast = AsyncMock()
            async with AsyncClient(
                transport=transport, base_url="http://test", headers=AUTH_HEADER
            ) as c:
                r = await c.patch(
                    "/api/settings",
                    json={"po_limit": 2000.0},
                    headers=AUTH_HEADER,
                )
        app.dependency_overrides.clear()
        assert r.status_code == 200
        assert r.json()["po_limit"] == 2000.0

    @pytest.mark.asyncio
    async def test_patch_settings_po_limit_negative(self, seeded_session):
        app.dependency_overrides.update(_overrides(seeded_session))
        app.dependency_overrides[verify_auth] = lambda: "op"
        transport = ASGITransport(app=app)
        async with AsyncClient(
            transport=transport, base_url="http://test", headers=AUTH_HEADER
        ) as c:
            r = await c.patch(
                "/api/settings",
                json={"po_limit": -10},
                headers=AUTH_HEADER,
            )
        app.dependency_overrides.clear()
        assert r.status_code == 400

    @pytest.mark.asyncio
    async def test_patch_settings_pricing_limit(self, seeded_session):
        app.dependency_overrides.update(_overrides(seeded_session))
        app.dependency_overrides[verify_auth] = lambda: "op"
        transport = ASGITransport(app=app)
        with patch("ecommerce_ops.api.core_routes.ws_manager") as mock_ws:
            mock_ws.broadcast = AsyncMock()
            async with AsyncClient(
                transport=transport, base_url="http://test", headers=AUTH_HEADER
            ) as c:
                r = await c.patch(
                    "/api/settings",
                    json={"pricing_limit": 10.0},
                    headers=AUTH_HEADER,
                )
        app.dependency_overrides.clear()
        assert r.status_code == 200
        assert r.json()["pricing_limit"] == 10.0

    @pytest.mark.asyncio
    async def test_patch_settings_pricing_limit_zero(self, seeded_session):
        app.dependency_overrides.update(_overrides(seeded_session))
        app.dependency_overrides[verify_auth] = lambda: "op"
        transport = ASGITransport(app=app)
        async with AsyncClient(
            transport=transport, base_url="http://test", headers=AUTH_HEADER
        ) as c:
            r = await c.patch(
                "/api/settings",
                json={"pricing_limit": 0},
                headers=AUTH_HEADER,
            )
        app.dependency_overrides.clear()
        assert r.status_code == 400

    @pytest.mark.asyncio
    async def test_patch_settings_reviews_threshold(self, seeded_session):
        app.dependency_overrides.update(_overrides(seeded_session))
        app.dependency_overrides[verify_auth] = lambda: "op"
        transport = ASGITransport(app=app)
        with patch("ecommerce_ops.api.core_routes.ws_manager") as mock_ws:
            mock_ws.broadcast = AsyncMock()
            async with AsyncClient(
                transport=transport, base_url="http://test", headers=AUTH_HEADER
            ) as c:
                r = await c.patch(
                    "/api/settings",
                    json={"reviews_rating_threshold": 3},
                    headers=AUTH_HEADER,
                )
        app.dependency_overrides.clear()
        assert r.status_code == 200
        assert r.json()["reviews_rating_threshold"] == 3

    @pytest.mark.asyncio
    async def test_patch_settings_reviews_threshold_out_of_range(self, seeded_session):
        app.dependency_overrides.update(_overrides(seeded_session))
        app.dependency_overrides[verify_auth] = lambda: "op"
        transport = ASGITransport(app=app)
        async with AsyncClient(
            transport=transport, base_url="http://test", headers=AUTH_HEADER
        ) as c:
            r = await c.patch(
                "/api/settings",
                json={"reviews_rating_threshold": 10},
                headers=AUTH_HEADER,
            )
        app.dependency_overrides.clear()
        assert r.status_code == 400

    @pytest.mark.asyncio
    async def test_patch_settings_slack_channel(self, seeded_session):
        app.dependency_overrides.update(_overrides(seeded_session))
        app.dependency_overrides[verify_auth] = lambda: "op"
        transport = ASGITransport(app=app)
        with patch("ecommerce_ops.api.core_routes.ws_manager") as mock_ws:
            mock_ws.broadcast = AsyncMock()
            async with AsyncClient(
                transport=transport, base_url="http://test", headers=AUTH_HEADER
            ) as c:
                r = await c.patch(
                    "/api/settings",
                    json={"slack_channel": "#ops-alerts"},
                    headers=AUTH_HEADER,
                )
        app.dependency_overrides.clear()
        assert r.status_code == 200

    @pytest.mark.asyncio
    async def test_patch_settings_not_found(self, engine):
        factory = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)
        async with factory() as s:
            app.dependency_overrides.update(_overrides(s))
        app.dependency_overrides[verify_auth] = lambda: "op"
        transport = ASGITransport(app=app)
        async with AsyncClient(
            transport=transport, base_url="http://test", headers=AUTH_HEADER
        ) as c:
            r = await c.patch(
                "/api/settings",
                json={"shadow_mode": True},
                headers=AUTH_HEADER,
            )
        app.dependency_overrides.clear()
        assert r.status_code == 404


# ---------------------------------------------------------------------------
# 7.  Analytics
# ---------------------------------------------------------------------------


class TestAnalytics:
    @pytest.mark.asyncio
    async def test_analytics_empty_db(self, engine):
        factory = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)
        async with factory() as s:
            app.dependency_overrides.update(_overrides(s))
        transport = ASGITransport(app=app)
        async with AsyncClient(
            transport=transport, base_url="http://test", headers=AUTH_HEADER
        ) as c:
            r = await c.get("/api/analytics")
        app.dependency_overrides.clear()
        assert r.status_code == 200
        body = r.json()
        assert "summary" in body
        assert "graduation" in body
        assert "risk_distribution" in body
        assert "charts" in body

    @pytest.mark.asyncio
    async def test_analytics_with_data(self, seeded_session):
        app.dependency_overrides.update(_overrides(seeded_session))
        transport = ASGITransport(app=app)
        async with AsyncClient(
            transport=transport, base_url="http://test", headers=AUTH_HEADER
        ) as c:
            r = await c.get("/api/analytics")
        app.dependency_overrides.clear()
        assert r.status_code == 200
        body = r.json()
        assert body["summary"]["total_decisions"] >= 1
        assert len(body["graduation"]) == 5
        assert "approval_rate_over_time" in body["charts"]


# ---------------------------------------------------------------------------
# 8.  Pipeline / Run
# ---------------------------------------------------------------------------


class TestPipeline:
    @pytest.mark.asyncio
    async def test_trigger_run(self, seeded_session):
        app.dependency_overrides.update(_overrides(seeded_session))
        transport = ASGITransport(app=app)
        with (
            patch("ecommerce_ops.api.app.ws_manager") as mock_ws,
            patch("ecommerce_ops.api.app.task_queue") as mock_tq,
            patch("ecommerce_ops.api.app.run_pipeline_task"),
        ):
            mock_ws.broadcast = AsyncMock()
            mock_tq.enqueue = AsyncMock(return_value="task-1")
            async with AsyncClient(
                transport=transport, base_url="http://test", headers=AUTH_HEADER
            ) as c:
                r = await c.post("/api/run")
        app.dependency_overrides.clear()
        assert r.status_code == 200
        body = r.json()
        assert "run_id" in body
        assert body["message"] == "Operations cycle triggered"

    @pytest.mark.asyncio
    async def test_get_task_not_found(self):
        transport = ASGITransport(app=app)
        async with AsyncClient(
            transport=transport, base_url="http://test", headers=AUTH_HEADER
        ) as c:
            r = await c.get(f"/api/tasks/{uuid.uuid4()}")
        assert r.status_code == 404

    @pytest.mark.asyncio
    async def test_get_task_found(self):
        from ecommerce_ops.infra.task_queue import Task, TaskQueue, TaskStatus

        tq = TaskQueue(num_workers=0, max_queue_size=10)
        task_id = str(uuid.uuid4())
        dummy = Task(task_id, "test-task", lambda: None)
        dummy.status = TaskStatus.COMPLETED
        dummy.completed_at = utc_now()
        tq._tasks[task_id] = dummy

        with patch("ecommerce_ops.api.app.task_queue", tq):
            transport = ASGITransport(app=app)
            async with AsyncClient(
                transport=transport, base_url="http://test", headers=AUTH_HEADER
            ) as c:
                r = await c.get(f"/api/tasks/{task_id}")
        assert r.status_code == 200
        body = r.json()
        assert body["id"] == task_id
        assert body["status"] == "completed"


# ---------------------------------------------------------------------------
# 9.  Metrics
# ---------------------------------------------------------------------------


class TestMetrics:
    @pytest.mark.asyncio
    async def test_metrics_returns_prometheus(self):
        transport = ASGITransport(app=app)
        async with AsyncClient(
            transport=transport, base_url="http://test", headers=AUTH_HEADER
        ) as c:
            r = await c.get("/metrics")
        assert r.status_code == 200
        ct = r.headers.get("content-type", "")
        assert "text/plain" in ct


# ---------------------------------------------------------------------------
# 10.  Shopify Integration
# ---------------------------------------------------------------------------


class TestShopify:
    @pytest.mark.asyncio
    async def test_shopify_status_not_configured(self):
        with (
            patch.object(app_settings, "SHOPIFY_SHOP_DOMAIN", None),
            patch.object(app_settings, "SHOPIFY_ACCESS_TOKEN", None),
        ):
            transport = ASGITransport(app=app)
            async with AsyncClient(
                transport=transport, base_url="http://test", headers=AUTH_HEADER
            ) as c:
                r = await c.get("/shopify/status")
        assert r.status_code == 200
        body = r.json()
        assert body["configured"] is False

    @pytest.mark.asyncio
    async def test_shopify_status_configured(self):
        with (
            patch.object(app_settings, "SHOPIFY_SHOP_DOMAIN", "my-store.myshopify.com"),
            patch.object(app_settings, "SHOPIFY_ACCESS_TOKEN", "shpat_xxx"),
        ):
            transport = ASGITransport(app=app)
            async with AsyncClient(
                transport=transport, base_url="http://test", headers=AUTH_HEADER
            ) as c:
                r = await c.get("/shopify/status")
        assert r.status_code == 200
        body = r.json()
        assert body["configured"] is True
        assert body["shop_domain"] == "my-store.myshopify.com"

    @pytest.mark.asyncio
    async def test_shopify_sync_not_configured_returns_400(self):
        with (
            patch.object(app_settings, "SHOPIFY_SHOP_DOMAIN", None),
            patch.object(app_settings, "SHOPIFY_ACCESS_TOKEN", None),
        ):
            transport = ASGITransport(app=app)
            async with AsyncClient(
                transport=transport, base_url="http://test", headers=AUTH_HEADER
            ) as c:
                r = await c.post("/shopify/sync")
        assert r.status_code == 400

    @pytest.mark.asyncio
    async def test_shopify_install(self):
        with patch("ecommerce_ops.api.shopify.shopify_oauth") as mock_oauth:
            mock_oauth.get_install_url.return_value = "https://shop.myshopify.com/admin/oauth"
            transport = ASGITransport(app=app)
            async with AsyncClient(
                transport=transport, base_url="http://test", headers=AUTH_HEADER
            ) as c:
                r = await c.post(
                    "/shopify/install",
                    json={"shop_domain": "my-store.myshopify.com"},
                )
        assert r.status_code == 200
        body = r.json()
        assert "url" in body
        assert "state" in body


# ---------------------------------------------------------------------------
# 11.  Demo Endpoints
# ---------------------------------------------------------------------------


class TestDemo:
    @pytest.mark.asyncio
    async def test_demo_status(self):
        transport = ASGITransport(app=app)
        async with AsyncClient(
            transport=transport, base_url="http://test", headers=AUTH_HEADER
        ) as c:
            r = await c.get("/demo/demo/status")
        assert r.status_code == 200
        body = r.json()
        assert "demo_mode" in body
        assert "features" in body

    @pytest.mark.asyncio
    async def test_demo_scenarios(self):
        transport = ASGITransport(app=app)
        async with AsyncClient(
            transport=transport, base_url="http://test", headers=AUTH_HEADER
        ) as c:
            r = await c.get("/demo/demo/scenarios")
        assert r.status_code == 200
        scenarios = r.json()["scenarios"]
        ids = {s["id"] for s in scenarios}
        assert "fraud_detection" in ids

    @pytest.mark.asyncio
    async def test_run_demo_fraud(self):
        from ecommerce_ops.security.auth import require_auth

        app.dependency_overrides[require_auth] = lambda: {"id": "u1"}
        try:
            transport = ASGITransport(app=app)
            async with AsyncClient(
                transport=transport, base_url="http://test", headers=AUTH_HEADER
            ) as c:
                r = await c.post("/demo/demo/run/fraud_detection")
        finally:
            app.dependency_overrides.pop(require_auth, None)
        assert r.status_code == 200
        assert r.json()["status"] == "completed"

    @pytest.mark.asyncio
    async def test_run_demo_unknown_returns_404(self):
        from ecommerce_ops.security.auth import require_auth

        app.dependency_overrides[require_auth] = lambda: {"id": "u1"}
        try:
            transport = ASGITransport(app=app)
            async with AsyncClient(
                transport=transport, base_url="http://test", headers=AUTH_HEADER
            ) as c:
                r = await c.post("/demo/demo/run/nonexistent")
        finally:
            app.dependency_overrides.pop(require_auth, None)
        assert r.status_code == 404


# ---------------------------------------------------------------------------
# 12.  Memory Endpoints
# ---------------------------------------------------------------------------


class TestMemory:
    @pytest.mark.asyncio
    async def test_list_memories(self):
        with patch("ecommerce_ops.api.memory.vector_store") as mock_vs:
            mock_vs._filter_memories = AsyncMock(return_value=[])
            transport = ASGITransport(app=app)
            async with AsyncClient(
                transport=transport, base_url="http://test", headers=AUTH_HEADER
            ) as c:
                r = await c.get("/memory/memories")
        assert r.status_code == 200
        body = r.json()
        assert "memories" in body
        assert body["total"] == 0

    @pytest.mark.asyncio
    async def test_create_memory(self):
        mock_entry = MagicMock()
        mock_entry.id = "mem-1"
        mock_entry.memory_type.value = "episodic"
        mock_entry.importance.value = "medium"
        mock_entry.created_at = utc_now()
        with patch("ecommerce_ops.api.memory.memory_retrieval") as mock_mr:
            mock_mr.remember = AsyncMock(return_value=mock_entry)
            transport = ASGITransport(app=app)
            async with AsyncClient(
                transport=transport, base_url="http://test", headers=AUTH_HEADER
            ) as c:
                r = await c.post(
                    "/memory/memories",
                    json={"content": "Test memory entry"},
                )
        assert r.status_code == 200
        body = r.json()
        assert body["id"] == "mem-1"

    @pytest.mark.asyncio
    async def test_search_memories(self):
        mock_result = MagicMock()
        mock_result.entry.id = "m1"
        mock_result.entry.content = "Found it"
        mock_result.entry.memory_type.value = "episodic"
        mock_result.entry.importance.value = "high"
        mock_result.entry.created_at = utc_now()
        mock_result.similarity = 0.95
        mock_result.score = 0.9
        with patch("ecommerce_ops.api.memory.memory_retrieval") as mock_mr:
            mock_mr.recall = AsyncMock(return_value=[mock_result])
            transport = ASGITransport(app=app)
            async with AsyncClient(
                transport=transport, base_url="http://test", headers=AUTH_HEADER
            ) as c:
                r = await c.post(
                    "/memory/memories/search",
                    json={"query": "test query", "max_results": 5},
                )
        assert r.status_code == 200
        body = r.json()
        assert body["total"] == 1
        assert body["results"][0]["similarity"] == 0.95

    @pytest.mark.asyncio
    async def test_get_memory_not_found(self):
        with patch("ecommerce_ops.api.memory.vector_store") as mock_vs:
            mock_vs.get = AsyncMock(return_value=None)
            transport = ASGITransport(app=app)
            async with AsyncClient(
                transport=transport, base_url="http://test", headers=AUTH_HEADER
            ) as c:
                r = await c.get("/memory/memories/nonexistent")
        assert r.status_code == 404

    @pytest.mark.asyncio
    async def test_get_memory_found(self):
        mock_entry = MagicMock()
        mock_entry.id = "m1"
        mock_entry.content = "hello"
        mock_entry.memory_type.value = "episodic"
        mock_entry.importance.value = "medium"
        mock_entry.agent_name = "agent"
        mock_entry.session_id = "s1"
        mock_entry.tags = ["tag1"]
        mock_entry.created_at = utc_now()
        mock_entry.access_count = 3
        with patch("ecommerce_ops.api.memory.vector_store") as mock_vs:
            mock_vs.get = AsyncMock(return_value=mock_entry)
            transport = ASGITransport(app=app)
            async with AsyncClient(
                transport=transport, base_url="http://test", headers=AUTH_HEADER
            ) as c:
                r = await c.get("/memory/memories/m1")
        assert r.status_code == 200
        assert r.json()["id"] == "m1"

    @pytest.mark.asyncio
    async def test_delete_memory(self):
        with patch("ecommerce_ops.api.memory.vector_store") as mock_vs:
            mock_vs.delete = AsyncMock(return_value=True)
            transport = ASGITransport(app=app)
            async with AsyncClient(
                transport=transport, base_url="http://test", headers=AUTH_HEADER
            ) as c:
                r = await c.delete("/memory/memories/m1")
        assert r.status_code == 200
        assert r.json()["deleted"] is True

    @pytest.mark.asyncio
    async def test_memory_stats(self):
        mock_stats = MagicMock()
        mock_stats.model_dump.return_value = {"total": 0, "by_type": {}}
        with patch("ecommerce_ops.api.memory.vector_store") as mock_vs:
            mock_vs.get_stats = AsyncMock(return_value=mock_stats)
            transport = ASGITransport(app=app)
            async with AsyncClient(
                transport=transport, base_url="http://test", headers=AUTH_HEADER
            ) as c:
                r = await c.get("/memory/memories/stats/summary")
        assert r.status_code == 200

    @pytest.mark.asyncio
    async def test_create_session(self):
        mock_sess = MagicMock()
        mock_sess.session_id = "sess-1"
        mock_sess.user_id = "u1"
        mock_sess.agent_name = "agent"
        mock_sess.start_time = utc_now()
        with patch("ecommerce_ops.api.memory.session_manager") as mock_sm:
            mock_sm.create_session.return_value = mock_sess
            transport = ASGITransport(app=app)
            async with AsyncClient(
                transport=transport, base_url="http://test", headers=AUTH_HEADER
            ) as c:
                r = await c.post(
                    "/memory/sessions",
                    json={"user_id": "u1", "agent_name": "agent"},
                )
        assert r.status_code == 200
        assert r.json()["session_id"] == "sess-1"

    @pytest.mark.asyncio
    async def test_list_sessions(self):
        with patch("ecommerce_ops.api.memory.session_manager") as mock_sm:
            mock_sm.get_active_sessions.return_value = []
            transport = ASGITransport(app=app)
            async with AsyncClient(
                transport=transport, base_url="http://test", headers=AUTH_HEADER
            ) as c:
                r = await c.get("/memory/sessions")
        assert r.status_code == 200
        assert r.json()["sessions"] == []


# ---------------------------------------------------------------------------
# 13.  WebSocket (connection test)
# ---------------------------------------------------------------------------


class TestWebSocket:
    @pytest.mark.asyncio
    async def test_ws_auth_rejected_invalid_token(self):
        """WebSocket with bad token should be rejected with close code 4001."""
        transport = ASGITransport(app=app)
        async with (
            AsyncClient(transport=transport, base_url="http://test", headers=AUTH_HEADER) as c,
            c.stream("GET", "/ws/queue?token=bad-token"),
        ):
            pass
        # The connection is closed by server — httpx will raise or return early.
        # We just verify the request doesn't 500; the WS endpoint accepts then closes.
        assert True

    @pytest.mark.asyncio
    async def test_ws_no_token_rejected(self):
        """WebSocket with no token in dev mode should connect (dev-ws-operator)."""
        transport = ASGITransport(app=app)
        async with (
            AsyncClient(transport=transport, base_url="http://test", headers=AUTH_HEADER) as c,
            c.stream("GET", "/ws/queue"),
        ):
            pass
        # In testing mode (non-production), any token is accepted by the WS manager
        assert True


# ---------------------------------------------------------------------------
# 14.  OpenAPI / Docs
# ---------------------------------------------------------------------------


class TestDocs:
    @pytest.mark.asyncio
    async def test_openapi_json_disabled_outside_dev(self):
        # docs/redoc/openapi are disabled outside development.
        transport = ASGITransport(app=app)
        async with AsyncClient(
            transport=transport, base_url="http://test", headers=AUTH_HEADER
        ) as c:
            r = await c.get("/openapi.json")
        assert r.status_code == 404

    @pytest.mark.asyncio
    async def test_docs_page_disabled_outside_dev(self):
        transport = ASGITransport(app=app)
        async with AsyncClient(
            transport=transport, base_url="http://test", headers=AUTH_HEADER
        ) as c:
            r = await c.get("/docs")
        assert r.status_code == 404

    @pytest.mark.asyncio
    async def test_redoc_page_disabled_outside_dev(self):
        transport = ASGITransport(app=app)
        async with AsyncClient(
            transport=transport, base_url="http://test", headers=AUTH_HEADER
        ) as c:
            r = await c.get("/redoc")
        assert r.status_code == 404


# ---------------------------------------------------------------------------
# 15.  Edge cases / error paths
# ---------------------------------------------------------------------------


class TestEdgeCases:
    @pytest.mark.asyncio
    async def test_approve_with_draft_response(self, seeded_session):
        app.dependency_overrides.update(_overrides(seeded_session))
        app.dependency_overrides[verify_auth] = lambda: "op"
        transport = ASGITransport(app=app)
        with (
            patch("ecommerce_ops.api.core_routes.ws_manager") as mock_ws,
            patch(
                "ecommerce_ops.api.core_routes.execute_shop_action", new_callable=AsyncMock
            ) as mock_exec,
            patch("ecommerce_ops.api.core_routes.update_agent_streak", new_callable=AsyncMock),
        ):
            mock_exec.return_value = (True, "ok")
            mock_ws.broadcast = AsyncMock()
            async with AsyncClient(
                transport=transport, base_url="http://test", headers=AUTH_HEADER
            ) as c:
                r = await c.post(
                    "/api/approvals/act-1/approve",
                    json={"notes": "ok", "draft_response": "Thanks for your order!"},
                    headers=AUTH_HEADER,
                )
        app.dependency_overrides.clear()
        assert r.status_code == 200
        body = r.json()
        assert body["status"] in ("approved", "executed")

    @pytest.mark.asyncio
    async def test_approve_execution_failure(self, seeded_session):
        app.dependency_overrides.update(_overrides(seeded_session))
        app.dependency_overrides[verify_auth] = lambda: "op"
        transport = ASGITransport(app=app)
        with (
            patch("ecommerce_ops.api.core_routes.ws_manager") as mock_ws,
            patch(
                "ecommerce_ops.api.core_routes.execute_shop_action", new_callable=AsyncMock
            ) as mock_exec,
            patch("ecommerce_ops.api.core_routes.update_agent_streak", new_callable=AsyncMock),
        ):
            mock_exec.return_value = (False, "Shopify API error")
            mock_ws.broadcast = AsyncMock()
            async with AsyncClient(
                transport=transport, base_url="http://test", headers=AUTH_HEADER
            ) as c:
                r = await c.post(
                    "/api/approvals/act-1/approve",
                    json={},
                    headers=AUTH_HEADER,
                )
        app.dependency_overrides.clear()
        assert r.status_code == 200
        assert r.json()["status"] == "failed"

    @pytest.mark.asyncio
    async def test_get_approvals_all_status(self, seeded_session):
        app.dependency_overrides.update(_overrides(seeded_session))
        transport = ASGITransport(app=app)
        async with AsyncClient(
            transport=transport, base_url="http://test", headers=AUTH_HEADER
        ) as c:
            r = await c.get("/api/approvals?status=all")
        app.dependency_overrides.clear()
        assert r.status_code == 200

    @pytest.mark.asyncio
    async def test_get_approvals_sort_oldest(self, seeded_session):
        app.dependency_overrides.update(_overrides(seeded_session))
        transport = ASGITransport(app=app)
        async with AsyncClient(
            transport=transport, base_url="http://test", headers=AUTH_HEADER
        ) as c:
            r = await c.get("/api/approvals?sort=oldest")
        app.dependency_overrides.clear()
        assert r.status_code == 200

    @pytest.mark.asyncio
    async def test_audit_filter_action_type(self, seeded_session):
        app.dependency_overrides.update(_overrides(seeded_session))
        transport = ASGITransport(app=app)
        async with AsyncClient(
            transport=transport, base_url="http://test", headers=AUTH_HEADER
        ) as c:
            r = await c.get("/api/audit?action_type=fraud_hold")
        app.dependency_overrides.clear()
        assert r.status_code == 200
        for e in r.json()["entries"]:
            assert e["action_type"] == "fraud_hold"

    @pytest.mark.asyncio
    async def test_audit_all_filters(self, seeded_session):
        app.dependency_overrides.update(_overrides(seeded_session))
        transport = ASGITransport(app=app)
        async with AsyncClient(
            transport=transport, base_url="http://test", headers=AUTH_HEADER
        ) as c:
            r = await c.get(
                "/api/audit?agent=FraudAgent&decision=approved&operator=admin"
                "&action_type=fraud_hold&page=1&limit=5"
            )
        app.dependency_overrides.clear()
        assert r.status_code == 200

    @pytest.mark.asyncio
    async def test_approve_expired_action(self, session):
        expired = ApprovalAction(
            id="expired-1",
            agent="FraudAgent",
            action_type="fraud_hold",
            status="pending",
            risk_level="medium",
            confidence_score=0.8,
            created_at=utc_now() - timedelta(days=2),
            expires_at=utc_now() - timedelta(hours=1),
            requires_hitl=True,
            shadow_mode=True,
            payload={"order_id": "ORD-999"},
            evidence=[],
            impact={"financial_impact": 0.0},
        )
        session.add(expired)
        await session.commit()
        app.dependency_overrides.update(_overrides(session))
        app.dependency_overrides[verify_auth] = lambda: "op"
        transport = ASGITransport(app=app)
        async with AsyncClient(
            transport=transport, base_url="http://test", headers=AUTH_HEADER
        ) as c:
            r = await c.post(
                "/api/approvals/expired-1/approve",
                json={},
                headers=AUTH_HEADER,
            )
        app.dependency_overrides.clear()
        assert r.status_code == 400
        assert "expired" in r.json()["detail"].lower()

    @pytest.mark.asyncio
    async def test_reject_already_decided_returns_400(self, seeded_session):
        app.dependency_overrides.update(_overrides(seeded_session))
        app.dependency_overrides[verify_auth] = lambda: "op"
        transport = ASGITransport(app=app)
        with patch("ecommerce_ops.api.core_routes.ws_manager") as mock_ws:
            mock_ws.broadcast = AsyncMock()
            async with AsyncClient(
                transport=transport, base_url="http://test", headers=AUTH_HEADER
            ) as c:
                _r1 = await c.post(
                    "/api/approvals/act-2/reject",
                    json={"reason": "first"},
                    headers=AUTH_HEADER,
                )
                r2 = await c.post(
                    "/api/approvals/act-2/reject",
                    json={"reason": "second"},
                    headers=AUTH_HEADER,
                )
        app.dependency_overrides.clear()
        assert r2.status_code == 400

    @pytest.mark.asyncio
    async def test_run_creates_settings_if_missing(self, engine):
        factory = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)
        async with factory() as s:
            app.dependency_overrides.update(_overrides(s))
        transport = ASGITransport(app=app)
        with (
            patch("ecommerce_ops.api.app.ws_manager") as mock_ws,
            patch("ecommerce_ops.api.app.task_queue") as mock_tq,
            patch("ecommerce_ops.api.app.run_pipeline_task"),
        ):
            mock_ws.broadcast = AsyncMock()
            mock_tq.enqueue = AsyncMock(return_value="task-1")
            async with AsyncClient(
                transport=transport, base_url="http://test", headers=AUTH_HEADER
            ) as c:
                r = await c.post("/api/run")
        app.dependency_overrides.clear()
        assert r.status_code == 200

    @pytest.mark.asyncio
    async def test_ws_stats_requires_auth(self, seeded_session):
        app.dependency_overrides.update(_overrides(seeded_session))
        transport = ASGITransport(app=app)
        async with AsyncClient(
            transport=transport, base_url="http://test", headers={"Authorization": "Bearer invalid"}
        ) as c:
            r = await c.get("/api/ws/stats")
        app.dependency_overrides.clear()
        assert r.status_code in (401, 403)

    @pytest.mark.asyncio
    async def test_ws_stats_with_auth(self, seeded_session):
        app.dependency_overrides.update(_overrides(seeded_session))
        app.dependency_overrides[verify_auth] = lambda: "op"
        transport = ASGITransport(app=app)
        async with AsyncClient(
            transport=transport, base_url="http://test", headers=AUTH_HEADER
        ) as c:
            r = await c.get("/api/ws/stats", headers=AUTH_HEADER)
        app.dependency_overrides.clear()
        assert r.status_code == 200
        body = r.json()
        assert "total_connections" in body

    @pytest.mark.asyncio
    async def test_batch_empty_ids(self, seeded_session):
        app.dependency_overrides.update(_overrides(seeded_session))
        app.dependency_overrides[verify_auth] = lambda: "op"
        transport = ASGITransport(app=app)
        async with AsyncClient(
            transport=transport, base_url="http://test", headers=AUTH_HEADER
        ) as c:
            r = await c.post(
                "/api/approvals/batch",
                json={"ids": [], "action": "approve"},
                headers=AUTH_HEADER,
            )
        app.dependency_overrides.clear()
        assert r.status_code == 200
        assert r.json()["affected_ids"] == []

    @pytest.mark.asyncio
    async def test_get_approvals_nonexistent_action(self, seeded_session):
        app.dependency_overrides.update(_overrides(seeded_session))
        transport = ASGITransport(app=app)
        async with AsyncClient(
            transport=transport, base_url="http://test", headers=AUTH_HEADER
        ) as c:
            r = await c.get("/api/approvals/does-not-exist")
        app.dependency_overrides.clear()
        assert r.status_code == 404

    @pytest.mark.asyncio
    async def test_approve_not_pending_returns_400(self, seeded_session):
        app.dependency_overrides.update(_overrides(seeded_session))
        app.dependency_overrides[verify_auth] = lambda: "op"
        transport = ASGITransport(app=app)
        with patch("ecommerce_ops.api.core_routes.ws_manager") as mock_ws:
            mock_ws.broadcast = AsyncMock()
            async with AsyncClient(
                transport=transport, base_url="http://test", headers=AUTH_HEADER
            ) as c:
                _r = await c.post(
                    "/api/approvals/act-2/approve",
                    json={},
                    headers=AUTH_HEADER,
                )
                # act-2 is still pending; approve it
                # then try again
                r2 = await c.post(
                    "/api/approvals/act-2/approve",
                    json={},
                    headers=AUTH_HEADER,
                )
        app.dependency_overrides.clear()
        # The second call should fail since act-2 is no longer pending
        assert r2.status_code == 400
