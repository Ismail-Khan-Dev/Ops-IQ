import hmac
import logging
import os
import time
import uuid
from contextlib import asynccontextmanager, suppress
from typing import Any, Dict, Optional

from fastapi import Depends, FastAPI, HTTPException, Request, WebSocket, WebSocketDisconnect
from fastapi.responses import JSONResponse, Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field
from sqlalchemy import desc, func, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from ecommerce_ops.api.auth import verify_auth, verify_auth_optional
from ecommerce_ops.api.cart_recovery import router as cart_recovery_router
from ecommerce_ops.api.core_routes import router as core_router
from ecommerce_ops.api.customer_support import router as customer_support_router
from ecommerce_ops.api.demo import router as demo_router
from ecommerce_ops.api.integrations import router as integrations_router
from ecommerce_ops.api.memory import router as memory_router
from ecommerce_ops.api.metrics import (
    METRIC_DB_CONNECTION_POOL,
    METRIC_QUEUE_DEPTH,
)
from ecommerce_ops.api.middleware import setup_middleware
from ecommerce_ops.api.observability import router as observability_router
from ecommerce_ops.api.roi import router as roi_router
from ecommerce_ops.api.security import router as security_router
from ecommerce_ops.api.shopify import router as shopify_router
from ecommerce_ops.api.slack import router as slack_router
from ecommerce_ops.api.sso import router as sso_router
from ecommerce_ops.api.versioning import APIVersionMiddleware, create_v1_router
from ecommerce_ops.api.ws import WS_TICKET_TTL_SECONDS, ws_manager, ws_ticket_store
from ecommerce_ops.config import Environment
from ecommerce_ops.config import settings as app_settings
from ecommerce_ops.infra.browser_pool import browser_pool
from ecommerce_ops.infra.redis_task_queue import RedisTaskQueue, TaskPriority
from ecommerce_ops.infra.task_queue import TaskQueue
from ecommerce_ops.models import (
    AuditEntry,
    StoreSettings,
    async_session_factory,
    get_db_session,
    init_db,
    seed_data_if_empty,
)
from ecommerce_ops.observability.tracing_otel import init_tracing, instrument_app
from ecommerce_ops.pipeline.outbox import OutboxSweeper
from ecommerce_ops.pipeline.runner import run_pipeline_task
from ecommerce_ops.security.auth import AuthenticationMiddleware, require_permission
from ecommerce_ops.security.models import Permission, User
from ecommerce_ops.telemetry import configure_logger
from ecommerce_ops.utils import utc_now

configure_logger()
logger = logging.getLogger("ecommerce_ops.api")


task_queue = TaskQueue(
    num_workers=app_settings.TASK_QUEUE_WORKERS, max_queue_size=app_settings.TASK_QUEUE_MAX_SIZE
)
redis_task_queue: Optional["RedisTaskQueue"] = None
outbox_sweeper = OutboxSweeper()
SERVER_START_TIME = time.time()


async def _pipeline_task_handler(payload: Dict[str, Any]):
    """Handler for Redis-backed pipeline tasks."""
    run_id = payload.get("run_id", "")
    shop_domain = payload.get("shop_domain")
    async with async_session_factory() as session:
        res = await session.execute(select(StoreSettings).where(StoreSettings.id == 1))
        db_settings = res.scalar_one_or_none()
        if not db_settings:
            db_settings = StoreSettings(
                id=1,
                shadow_mode=True,
                fraud_threshold=70,
                po_limit=1000.0,
                pricing_limit=5.0,
                reviews_rating_threshold=4,
            )
            session.add(db_settings)
            await session.commit()
    await run_pipeline_task(run_id, db_settings, shop_domain=shop_domain)


async def _init_task_queue() -> Optional["RedisTaskQueue"]:
    """Initialize RedisTaskQueue if Redis is available, else fall back to in-memory."""
    try:
        from ecommerce_ops.memory.cache import cache

        redis_client = await cache.get_client()
        if redis_client is None:
            logger.warning("Redis unavailable, using in-memory task queue")
            return None
        from ecommerce_ops.connectors.shopify.handlers.order_handlers import (
            SHOPIFY_TASK_NAMES,
            process_shopify_event,
        )

        rq = RedisTaskQueue(
            redis_client,
            num_workers=app_settings.TASK_QUEUE_WORKERS,
            max_queue_size=app_settings.TASK_QUEUE_MAX_SIZE,
        )
        rq.register_handler("pipeline", _pipeline_task_handler)
        for task_name in SHOPIFY_TASK_NAMES:
            rq.register_handler(task_name, process_shopify_event)
        await rq.start()
        logger.info("RedisTaskQueue started (cross-worker task sharing enabled)")
        return rq
    except Exception as e:
        logger.warning("RedisTaskQueue init failed, using in-memory: %s", e)
        return None


