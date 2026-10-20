import hashlib
import json
import logging
import time
from typing import Any, Dict, Optional

import redis.asyncio as redis
from redis.exceptions import ConnectionError, TimeoutError

from ecommerce_ops.api.metrics import METRIC_CACHE_HIT_RATIO
from ecommerce_ops.config import Environment, settings
from ecommerce_ops.infra.circuit_breaker import CircuitBreaker, CircuitBreakerOpenError
from ecommerce_ops.infra.retry import async_retry_decorator

logger = logging.getLogger("ecommerce_ops.memory")


# Backoff window between connection attempts. Without it, every caller hammers
# the connect timeout whenever Redis is down, which stalls boot and turns
# benchmark/test runs into long hangs. After one failed attempt, callers get
# None (graceful degradation) until the window elapses.
REDIS_RECONNECT_BACKOFF_SECONDS = 30.0


CACHE_TTL_BY_PREFIX: dict[str, int] = {
    "/api/analytics": 10,
    "/api/agents/status": 5,
    "/api/settings": 30,
    "/api/approvals": 5,
    "/api/audit": 10,
    "/health": 5,
}


def _cache_key(method: str, path: str, query: str = "") -> str:
    raw = f"{method}:{path}:{query}"
    return f"http_cache:{hashlib.sha256(raw.encode()).hexdigest()}"


def _get_ttl(path: str) -> int:
    for prefix, ttl in CACHE_TTL_BY_PREFIX.items():
        if path.startswith(prefix):
            return ttl
    return 0


class RedisCache:
    _circuit_breaker = CircuitBreaker(name="Redis", failure_threshold=3, recovery_timeout=15.0)
    _redis: Optional[redis.Redis] = None
    _last_connect_attempt: float = 0.0

    async def get_client(self) -> Optional[redis.Redis]:
        if self._redis is not None:
            return self._redis
        if settings.ENV == Environment.TESTING:
            return None
        now = time.monotonic()
        if now - self._last_connect_attempt < REDIS_RECONNECT_BACKOFF_SECONDS:
            return None
        self._last_connect_attempt = now
        try:
            client = redis.from_url(
                self.redis_url,
                decode_responses=True,
                max_connections=settings.REDIS_MAX_CONNECTIONS,
                socket_timeout=settings.REDIS_SOCKET_TIMEOUT,
                socket_connect_timeout=settings.REDIS_SOCKET_CONNECT_TIMEOUT,
            )
            await client.ping()
            self._redis = client
            logger.info("Initialized Redis client")
        except Exception as e:
            logger.warning("Failed to initialize Redis: %s", e)
            self._redis = None
        return self._redis

    def __init__(self) -> None:
        self.redis_url = settings.REDIS_URL
        self._hits = 0
        self._misses = 0
        self._last_hit_ratio = 0.0

    def _update_hit_ratio(self, hit: bool) -> None:
        if hit:
            self._hits += 1
        else:
            self._misses += 1
        total = self._hits + self._misses
        if total >= 10:
            ratio = self._hits / total
            self._last_hit_ratio = round(ratio, 4)
            METRIC_CACHE_HIT_RATIO.set(self._last_hit_ratio)

    async def get(self, key: str) -> Optional[Any]:
        try:
            value = await self._circuit_breaker.call(self._get_with_retry, key)
            self._update_hit_ratio(value is not None)
            return value
        except CircuitBreakerOpenError:
            logger.warning("Redis circuit open, skipping GET %s", key)
            return None
        except Exception as e:
            logger.warning("Redis error during GET %s: %s", key, e)
            return None

    async def set(self, key: str, value: Any, ttl: int = 3600) -> bool:
        try:
            return bool(await self._circuit_breaker.call(self._set_with_retry, key, value, ttl))
        except CircuitBreakerOpenError:
            logger.warning("Redis circuit open, skipping SET %s", key)
            return False
        except Exception as e:
            logger.warning("Redis error during SET %s: %s", key, e)
            return False

    async def get_cached_response(
        self, method: str, path: str, query: str = ""
    ) -> Optional[tuple[int, Dict[str, Any]]]:
        ttl = _get_ttl(path)
        if ttl == 0 or method != "GET":
            return None
        key = _cache_key(method, path, query)
        raw = await self.get(key)
        if raw is None:
            return None
        return raw["status_code"], raw["body"]

    async def set_cached_response(
        self, method: str, path: str, query: str, status_code: int, body: Dict[str, Any]
    ) -> None:
        ttl = _get_ttl(path)
        if ttl == 0 or method != "GET":
            return
        key = _cache_key(method, path, query)
        await self.set(key, {"status_code": status_code, "body": body}, ttl=ttl)

    @async_retry_decorator(  # type: ignore[untyped-decorator]
        exceptions=(ConnectionError, TimeoutError, CircuitBreakerOpenError),
        max_attempts=2,
        min_wait=0.5,
        max_wait=2.0,
    )
    async def _get_with_retry(self, key: str) -> Optional[Any]:
        client = await self.get_client()
        if client is None:
            return None
        val = await client.get(key)
        if val:
            return json.loads(val)
        return None

    @async_retry_decorator(  # type: ignore[untyped-decorator]
        exceptions=(ConnectionError, TimeoutError, CircuitBreakerOpenError),
        max_attempts=2,
        min_wait=0.5,
        max_wait=2.0,
    )
    async def _set_with_retry(self, key: str, value: Any, ttl: int) -> bool:
        client = await self.get_client()
        if client is None:
            return False
        val_str = json.dumps(value)
        await client.set(key, val_str, ex=ttl)
        return True

    async def close(self) -> None:
        if self._redis:
            await self._redis.close()
            self._redis = None


cache = RedisCache()
