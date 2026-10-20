import logging
import os
from typing import AsyncGenerator

from sqlalchemy import (
    JSON,
    Boolean,
    Column,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
)
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import declarative_base

from ecommerce_ops.config import Environment, settings
from ecommerce_ops.utils import utc_now

logger = logging.getLogger("ecommerce_ops.db")

db_url = settings.DATABASE_URL

is_sqlite = "sqlite" in db_url
if settings.ENV == Environment.PRODUCTION and is_sqlite:
    raise RuntimeError(
        "SQLite is not supported in production. Set DATABASE_URL to a PostgreSQL connection string."
    )

engine_kwargs = {
    "echo": False,
    "future": True,
}

if is_sqlite:
    engine_kwargs["connect_args"] = {"timeout": 15}
else:
    engine_kwargs["pool_size"] = settings.DB_POOL_SIZE
    engine_kwargs["max_overflow"] = settings.DB_MAX_OVERFLOW
    engine_kwargs["pool_timeout"] = settings.DB_POOL_TIMEOUT
    engine_kwargs["pool_pre_ping"] = True
    engine_kwargs["pool_recycle"] = 3600

engine = create_async_engine(db_url, **engine_kwargs)

async_session_factory = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)

Base = declarative_base()


def utcnow():
    return utc_now()


class ApprovalAction(Base):
    __tablename__ = "approval_actions"

    id = Column(String, primary_key=True)
    agent = Column(String, nullable=False, index=True)
    action_type = Column(String, nullable=False)
    status = Column(String, default="pending", nullable=False, index=True)
    risk_level = Column(String, default="low", nullable=False, index=True)
    confidence_score = Column(Float, default=0.0, nullable=False)
    created_at = Column(DateTime, default=utcnow, nullable=False)
    expires_at = Column(DateTime, nullable=True)
    requires_hitl = Column(Boolean, default=True, nullable=False)
    shadow_mode = Column(Boolean, default=True, nullable=False)

    payload = Column(JSON, nullable=False)
    evidence = Column(JSON, nullable=False)
    impact = Column(JSON, nullable=False)

    reviewed_by = Column(String, nullable=True)
    reviewed_at = Column(DateTime, nullable=True)
    rejection_reason = Column(String, nullable=True)
    operator_notes = Column(String, nullable=True)

    __table_args__ = (
        Index("ix_approval_actions_agent_status", "agent", "status"),
        Index("ix_approval_actions_agent_risk_status", "agent", "risk_level", "status"),
        Index("ix_approval_actions_created_at", "created_at"),
    )


class AuditEntry(Base):
    __tablename__ = "audit_entries"

    id = Column(Integer, primary_key=True, autoincrement=True)
    action_id = Column(String, ForeignKey("approval_actions.id"), nullable=True)
    timestamp = Column(DateTime, default=utcnow, nullable=False, index=True)
    agent = Column(String, nullable=False, index=True)
    action_type = Column(String, nullable=False, index=True)
    decision = Column(String, nullable=False, index=True)
    operator = Column(String, nullable=True)
    confidence_score = Column(Float, default=0.0, nullable=False)
    financial_impact = Column(Float, nullable=True)
    details = Column(JSON, nullable=True)

    __table_args__ = (
        Index("ix_audit_entries_agent_action_type", "agent", "action_type"),
        Index("ix_audit_entries_agent_decision", "agent", "decision"),
    )


class AgentStatus(Base):
    __tablename__ = "agent_status"

    agent_id = Column(String, primary_key=True)
    status = Column(String, default="active", nullable=False)
    streak = Column(Integer, default=0, nullable=False)
    autonomy_level = Column(String, default="supervised", nullable=False, index=True)
    total_decisions = Column(Integer, default=0, nullable=False)
    total_approvals = Column(Integer, default=0, nullable=False)
    total_rejections = Column(Integer, default=0, nullable=False)
    avg_confidence = Column(Float, default=0.0, nullable=False)


