"""Shared fixtures and configuration for all tests."""
from ecommerce_ops.utils import utc_now

import os
import uuid
from datetime import datetime, timedelta, UTC
from typing import Any, AsyncGenerator

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

# Set test environment before any imports
os.environ["ENV"] = "testing"
os.environ["DEEPSEEK_API_KEY"] = "sk-test-key"
os.environ["API_KEY"] = "opsiq-dev-key-2024"
os.environ["REDIS_URL"] = "redis://localhost:6379/0"

# Always use SQLite for tests (Docker containers may not have PostgreSQL accessible at localhost)
_TEST_DB_URL = "sqlite+aiosqlite://"
os.environ["DATABASE_URL"] = _TEST_DB_URL

from ecommerce_ops.models.db import AgentStatus, ApprovalAction, AuditEntry, Base, StoreSettings

# Register tools that tests depend on
try:
    from ecommerce_ops.tools.scraper_tool import ScraperTool  # noqa: F401
except Exception:
    pass

# Ensure ScraperTool is always registered for tool registry tests
try:
    from ecommerce_ops.tools.registry import ToolRegistry
    from ecommerce_ops.tools.scraper_tool import ScraperTool as _ScraperTool
    if not ToolRegistry.get("scrape_competitor_price"):
        ToolRegistry.register(_ScraperTool())
except Exception:
    pass


@pytest.fixture(scope="session", autouse=True)
def _create_all_tables():
    """Create all tables once for the entire test session on the app's engine."""
    import asyncio

    from ecommerce_ops.models.db import engine

    async def _setup():
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)

    loop = asyncio.new_event_loop()
    loop.run_until_complete(_setup())
    loop.close()
    yield


@pytest_asyncio.fixture
async def db_session() -> AsyncGenerator[AsyncSession, None]:
    """Create a fresh database for each test (in-memory SQLite or fresh PostgreSQL)."""
    is_pg = "postgresql" in _TEST_DB_URL
    if is_pg:
        # Use the test database URL directly; created by CI services
        engine = create_async_engine(
            _TEST_DB_URL,
            echo=False,
            future=True,
            pool_size=5,
            max_overflow=2,
            pool_pre_ping=True,
        )
    else:
        engine = create_async_engine("sqlite+aiosqlite://", echo=False)

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    session_factory = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)
    async with session_factory() as session:
        yield session

    await engine.dispose()


@pytest_asyncio.fixture
async def seeded_db_session(db_session: AsyncSession) -> AsyncSession:
    """Pre-populate the database with seed data."""
    now = utc_now()

    db_session.add(StoreSettings(
        id=1, shadow_mode=True, fraud_threshold=70,
        po_limit=1000.0, pricing_limit=5.0, reviews_rating_threshold=4,
    ))

    for agent_name in ["FraudAgent", "InventoryAgent", "PricingAgent", "ReviewsAgent", "MarketingAgent"]:
        db_session.add(AgentStatus(
            agent_id=agent_name, status="active", streak=0,
            autonomy_level="shadow", total_decisions=0, total_approvals=0,
            total_rejections=0, avg_confidence=0.0,
        ))

    db_session.add(ApprovalAction(
        id="test-action-1", agent="FraudAgent", action_type="fraud_hold",
        status="pending", risk_level="high", confidence_score=0.92,
        created_at=now - timedelta(minutes=15), expires_at=now + timedelta(hours=23),
        requires_hitl=True, shadow_mode=True,
        payload={"order_id": "ORD-001", "fraud_score": 85, "risk_signals": ["IP mismatch"]},
        evidence=[{"label": "Risk Score", "value": "85/100", "weight": "primary", "source": "FraudAgent"}],
        impact={"financial_impact": 450.0, "affected_orders": ["ORD-001"], "reversible": True},
    ))

    db_session.add(ApprovalAction(
        id="test-action-2", agent="InventoryAgent", action_type="purchase_order",
        status="pending", risk_level="low", confidence_score=0.85,
        created_at=now - timedelta(hours=1), expires_at=now + timedelta(days=2),
        requires_hitl=False, shadow_mode=True,
        payload={"sku": "MUG-WHITE", "reorder_quantity": 100, "total_po_value": 500.0},
        evidence=[{"label": "Stockout", "value": "3 days", "weight": "primary", "source": "Forecaster"}],
        impact={"financial_impact": -500.0, "affected_skus": ["MUG-WHITE"], "reversible": True},
    ))

    db_session.add(ApprovalAction(
        id="test-action-3", agent="PricingAgent", action_type="price_change",
        status="executed", risk_level="low", confidence_score=0.95,
        created_at=now - timedelta(days=1), expires_at=None,
        requires_hitl=False, shadow_mode=False,
        payload={"sku": "TSHIRT-BLUE-L", "old_price": 25.0, "new_price": 23.0},
        evidence=[], impact={"financial_impact": 200.0, "reversible": True},
        reviewed_by="admin_operator", reviewed_at=now - timedelta(hours=12),
    ))

    db_session.add(AuditEntry(
        action_id="test-action-3", timestamp=now - timedelta(hours=12),
        agent="PricingAgent", action_type="price_change",
        decision="approved", operator="admin_operator",
        confidence_score=0.95, financial_impact=200.0,
        details={"notes": "Approved price drop"},
    ))

    await db_session.commit()
    return db_session


@pytest.fixture
def mock_inventory_state() -> dict[str, Any]:
    return {
        "inventory_data": [
            {"sku": "TSHIRT-BLUE-L", "stock": 3, "price": 25.0, "variant_id": "v1"},
            {"sku": "MUG-WHITE", "stock": 10, "price": 12.0, "variant_id": "v2"},
        ],
        "active_orders": [
            {"id": "o1", "line_items": [{"sku": "TSHIRT-BLUE-L", "quantity": 1}]},
        ],
        "reviews_data": [
            {"id": "r1", "content": "Great product!", "rating": 5},
        ],
        "decisions": [],
        "hitl_queue": [],
        "messages": [],
        "errors": [],
        "run_id": str(uuid.uuid4()),
        "timestamp": utc_now(),
        "step_index": 0,
    }


@pytest.fixture
def mock_fraud_state() -> dict[str, Any]:
    return {
        "active_orders": [
            {"id": "o_normal", "customer": {"email": "test@example.com"}},
            {"id": "o_suspicious", "customer": {"email": "suspicious@example.com"}},
        ],
        "decisions": [],
    }


@pytest.fixture
def mock_review_state() -> dict[str, Any]:
    return {
        "reviews_data": [
            {"id": "r1", "content": "Shirt shrank after one wash. Disappointed.", "rating": 2},
        ],
        "decisions": [],
    }


@pytest.fixture
def http_client():
    """Create a test client for the FastAPI app."""
    from httpx import ASGITransport, AsyncClient

    from ecommerce_ops.api.app import app

    transport = ASGITransport(app=app)
    return AsyncClient(transport=transport, base_url="http://test")
