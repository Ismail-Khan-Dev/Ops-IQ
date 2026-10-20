"""
Shopify OAuth State Store
Persists OAuth CSRF state across workers and restarts.

Uses Redis when available (recommended — multi-instance safe, survives
restarts) and transparently degrades to an in-process dictionary otherwise.
State values carry a short TTL and are single-use (consumed on callback).
"""

import contextlib
import logging
import secrets
import time
from typing import Optional

from ecommerce_ops.config import settings

logger = logging.getLogger("ecommerce_ops.connectors.shopify.oauth_state")

STATE_TTL_SECONDS = 600  # 10 minutes, matches Shopify redirect window


class OAuthStateStore:
    """Single-use OAuth state store with Redis backend + in-memory fallback."""

    PREFIX = "shopify:oauth:state:"

    def __init__(self, ttl_seconds: int = STATE_TTL_SECONDS):
        self.redis_url = settings.REDIS_URL
        self.ttl_seconds = ttl_seconds
        self._redis = None
        self._memory: dict[str, tuple[str, float]] = {}

    async def _get_redis(self):
        """Lazily acquire an async Redis client, or None when unavailable."""
        if self._redis is None:
            try:
                import redis.asyncio as redis

                client = redis.from_url(
                    self.redis_url,
                    decode_responses=True,
                    socket_timeout=settings.REDIS_SOCKET_TIMEOUT,
                    socket_connect_timeout=settings.REDIS_SOCKET_CONNECT_TIMEOUT,
                )
                await client.ping()
                self._redis = client
                logger.info("Redis-backed OAuth state store initialized")
            except Exception as e:
                logger.warning(
                    "OAuth state store using in-memory fallback (Redis unavailable: %s)", e
                )
                self._redis = None
        return self._redis

    async def create(self, shop_domain: str) -> str:
        """Generate a new single-use state token bound to a shop."""
        state = secrets.token_urlsafe(32)
        client = await self._get_redis()
        if client is not None:
            try:
                await client.set(
                    f"{self.PREFIX}{state}",
                    shop_domain,
                    ex=self.ttl_seconds,
                )
                return state
            except Exception as e:
                logger.warning("Redis SET for OAuth state failed, falling back: %s", e)
        self._memory[state] = (shop_domain, time.time())
        return state

    async def consume(self, state: str, max_age: int = STATE_TTL_SECONDS) -> Optional[str]:
        """Validate and consume a state token.

        Returns the bound shop domain if the token is valid and fresh,
        otherwise None. Tokens are single-use.
        """
        if not state:
            return None
        client = await self._get_redis()
        if client is not None:
            try:
                shop_domain = await client.getdel(f"{self.PREFIX}{state}")
                if shop_domain:
                    return shop_domain
                return None
            except Exception as e:
                logger.warning("Redis GETDEL for OAuth state failed, falling back: %s", e)

        entry = self._memory.pop(state, None)
        if entry is None:
            return None
        shop_domain, created = entry
        if time.time() - created > max_age:
            logger.warning("Expired OAuth state token detected")
            return None
        return shop_domain

    async def close(self):
        if self._redis:
            with contextlib.suppress(Exception):
                await self._redis.close()
            self._redis = None


# Singleton
oauth_state_store = OAuthStateStore()