class StoreSettings(Base):
    __tablename__ = "store_settings"

    id = Column(Integer, primary_key=True, default=1)
    shadow_mode = Column(Boolean, default=True, nullable=False)
    fraud_threshold = Column(Integer, default=70, nullable=False)
    po_limit = Column(Float, default=1000.0, nullable=False)
    pricing_limit = Column(Float, default=5.0, nullable=False)
    reviews_rating_threshold = Column(Integer, default=4, nullable=False)


# ── RBAC Models (Persistent) ──────────────────────────────


class RBACUser(Base):
    __tablename__ = "rbac_users"

    id = Column(String, primary_key=True)
    email = Column(String, unique=True, nullable=False, index=True)
    name = Column(String, nullable=True)
    role = Column(String, nullable=False, default="viewer", index=True)
    is_active = Column(Boolean, default=True, nullable=False)
    permissions = Column(JSON, default=list, nullable=False)
    metadata_json = Column(JSON, default=dict, nullable=False)
    created_at = Column(DateTime, default=utcnow, nullable=False)
    updated_at = Column(DateTime, default=utcnow, onupdate=utcnow, nullable=False)
    last_login = Column(DateTime, nullable=True)
    login_count = Column(Integer, default=0, nullable=False)

    __table_args__ = (Index("idx_rbac_users_role_active", "role", "is_active"),)


class RBACApiKey(Base):
    __tablename__ = "rbac_api_keys"

    id = Column(String, primary_key=True)
    key_hash = Column(String, unique=True, nullable=False, index=True)
    key_hash_fast = Column(String, unique=True, nullable=True, index=True)
    key_prefix = Column(String, nullable=False)
    name = Column(String, nullable=False)
    user_id = Column(String, ForeignKey("rbac_users.id"), nullable=False, index=True)
    role = Column(String, nullable=False)
    permissions = Column(JSON, default=list, nullable=False)
    is_active = Column(Boolean, default=True, nullable=False)
    expires_at = Column(DateTime, nullable=True)
    last_used = Column(DateTime, nullable=True)
    usage_count = Column(Integer, default=0, nullable=False)
    created_at = Column(DateTime, default=utcnow, nullable=False)
    metadata_json = Column(JSON, default=dict, nullable=False)


# ── Shopify Webhook Events (Persistent) ───────────────────


class ShopifyWebhookEvent(Base):
    __tablename__ = "shopify_webhook_events"

    id = Column(Integer, primary_key=True, autoincrement=True)
    topic = Column(String, nullable=False, index=True)
    shop_domain = Column(String, nullable=False, index=True)
    api_version = Column(String, nullable=True)
    event_id = Column(String, nullable=True, index=True)
    received_at = Column(DateTime, default=utcnow, nullable=False, index=True)
    processed = Column(Boolean, default=False, nullable=False)
    error = Column(String, nullable=True)
    payload = Column(JSON, nullable=False)

    __table_args__ = (
        Index("ix_shopify_webhook_events_topic_time", "topic", "received_at"),
        Index("ix_shopify_webhook_events_shop_time", "shop_domain", "received_at"),
    )


# ── Security Audit Log (Persistent) ───────────────────────


class SecurityAuditLog(Base):
    __tablename__ = "security_audit_log"

    id = Column(Integer, primary_key=True, autoincrement=True)
    event_type = Column(String, nullable=False, index=True)
    action = Column(String, nullable=False, index=True)
    resource = Column(String, nullable=False, index=True)
    resource_id = Column(String, nullable=True)
    user_id = Column(String, ForeignKey("rbac_users.id"), nullable=True, index=True)
    user_email = Column(String, nullable=True)
    api_key_id = Column(String, ForeignKey("rbac_api_keys.id"), nullable=True)
    role = Column(String, nullable=True)
    success = Column(Boolean, nullable=False, default=True)
    ip_address = Column(String, nullable=True)
    user_agent = Column(String, nullable=True)
    details = Column(JSON, default=dict, nullable=False)
    risk_level = Column(String, nullable=False, default="low", index=True)
    timestamp = Column(DateTime, default=utcnow, nullable=False, index=True)

    __table_args__ = (
        Index("idx_security_audit_type_time", "event_type", "timestamp"),
        Index("idx_security_audit_risk", "risk_level", "timestamp"),
    )


# ── Pipeline Run Tracking (C4) ─────────────────────────────


