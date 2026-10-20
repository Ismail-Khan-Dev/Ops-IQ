"""
WebSocket Connection Manager with Authentication
Production-grade WS manager with token auth, per-IP limits, rate limiting,
and Redis PubSub for cross-worker broadcast.

Hardening (H4/H6):
- WS tickets are stored in Redis (shared across workers) with SETNX + TTL,
  so multi-worker deployments can exchange tickets regardless of which
  worker handles the WS handshake.
- Pub/sub listener auto-reconnects and is re-started on failure.
- Half-open sockets are pruned during disconnect and broadcast.
"""

import asyncio
import contextlib
import hmac
import ipaddress
import json
import logging
import secrets
import time
from collections import defaultdict
from typing import Dict, List, Optional

from fastapi import WebSocket

from ecommerce_ops.config import Environment, settings
from ecommerce_ops.infra.async_utils import LoopAwareLock

logger = logging.getLogger("ecommerce_ops.api.ws")

# ── Limits ─────────────────────────────────────────────────
MAX_WS_CONNECTIONS = 500
MAX_CONNECTIONS_PER_IP = 5
RATE_LIMIT_MESSAGES = 30  # per minute
RATE_LIMIT_WINDOW = 60.0  # seconds
WS_TICKET_TTL_SECONDS = 60  # short-lived, single-use WS tickets

# ── WebSocket Close Codes (RFC 6455 + custom) ──────────────
CLOSE_NORMAL = 1000
CLOSE_GOING_AWAY = 1001
CLOSE_POLICY_VIOLATION = 1008
CLOSE_TRY_AGAIN_LATER = 1013
CLOSE_AUTH_FAILED = 4001
CLOSE_RATE_LIMITED = 4008
CLOSE_TOO_MANY_CONNECTIONS = 4013


class WSTicketStore:
    """
    Redis-backed store of short-lived, single-use WebSocket tickets.

    Tickets are stored with SETEX (TTL-bounded, single-use) so that any worker
    in the fleet can validate them. This fixes the single-worker limitation of
    the in-memory store (H4).
    """

    TICKET_PREFIX = "ws:ticket:"

    def __init__(self, redis_client=None):
        self._redis = redis_client

    async def issue(self, operator: str = "ws-operator") -> str:
        ticket = secrets.token_urlsafe(32)
        if self._redis is not None:
            await self._redis.setex(
                f"{self.TICKET_PREFIX}{ticket}", WS_TICKET_TTL_SECONDS, operator
            )
        return ticket

    async def verify(self, ticket: str) -> Optional[str]:
        """
        Validate and consume a single-use ticket via Redis GETDEL.

        Returns the operator id on success, None on invalid/expired/reused.
        """
        if not ticket:
            return None

        if self._redis is not None:
            try:
                value = await self._redis.getdel(f"{self.TICKET_PREFIX}{ticket}")
            except Exception as e:
                logger.debug("WS ticket Redis verify failed: %s", e)
                return None
            if value is None:
                return None
            return value.decode() if isinstance(value, bytes) else value

        # Fallback: in-memory verification (dev/test only).
        return None

    def _purge_locked(self) -> None:
        pass


ws_ticket_store: WSTicketStore = WSTicketStore()


class AuthenticatedConnection:
    """Tracks a single authenticated WebSocket connection."""

    __slots__ = ("_message_times", "client_ip", "connected_at", "operator", "websocket")

    def __init__(self, websocket: WebSocket, operator: str, client_ip: str):
        self.websocket = websocket
        self.operator = operator
        self.client_ip = client_ip
        self.connected_at = time.monotonic()
        self._message_times: List[float] = []

    def check_rate_limit(self) -> bool:
        """Returns True if within rate limit, False if exceeded."""
        now = time.monotonic()
        cutoff = now - RATE_LIMIT_WINDOW
        self._message_times = [t for t in self._message_times if t > cutoff]
        if len(self._message_times) >= RATE_LIMIT_MESSAGES:
            return False
        self._message_times.append(now)
        return True

    @property
    def age_seconds(self) -> float:
        return time.monotonic() - self.connected_at


PUBSUB_CHANNEL = "opsiq:ws:broadcast"