async def _register_webhook_handlers() -> None:
    """Register Shopify webhook handlers at startup.

    Previously handlers were only registered inside the OAuth callback, so any
    worker that never ran a callback would silently drop webhooks ("no
    handlers for topic"). Registration is idempotent, so the legacy callback
    path remains harmless.
    """
    from ecommerce_ops.connectors.shopify.handlers.order_handlers import WEBHOOK_HANDLERS
    from ecommerce_ops.connectors.shopify.webhooks import webhook_router

    webhook_router.register_many(WEBHOOK_HANDLERS)
    logger.info("Registered %d Shopify webhook handler(s) at startup", len(WEBHOOK_HANDLERS))


@asynccontextmanager
async def lifespan(app: FastAPI):
    global redis_task_queue
    await _register_webhook_handlers()
    redis_task_queue = await _init_task_queue()
    if redis_task_queue is None:
        await task_queue.start()
    supervisor_ok = False
    try:
        app.state.supervisor = None
        supervisor_ok = True
    except Exception as e:
        logger.critical("Failed to initialize Supervisor: %s", e)

    try:
        await init_db()
        await seed_data_if_empty()
        try:
            from ecommerce_ops.models import engine

            METRIC_DB_CONNECTION_POOL.set(engine.pool.size())
        except Exception:
            pass
        logger.info("Database initialization complete.")
    except Exception as e:
        logger.critical("Database initialization failed: %s", e)
        if app_settings.ENV == "production":
            raise

    await outbox_sweeper.start()

    try:
        await browser_pool.start()
        logger.info("Browser pool initialized.")
    except Exception as e:
        logger.warning("Browser pool initialization failed (scraping will fall back): %s", e)

    try:
        from ecommerce_ops.memory.cache import cache

        redis_client = await cache.get_client()
        if redis_client is not None:
            await ws_manager.init_redis(redis_client)
            from ecommerce_ops.security.sso import sso_manager

            await sso_manager.init_redis(redis_client)
    except Exception as e:
        logger.warning("WS/SSO Redis init skipped: %s", e)

    if supervisor_ok:
        logger.info("Application fully initialized and ready.")
    else:
        logger.warning("Application started without Supervisor — /api/run will fail.")

    yield

    logger.info("Graceful shutdown initiated — closing WebSocket connections...")
    async with ws_manager._lock:
        close_snapshot = list(ws_manager._connections)
    for conn in close_snapshot:
        with suppress(Exception):
            await conn.websocket.close(code=1001, reason="Server shutting down")
    ws_manager._connections.clear()
    ws_manager._ip_counts.clear()
    logger.info("WebSocket connections drained (%d closed)", len(close_snapshot))

    await ws_manager.close_redis()
    await outbox_sweeper.stop()
    if redis_task_queue is not None:
        await redis_task_queue.stop(wait=True)
    else:
        await task_queue.stop(wait=True)
    await browser_pool.stop()
    from ecommerce_ops.memory.cache import cache

    await cache.close()
    logger.info("Application shutdown complete.")