class PipelineRun(Base):
    """Idempotency table for pipeline runs.

    Each ``run_id`` is unique — an INSERT … ON CONFLICT DO NOTHING at the
    start of ``run_pipeline_task`` prevents duplicate/overlapping runs.
    The row is updated as the run progresses so downstream consumers can
    query run status without polling Redis or application logs.
    """

    __tablename__ = "pipeline_runs"

    id = Column(Integer, primary_key=True, autoincrement=True)
    run_id = Column(String, unique=True, nullable=False, index=True)
    # Multi-store (week 9): the shop this run is scoped to. NULL means the
    # default (env-configured) store.
    shop_domain = Column(String, nullable=True, index=True)
    status = Column(String, nullable=False, default="pending", index=True)
    data_source = Column(String, nullable=True)
    decisions_count = Column(Integer, nullable=False, default=0)
    actions_count = Column(Integer, nullable=False, default=0)
    evaluation_avg_score = Column(Float, nullable=True)
    evaluation_pass_rate = Column(Float, nullable=True)
    error = Column(String, nullable=True)
    started_at = Column(DateTime, default=utcnow, nullable=False)
    finished_at = Column(DateTime, nullable=True)

    __table_args__ = ()


# ── Outbox Pattern (C5) ────────────────────────────────────


class OutboxMessage(Base):
    """Transactional outbox for pipeline action dispatch.

    Before a live Shopify call is attempted, the action is written here with
    status ``pending``. After the call succeeds the row moves to ``sent``.
    A background poller can retry ``pending`` rows that were never committed,
    guaranteeing at-least-once delivery without duplicating Shopify API calls
    (the PipelineRun table handles idempotency).
    """

    __tablename__ = "outbox_messages"

    id = Column(Integer, primary_key=True, autoincrement=True)
    action_id = Column(String, ForeignKey("approval_actions.id"), nullable=False, index=True)
    status = Column(String, nullable=False, default="pending", index=True)
    payload = Column(JSON, nullable=False)
    created_at = Column(DateTime, default=utcnow, nullable=False)
    sent_at = Column(DateTime, nullable=True)
    error = Column(String, nullable=True)
    retry_count = Column(Integer, nullable=False, default=0)

    __table_args__ = ()


# ── A/B Shadow Experiments (Week 8) ─────────────────────────


class ABExperimentRun(Base):
    """Record of a shadow-mode A/B comparison between the production agent
    decision (variant A) and a configured baseline strategy (variant B).

    In shadow mode nothing is executed, so this table captures *which* strategy
    would have produced the higher-scoring decision, along with the divergence
    between the two.  Teams use the aggregate winner/divergence to promote
    better thresholds or rule baselines without touching live traffic.
    """

    __tablename__ = "ab_experiment_runs"

    id = Column(Integer, primary_key=True, autoincrement=True)
    run_id = Column(String, nullable=False, index=True)
    agent_name = Column(String, nullable=False, index=True)
    action_type = Column(String, nullable=False)
    variant_a_score = Column(Float, nullable=False)
    variant_b_score = Column(Float, nullable=False)
    divergence = Column(Float, nullable=False)
    winner = Column(String, nullable=False, index=True)  # "A" | "B" | "tie"
    baseline_params = Column(JSON, nullable=True)
    created_at = Column(DateTime, default=utcnow, nullable=False)

    __table_args__ = (Index("ix_ab_experiment_runs_agent_created", "agent_name", "created_at"),)


# ── Shopify OAuth Credentials (C9) ────────────────────────


class ServerCredential(Base):
    """Server-level credential rotation ledger (week 9).

    Holds only SHA-256 hashes of the server API key material so a database
    leak never exposes usable secrets.  ``status`` is one of:

    - ``active``  — currently accepted for API auth.
    - ``rotated`` — previous key, still accepted during the grace window
      (``valid_until``), giving zero-downtime credential rotation.
    - ``revoked`` — no longer accepted.

    The env-key (``API_KEY``) acts as the bootstrap credential; the first
    rotation writes it here as ``rotated`` so it can be cut over explicitly.
    """

    __tablename__ = "server_credentials"

    id = Column(Integer, primary_key=True, autoincrement=True)
    key_hash = Column(String, unique=True, nullable=False, index=True)
    key_prefix = Column(String, nullable=False)
    status = Column(String, nullable=False, default="active", index=True)
    valid_until = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=utcnow, nullable=False)
    rotated_at = Column(DateTime, nullable=True)

    __table_args__ = (Index("ix_server_credentials_status_valid_until", "status", "valid_until"),)