class ConnectionManager:
    """WebSocket connection manager with authentication, rate limiting, and Redis PubSub."""

    def __init__(self):
        self._connections: List[AuthenticatedConnection] = []
        # LoopAwareLock: this manager is a process-level singleton shared across
        # event loops (uvicorn --reload, per-test loops), so a plain asyncio.Lock
        # would bind to the first loop it contends on and break the next one.
        self._lock = LoopAwareLock()
        self._ip_counts: Dict[str, int] = defaultdict(int)
        self._redis = None
        self._pubsub_task: Optional[asyncio.Task] = None
        self._pubsub = None

    async def init_redis(self, redis_client):
        """Initialize Redis PubSub for cross-worker broadcasts."""
        self._redis = redis_client
        # Also wire Redis into the ticket store for shared multi-worker auth.
        ws_ticket_store._redis = redis_client
        if self._redis is None:
            return
        try:
            self._pubsub = self._redis.pubsub()
            await self._pubsub.subscribe(PUBSUB_CHANNEL)
            self._pubsub_task = asyncio.create_task(self._pubsub_listener())
            logger.info("WS Redis PubSub initialized (channel=%s)", PUBSUB_CHANNEL)
        except Exception as e:
            logger.warning("WS Redis PubSub init failed (broadcasts will be local-only): %s", e)
            self._redis = None

    async def _pubsub_listener(self):
        """Listen for cross-worker broadcast messages from Redis.

        Auto-reconnects on disconnect (H6 resilience).
        """
        while self._redis is not None:
            pubsub = None
            try:
                pubsub = self._redis.pubsub()
                await pubsub.subscribe(PUBSUB_CHANNEL)
                logger.info("WS pubsub listener connected (channel=%s)", PUBSUB_CHANNEL)
                async for message in pubsub.listen():
                    if message["type"] != "message":
                        continue
                    try:
                        data = json.loads(message["data"])
                        conns_snapshot = []
                        async with self._lock:
                            conns_snapshot = list(self._connections)
                        dead = []
                        for conn in conns_snapshot:
                            try:
                                await conn.websocket.send_json(data)
                            except Exception:
                                dead.append(conn)
                        if dead:
                            async with self._lock:
                                for conn in dead:
                                    if conn in self._connections:
                                        self._connections.remove(conn)
                                        self._ip_counts[conn.client_ip] = max(
                                            0, self._ip_counts[conn.client_ip] - 1
                                        )
                    except Exception as e:
                        logger.debug("WS pubsub message parse error: %s", e)
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.warning("WS pubsub listener error (will reconnect in 5s): %s", e)
                try:
                    await asyncio.sleep(5)
                except asyncio.CancelledError:
                    break
            finally:
                if pubsub:
                    try:
                        await pubsub.unsubscribe(PUBSUB_CHANNEL)
                        await pubsub.close()
                    except Exception:
                        pass

    async def close_redis(self):
        """Clean up Redis PubSub subscription."""
        self._redis = None
        if self._pubsub_task:
            self._pubsub_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._pubsub_task
            self._pubsub_task = None

    def _get_client_ip(self, websocket: WebSocket) -> str:
        """Extract client IP, only honoring X-Forwarded-For from trusted proxies."""
        client = websocket.client
        direct_ip = client.host if client else "unknown"

        if settings.ENV == Environment.TESTING:
            forwarded = websocket.headers.get("x-forwarded-for", "")
            if forwarded:
                return forwarded.split(",")[0].strip()
            return direct_ip

        if not settings.TRUSTED_PROXIES:
            return direct_ip

        try:
            client_addr = ipaddress.ip_address(direct_ip)
        except ValueError:
            return direct_ip

        for proxy_cidr in settings.TRUSTED_PROXIES:
            try:
                if client_addr in ipaddress.ip_network(proxy_cidr, strict=False):
                    forwarded = websocket.headers.get("x-forwarded-for", "")
                    if forwarded:
                        return forwarded.split(",")[0].strip()
            except ValueError:
                pass

        return direct_ip

    async def _verify_token(self, token: Optional[str]) -> Optional[str]:
        """
        Verify WS auth token against the API_KEY (ticket verification is
        handled separately via the Redis-backed WSTicketStore.verify).
        Returns operator ID if valid, None if invalid.
        """
        if not token:
            return None

        api_key_setting = settings.API_KEY
        if api_key_setting:
            expected_key = api_key_setting.get_secret_value()
            if hmac.compare_digest(token, expected_key):
                return "ws-operator"
            return None

        # Dev mode: accept any token. Production must use API_KEY or ticket.
        if settings.ENV != Environment.PRODUCTION:
            return "dev-ws-operator"

        return None

    async def connect(
        self, websocket: WebSocket, token: Optional[str] = None
    ) -> Optional[AuthenticatedConnection]:
        """
        Authenticate and accept a WebSocket connection.
        Returns AuthenticatedConnection on success, None on rejection.
        """
        client_ip = self._get_client_ip(websocket)

        # 0. Accept a one-time ticket (single-use, TTL-bounded) OR an API key
        operator: Optional[str] = None
        if token:
            operator = await ws_ticket_store.verify(token) or await self._verify_token(token)
        if not operator:
            logger.warning("WS auth rejected from %s: invalid token", client_ip)
            await websocket.accept()
            await websocket.close(code=CLOSE_AUTH_FAILED, reason="Authentication failed")
            return None

        # 2. Check per-IP connection limit
        async with self._lock:
            if self._ip_counts[client_ip] >= MAX_CONNECTIONS_PER_IP:
                logger.warning(
                    "WS per-IP limit reached for %s (%d)", client_ip, self._ip_counts[client_ip]
                )
                await websocket.accept()
                await websocket.close(
                    code=CLOSE_TOO_MANY_CONNECTIONS,
                    reason=f"Maximum {MAX_CONNECTIONS_PER_IP} connections per IP",
                )
                return None

            # 3. Check global connection limit
            if len(self._connections) >= MAX_WS_CONNECTIONS:
                logger.warning("WS global limit reached (%d)", len(self._connections))
                await websocket.accept()
                await websocket.close(code=CLOSE_TRY_AGAIN_LATER, reason="Server at capacity")
                return None

        # 4. Accept and register
        await websocket.accept()
        conn = AuthenticatedConnection(websocket, operator, client_ip)
        async with self._lock:
            self._connections.append(conn)
            self._ip_counts[client_ip] += 1

        logger.info(
            "WS client connected: operator=%s ip=%s total=%d",
            operator,
            client_ip,
            len(self._connections),
        )
        return conn

    async def disconnect(self, conn: AuthenticatedConnection):
        """Remove a connection from tracking."""
        async with self._lock:
            if conn in self._connections:
                self._connections.remove(conn)
                self._ip_counts[conn.client_ip] = max(0, self._ip_counts[conn.client_ip] - 1)
                if self._ip_counts[conn.client_ip] == 0:
                    del self._ip_counts[conn.client_ip]
                logger.info(
                    "WS client disconnected: operator=%s ip=%s total=%d",
                    conn.operator,
                    conn.client_ip,
                    len(self._connections),
                )

    async def broadcast(self, message: dict):
        """Send a message to all authenticated connections across all workers."""
        if self._redis is not None:
            try:
                await self._redis.publish(PUBSUB_CHANNEL, json.dumps(message))
                return
            except Exception as e:
                logger.debug("Redis publish failed, falling back to local broadcast: %s", e)

        dead: List[AuthenticatedConnection] = []
        async with self._lock:
            conns_snapshot = list(self._connections)

        for conn in conns_snapshot:
            try:
                await conn.websocket.send_json(message)
            except Exception:
                dead.append(conn)

        if dead:
            async with self._lock:
                for conn in dead:
                    if conn in self._connections:
                        self._connections.remove(conn)
                        self._ip_counts[conn.client_ip] = max(
                            0, self._ip_counts[conn.client_ip] - 1
                        )

    @property
    def connection_count(self) -> int:
        return len(self._connections)

    def get_stats(self) -> dict:
        """Return connection statistics (no sensitive data)."""
        return {
            "total_connections": len(self._connections),
            "unique_ips": len(self._ip_counts),
            "max_connections": MAX_WS_CONNECTIONS,
            "max_per_ip": MAX_CONNECTIONS_PER_IP,
        }


ws_manager = ConnectionManager()