app = FastAPI(
    title="OpsIQ — Autonomous Ecommerce Operations Engine",
    description="""
## OpsIQ — AI-Powered Ecommerce Operations

OpsIQ is an autonomous multi-agent system that manages ecommerce operations including:

- **Fraud Detection** — LLM-powered risk assessment with rule-based fallback
- **Inventory Management** — Demand forecasting and automated reorder
- **Price Optimization** — Competitor price monitoring and dynamic pricing
- **Review Moderation** — Sentiment analysis and response drafting
- **Marketing Automation** — Campaign creation and audience segmentation

### Architecture
- **7 AI Agents** with LLM-first, rule-based fallback
- **PostgreSQL** for persistent storage (RBAC, audit, vector memory)
- **Redis** for caching, rate limiting, and session management
- **LangGraph** for agent orchestration and supervisor pattern
- **Prometheus + Grafana** for monitoring and alerting

### Security
- Role-Based Access Control (RBAC) with 5 roles
- API key authentication with SHA-256 hashing
- Audit logging for all security events
- Rate limiting with Redis sliding window
- Input sanitization and security headers
    """,
    version="0.2.0",
    docs_url="/docs" if app_settings.ENV == Environment.DEVELOPMENT else None,
    redoc_url="/redoc" if app_settings.ENV == Environment.DEVELOPMENT else None,
    openapi_url="/openapi.json" if app_settings.ENV == Environment.DEVELOPMENT else None,
    openapi_tags=[
        {"name": "Health", "description": "Health checks and readiness probes"},
        {"name": "Pipeline", "description": "Pipeline trigger and task management"},
        {"name": "Approvals", "description": "Human-in-the-loop approval queue"},
        {"name": "Audit", "description": "Audit log queries and export"},
        {"name": "Analytics", "description": "Analytics and reporting"},
        {"name": "Agents", "description": "Agent status and configuration"},
        {"name": "Settings", "description": "Store settings management"},
        {"name": "Observability", "description": "Traces, evaluations, and metrics"},
        {"name": "Memory", "description": "Vector memory and session management"},
        {"name": "Security", "description": "RBAC, API keys, and security management"},
        {"name": "Shopify", "description": "Shopify integration and webhooks"},
        {"name": "Cart Recovery", "description": "Abandoned cart recovery automation"},
        {"name": "Customer Support", "description": "AI-powered customer support"},
    ],
)

setup_middleware(app)

# Instrument FastAPI with OpenTelemetry (before auth middleware)
otel_provider = init_tracing()
instrument_app(app)

# Authentication middleware (after all other middleware)
app.add_middleware(AuthenticationMiddleware)

# Include Shopify routes
app.include_router(shopify_router)

# Include Cart Recovery routes
app.include_router(cart_recovery_router)

# Include Customer Support routes
app.include_router(customer_support_router)

# Include Observability routes
app.include_router(observability_router)

# Include Memory routes
app.include_router(memory_router)

# Include Security routes
app.include_router(security_router)

# Include SSO routes
app.include_router(sso_router)

# Include Demo routes
app.include_router(demo_router)

# Include Integration routes (outbound webhooks)
app.include_router(integrations_router, prefix="/api")

# Include Slack interactive routes
app.include_router(slack_router, prefix="/api")
app.include_router(slack_router)

# Include ROI and Margin Preservation routes
app.include_router(roi_router, prefix="/api")
app.include_router(roi_router)

# Include Core routes (approvals, agents, settings, analytics, health)
app.include_router(core_router, prefix="/api")

# ── API Versioning: /api/v1/ routes + deprecation headers ──
v1_router = create_v1_router(
    shopify_router,
    cart_recovery_router,
    customer_support_router,
    observability_router,
    memory_router,
    security_router,
    demo_router,
    core_router,
    integrations_router=integrations_router,
    slack_router=slack_router,
    roi_router=roi_router,
)
app.include_router(v1_router)
app.add_middleware(APIVersionMiddleware)


class LoginBody(BaseModel):
    api_key: str
    operator_id: Optional[str] = None


async def get_current_operator(identity: str = Depends(verify_auth)) -> str:
    return identity or "unknown-operator"


@app.post("/api/auth/login")
async def login(body: LoginBody):
    import hmac

    api_key_setting = app_settings.API_KEY
    valid_key = api_key_setting.get_secret_value() if api_key_setting else ""

    if not valid_key or not body.api_key or not hmac.compare_digest(body.api_key, valid_key):
        raise HTTPException(status_code=401, detail="Invalid API key")

    return {
        "status": "ok",
        "operator": body.operator_id or "api-operator",
    }


@app.get("/api/auth/ws-ticket")
async def issue_ws_ticket(operator: str = Depends(get_current_operator)):
    """
    Exchange a valid API key for a short-lived, single-use WebSocket ticket.

    The frontend must NOT send its API key in the WS query string. Instead it
    calls this endpoint (through the BFF with an Authorization header managed
    server-side) and uses the returned ticket for the WS handshake.
    """
    ticket = await ws_ticket_store.issue(operator)
    return {
        "ticket": ticket,
        "ttl_seconds": WS_TICKET_TTL_SECONDS,
        "expires_in": WS_TICKET_TTL_SECONDS,
    }