class OutboundWebhook(Base):
    """Outbound webhook destinations (custom HTTPS endpoints).

    Each row is an HTTPS endpoint that receives event notifications the system
    emits (HITL requests, pipeline failures, agent graduations, daily
    summaries, …).  ``events`` is a JSON list of event types this hook should
    receive; the wildcard ``"*"`` matches every event.

    ``secret`` (optional) is used to HMAC-SHA256 sign the delivered payload so
    the receiving side can verify authenticity via the ``X-Ecom-Ops-Signature``
    header.  It is stored locally like the Shopify OAuth tokens and should be
    treated as sensitive.
    """

    __tablename__ = "outbound_webhooks"

    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String, unique=True, nullable=False, index=True)
    url = Column(String, nullable=False)
    secret = Column(String, nullable=True)
    events = Column(JSON, nullable=False)  # list[str]; "*" means all events
    enabled = Column(Boolean, default=True, nullable=False)
    created_at = Column(DateTime, default=utcnow, nullable=False)
    updated_at = Column(DateTime, default=utcnow, onupdate=utcnow, nullable=False)


class ShopifyShopCredential(Base):
    """Per-shop OAuth credentials persisted after token exchange.

    After a merchant installs the app, the access token is written here
    so it survives server restarts.  ``shop_domain`` is the unique key.
    """

    __tablename__ = "shopify_shop_credentials"

    id = Column(Integer, primary_key=True, autoincrement=True)
    shop_domain = Column(String, unique=True, nullable=False, index=True)
    access_token = Column(String, nullable=False)
    scope = Column(String, nullable=True)
    installed_at = Column(DateTime, default=utcnow, nullable=False)
    updated_at = Column(DateTime, default=utcnow, onupdate=utcnow, nullable=False)
    is_active = Column(Boolean, default=True, nullable=False)


# ── Shopify Synced Data Snapshots (Phase 3 — sync persistence) ──
# The /shopify/sync endpoint pulls products/orders/customers from Shopify.
# These tables persist the synced data (key columns + full raw payload)
# so the "synced" counts returned by the endpoint reflect real writes.


class ShopifyProductSnapshot(Base):
    __tablename__ = "shopify_product_snapshots"

    id = Column(Integer, primary_key=True, autoincrement=True)
    shopify_product_id = Column(String, nullable=False, index=True)
    shop_domain = Column(String, nullable=False, index=True)
    title = Column(String, nullable=True)
    sku = Column(String, nullable=True, index=True)
    min_price = Column(Float, nullable=False, default=0.0)
    max_price = Column(Float, nullable=False, default=0.0)
    total_inventory = Column(Integer, nullable=False, default=0)
    raw_data = Column(JSON, nullable=False)
    synced_at = Column(DateTime, default=utcnow, nullable=False)

    __table_args__ = (
        Index(
            "ix_shopify_product_snapshots_shop_product",
            "shop_domain",
            "shopify_product_id",
            unique=True,
        ),
    )


class ShopifyOrderSnapshot(Base):
    __tablename__ = "shopify_order_snapshots"

    id = Column(Integer, primary_key=True, autoincrement=True)
    shopify_order_id = Column(String, nullable=False, index=True)
    shop_domain = Column(String, nullable=False, index=True)
    order_number = Column(Integer, nullable=True)
    total_price = Column(Float, nullable=False, default=0.0)
    currency = Column(String, nullable=True)
    financial_status = Column(String, nullable=True)
    fulfillment_status = Column(String, nullable=True)
    raw_data = Column(JSON, nullable=False)
    synced_at = Column(DateTime, default=utcnow, nullable=False)

    __table_args__ = (
        Index(
            "ix_shopify_order_snapshots_shop_order", "shop_domain", "shopify_order_id", unique=True
        ),
    )


class ShopifyCustomerSnapshot(Base):
    __tablename__ = "shopify_customer_snapshots"

    id = Column(Integer, primary_key=True, autoincrement=True)
    shopify_customer_id = Column(String, nullable=False, index=True)
    shop_domain = Column(String, nullable=False, index=True)
    email = Column(String, nullable=True)
    first_name = Column(String, nullable=True)
    last_name = Column(String, nullable=True)
    orders_count = Column(Integer, nullable=False, default=0)
    total_spent = Column(Float, nullable=False, default=0.0)
    raw_data = Column(JSON, nullable=False)
    synced_at = Column(DateTime, default=utcnow, nullable=False)

    __table_args__ = (
        Index(
            "ix_shopify_customer_snapshots_shop_customer",
            "shop_domain",
            "shopify_customer_id",
            unique=True,
        ),
    )


# Async Generator for DB sessions
async def get_db_session() -> AsyncGenerator[AsyncSession, None]:
    async with async_session_factory() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()


def _auto_create_schema() -> bool:
    """Whether runtime startup should create tables via ORM metadata.

    PostgreSQL schema is managed exclusively by Alembic migrations; calling
    ``Base.metadata.create_all`` on top of them risks silent schema drift
    (tables Alembic removed or altered would be recreated from ORM metadata).
    ``create_all`` therefore only runs for throwaway/unmanaged databases
    (SQLite) or when ``AUTO_CREATE_SCHEMA`` is explicitly set to a truthy value.
    """
    forced = os.getenv("AUTO_CREATE_SCHEMA", "").strip().lower() in {
        "1",
        "true",
        "yes",
    }
    if forced:
        return True
    return is_sqlite


def _conflict_insert(table):
    """Dialect-aware insert supporting ``ON CONFLICT DO NOTHING``.

    The generic ``sqlalchemy.insert`` does not expose
    ``on_conflict_do_nothing``; only the PostgreSQL and SQLite dialect
    constructs do. ``indexes`` is not a valid argument either — the columns
    must be passed as ``index_elements``.
    """
    if is_sqlite:
        return sqlite_insert(table)
    return pg_insert(table)


# Database initialization helper
async def init_db():
    if _auto_create_schema():
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)

    async with async_session_factory() as session:
        # Idempotent seed inserts using ON CONFLICT DO NOTHING to prevent
        # IntegrityError crashes when 4 uvicorn workers start simultaneously
        # on a fresh database (M9).
        await session.execute(
            _conflict_insert(StoreSettings)
            .values(
                id=1,
                shadow_mode=settings.SHADOW_MODE,
                fraud_threshold=70,
                po_limit=settings.GLOBAL_PO_LIMIT,
                pricing_limit=settings.GLOBAL_PRICE_CHANGE_LIMIT_PERCENT,
                reviews_rating_threshold=4,
            )
            .on_conflict_do_nothing(index_elements=[StoreSettings.id])
        )

        agents = ["FraudAgent", "InventoryAgent", "PricingAgent", "ReviewsAgent", "MarketingAgent"]
        agent_values = [
            {
                "agent_id": name,
                "status": "active",
                "streak": 0,
                "autonomy_level": "shadow" if settings.SHADOW_MODE else "supervised",
                "total_decisions": 0,
                "total_approvals": 0,
                "total_rejections": 0,
                "avg_confidence": 0.0,
            }
            for name in agents
        ]
        await session.execute(
            _conflict_insert(AgentStatus)
            .values(agent_values)
            .on_conflict_do_nothing(index_elements=[AgentStatus.agent_id])
        )

        await session.execute(
            _conflict_insert(RBACUser)
            .values(
                # Deterministic id so concurrent workers dedupe on PK (M9):
                # a random UUID would never collide and the unique-email
                # constraint would fire on the second worker.
                id="default-admin",
                email="admin@example.com",
                name="Admin",
                role="super_admin",
                is_active=True,
                permissions=[],
                metadata_json={"is_default_admin": True},
            )
            .on_conflict_do_nothing(index_elements=[RBACUser.id])
        )
        logger.info("Database initialization complete (idempotent)")

        await session.commit()