@app.get("/health")
async def health(operator: str = Depends(verify_auth_optional)):
    deps: dict[str, str] = {}
    all_ok = True
    uptime_seconds = time.time() - SERVER_START_TIME

    # Database check
    try:
        async for session in get_db_session():
            await session.execute(select(func.now()))
        deps["database"] = "healthy"
    except Exception:
        deps["database"] = "unhealthy"
        all_ok = False

    # Redis check
    try:
        from ecommerce_ops.memory.cache import cache

        client = await cache.get_client()
        if client:
            await client.ping()
            deps["redis"] = "healthy"
        else:
            deps["redis"] = "unavailable"
            all_ok = False
    except Exception:
        deps["redis"] = "unavailable"
        all_ok = False

    # Task queue check
    try:
        if redis_task_queue is not None:
            task_queue_size = (
                len(await redis_task_queue.redis.zrange(redis_task_queue.QUEUE_KEY, 0, -1))
                if redis_task_queue.redis
                else 0
            )
        else:
            task_queue_size = task_queue._queue.qsize() if hasattr(task_queue, "_queue") else 0
        METRIC_QUEUE_DEPTH.set(task_queue_size)
        deps["task_queue_depth"] = str(task_queue_size)
        deps["task_queue"] = "healthy"
    except Exception:
        deps["task_queue"] = "unknown"

    # pgvector check
    try:
        from ecommerce_ops.models import async_session_factory

        async with async_session_factory() as session:
            result = await session.execute(
                text("SELECT 1 FROM pg_extension WHERE extname = 'vector'")
            )
            if result.fetchone():
                deps["pgvector"] = "healthy"
            else:
                deps["pgvector"] = "not installed"
    except Exception:
        deps["pgvector"] = "unavailable"

    # Safety engine check
    try:
        deps["safety_engine"] = "loaded"
    except Exception:
        deps["safety_engine"] = "unavailable"

    # Agent status check
    try:
        from ecommerce_ops.agents.factory import agent_factory

        for name in ["fraud", "inventory", "pricing", "reviews", "marketing"]:
            agent_factory.get_agent(name)
        deps["agents"] = "loaded"
    except Exception:
        deps["agents"] = "degraded"

    status_code = 200 if all_ok else 503
    return JSONResponse(
        status_code=status_code,
        content={
            "status": "ok" if all_ok else "degraded",
            "dependencies": deps,
            "uptime_seconds": uptime_seconds,
            "version": app_settings.PROJECT_NAME,
            "version_number": "0.2.0",
            "environment": app_settings.ENV.value
            if hasattr(app_settings.ENV, "value")
            else str(app_settings.ENV),
            "timestamp": utc_now().isoformat(),
            "checks": {
                "database": deps.get("database", "unknown"),
                "redis": deps.get("redis", "unknown"),
                "pgvector": deps.get("pgvector", "unknown"),
                "task_queue": deps.get("task_queue", "unknown"),
                "agents": deps.get("agents", "unknown"),
            },
        },
    )


@app.websocket("/ws/queue")
async def websocket_endpoint(websocket: WebSocket, token: Optional[str] = None):
    """Authenticated WebSocket endpoint for real-time events.

    Auth: Pass API key as query param ?token=<api-key>
    Browser WS API cannot send custom headers, so query param is the standard approach.
    """
    from ecommerce_ops.api.ws import (
        CLOSE_RATE_LIMITED,
    )

    conn = await ws_manager.connect(websocket, token=token)
    if conn is None:
        # Connection was rejected (auth failed, rate limited, or at capacity)
        return

    try:
        while True:
            data = await websocket.receive_text()
            # Rate limit check
            if not conn.check_rate_limit():
                await websocket.send_json({"type": "error", "payload": {"code": "rate_limited"}})
                await websocket.close(code=CLOSE_RATE_LIMITED, reason="Rate limit exceeded")
                break
            # Respond to ping
            try:
                import json

                msg = json.loads(data)
                if msg.get("type") == "ping":
                    await websocket.send_json({"type": "pong"})
            except (json.JSONDecodeError, ValueError):
                await websocket.send_json({"type": "pong"})
    except WebSocketDisconnect:
        pass
    except Exception as e:
        logger.warning("WS error for %s: %s", conn.operator, e)
    finally:
        await ws_manager.disconnect(conn)


@app.get("/api/audit")
async def get_audit_logs(
    agent: Optional[str] = None,
    decision: Optional[str] = None,
    operator: Optional[str] = None,
    action_type: Optional[str] = None,
    page: int = 1,
    limit: int = 20,
    _: User = Depends(require_permission(Permission.AUDIT_VIEW)),
    db: AsyncSession = Depends(get_db_session),
):
    query = select(AuditEntry)
    if agent and agent != "all":
        query = query.where(AuditEntry.agent == agent)
    if decision and decision != "all":
        query = query.where(AuditEntry.decision == decision)
    if operator and operator != "all":
        query = query.where(AuditEntry.operator == operator)
    if action_type and action_type != "all":
        query = query.where(AuditEntry.action_type == action_type)
    query = query.order_by(desc(AuditEntry.timestamp))

    count_query = select(func.count()).select_from(query.subquery())
    total = (await db.execute(count_query)).scalar() or 0

    offset = (page - 1) * limit
    query = query.offset(offset).limit(limit)
    entries = (await db.execute(query)).scalars().all()

    return {"entries": entries, "total": total, "page": page, "limit": limit}


@app.get("/api/audit/export")
async def export_audit_logs(
    format: str = "csv",
    _: User = Depends(require_permission(Permission.AUDIT_EXPORT)),
    db: AsyncSession = Depends(get_db_session),
):
    import csv as _csv
    import io as _io
    import json as _json

    from fastapi.responses import StreamingResponse

    query = select(AuditEntry).order_by(desc(AuditEntry.timestamp)).limit(10000)

    def _serialize(e) -> dict:
        return {
            "action_id": e.action_id,
            "timestamp": e.timestamp.isoformat() if e.timestamp else None,
            "agent": e.agent,
            "action_type": e.action_type,
            "decision": e.decision,
            "operator": e.operator,
            "confidence": e.confidence_score,
            "financial_impact": e.financial_impact,
            "details": e.details,
        }

    async def _iter_csv():
        buffer = _io.StringIO()
        writer = _csv.writer(buffer)
        writer.writerow(
            [
                "ID",
                "Timestamp",
                "Agent",
                "Action Type",
                "Decision",
                "Operator",
                "Confidence",
                "Financial Impact",
                "Details",
            ]
        )
        row = buffer.getvalue()
        buffer.seek(0)
        buffer.truncate(0)
        yield row

        result = await db.stream(query)
        async for srows in result.scalars().partitions(500):
            for e in srows:
                writer.writerow(
                    [
                        e.action_id,
                        e.timestamp.isoformat() if e.timestamp else "",
                        e.agent,
                        e.action_type,
                        e.decision,
                        e.operator,
                        e.confidence_score,
                        e.financial_impact,
                        str(e.details),
                    ]
                )
            yield buffer.getvalue()
            buffer.seek(0)
            buffer.truncate(0)
        await result.close()

    async def _iter_json():
        yield '{"entries":['
        result = await db.stream(query)
        first = True
        async for srows in result.scalars().partitions(500):
            for e in srows:
                if not first:
                    yield ","
                first = False
                yield _json.dumps(_serialize(e))
        yield "]}"
        await result.close()

    if format == "csv":
        return StreamingResponse(
            _iter_csv(),
            media_type="text/csv",
            headers={"Content-Disposition": "attachment; filename=audit_log.csv"},
        )

    return StreamingResponse(
        _iter_json(),
        media_type="application/json",
        headers={"Content-Disposition": "attachment; filename=audit_log.json"},
    )


@app.get("/ready")
async def readiness():
    """Kubernetes-style readiness probe — checks critical deps only."""
    try:
        async for session in get_db_session():
            await session.execute(select(func.now()))
        db_ok = True
    except Exception:
        db_ok = False

    return JSONResponse(
        status_code=200 if db_ok else 503,
        content={
            "status": "ready" if db_ok else "not ready",
            "database": "ok" if db_ok else "down",
        },
    )


@app.get("/live")
async def liveness():
    """Kubernetes-style liveness probe."""
    return JSONResponse(status_code=200, content={"status": "alive"})


@app.get("/api/ws/stats")
async def ws_stats(
    operator: str = Depends(verify_auth),
):
    """WebSocket connection statistics (requires auth)."""
    return ws_manager.get_stats()


class RunRequest(BaseModel):
    """Trigger a pipeline run, optionally scoped to an installed store."""

    shop_domain: Optional[str] = Field(
        None,
        description="Scope the run to an OAuth-installed store "
        "(e.g. my-store.myshopify.com). Omit to use the env-configured store.",
    )


@app.post("/api/run")
async def trigger_run(
    body: Optional[RunRequest] = None,
    _: User = Depends(require_permission(Permission.AGENTS_EXECUTE)),
    db: AsyncSession = Depends(get_db_session),
):
    run_id = str(uuid.uuid4())
    shop_domain = body.shop_domain if body is not None else None
    res = await db.execute(select(StoreSettings).where(StoreSettings.id == 1))
    db_settings = res.scalar_one_or_none()
    if not db_settings:
        db_settings = StoreSettings(
            id=1,
            shadow_mode=True,
            fraud_threshold=70,
            po_limit=1000.0,
            pricing_limit=5.0,
            reviews_rating_threshold=4,
        )
        db.add(db_settings)
        await db.commit()

    await ws_manager.broadcast({"type": "pipeline_started", "payload": {"run_id": run_id}})

    if redis_task_queue is not None:
        task_id = await redis_task_queue.enqueue(
            "pipeline",
            {"run_id": run_id, "shop_domain": shop_domain},
            priority=TaskPriority.HIGH,
        )
    else:
        task_id = await task_queue.enqueue(
            "pipeline", run_pipeline_task, run_id, db_settings, shop_domain
        )

    return {
        "message": "Operations cycle triggered",
        "run_id": run_id,
        "shop_domain": shop_domain,
        "task_id": task_id,
    }


@app.get("/api/tasks/{task_id}")
async def get_task_status(
    task_id: str,
    _: User = Depends(require_permission(Permission.AGENTS_VIEW)),
):
    if redis_task_queue is not None:
        task = await redis_task_queue.get_task(task_id)
        if not task:
            raise HTTPException(status_code=404, detail="Task not found")
        return {
            "id": task.id,
            "name": task.name,
            "status": task.status.value,
            "error": task.error,
            "created_at": task.created_at,
            "started_at": task.started_at,
            "completed_at": task.completed_at,
        }
    else:
        task = task_queue.get_task(task_id)
        if not task:
            raise HTTPException(status_code=404, detail="Task not found")
        return {
            "id": task.id,
            "name": task.name,
            "status": task.status.value,
            "error": task.error,
            "created_at": task.created_at.isoformat(),
            "started_at": task.started_at.isoformat() if task.started_at else None,
            "completed_at": task.completed_at.isoformat() if task.completed_at else None,
        }


@app.get("/metrics")
async def metrics(request: Request):
    # Auth-gate /metrics in production (H8). Prometheus can use a bearer token
    # or basic auth configured via reverse proxy; otherwise we require API key.
    if app_settings.ENV == Environment.PRODUCTION:
        auth_header = request.headers.get("Authorization", "")
        api_key = app_settings.API_KEY.get_secret_value() if app_settings.API_KEY else None
        if not api_key:
            return Response(
                status_code=403,
                content="Metrics disabled: API_KEY not configured",
                media_type="text/plain",
            )
        # Accept "Bearer <api_key>" or "ApiKey <api_key>" from Prometheus.
        token = auth_header.replace("Bearer ", "").replace("ApiKey ", "").strip()
        if not token or not hmac.compare_digest(token, api_key):
            return Response(
                status_code=401,
                content=" Unauthorized",
                headers={"WWW-Authenticate": 'Bearer realm="metrics"'},
            )

    from ecommerce_ops.api.metrics import generate_metrics

    content, content_type = generate_metrics()
    return Response(content=content, media_type=content_type)


dist_path = "dashboard/dist"
if os.path.exists(dist_path):
    app.mount("/app", StaticFiles(directory=dist_path, html=True), name="static")
    logger.info("Mounted static frontend from %s at /app", dist_path)
else:
    logger.warning("Static frontend path '%s' not found.", dist_path)
