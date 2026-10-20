"""
Distributed Lock
Redis-backed mutual exclusion (SET NX EX + Lua-atomic release) with a local
in-process fallback so single-node deployments and tests remain correct.

Usage:
    lock = DistributedLock("outbox-sweeper", ttl_seconds=60)
    if await lock.acquire():
        try:
            ...
        finally:
            await lock.release()
"""

import asyncio
import logging
import time
import uuid
from typing import Optional

from redis.exceptions import ConnectionError, TimeoutError

from ecommerce_ops.infra.circuit_breaker import CircuitBreakerOpenError
from ecommerce_ops.memory.cache import cache

logger = logging.getLogger("ecommerce_ops.infra.distributed_lock")

# Lua release script: delete the key only if we still own it. Compare-and-delete
# must be atomic, otherwise a lock held past its TTL could be released by a
# previous owner right after the new owner acquires it.
_RELEASE_LUA = """
if redis.call("get", KEYS[1]) == ARGV[1] then
    return redis.call("del", KEYS[1])
else
    return 0
end
"""

# Local fallback: lock name -> (token, expires_at). Single-process asyncio is
# cooperatively scheduled, so dict operations here are atomic.
_memory_locks: dict[str, tuple[str, float]] = {}
MEMORY_MAX_LOCKS = 10_000


class DistributedLock:
    """A named mutual-exclusion lock with a lease TTL."""

    def __init__(
        self,
        name: str,
        ttl_seconds: float = 30.0,
        backend: Optional[object] = None,
        poll_interval: float = 0.05,
    ):
        self.name = name
        self.ttl_seconds = ttl_seconds
        self.backend = backend or cache
        self.poll_interval = poll_interval
        self._token: Optional[str] = None

    @property
    def _redis_key(self) -> str:
        return f"lock:{self.name}"

    async def acquire(self, timeout_seconds: Optional[float] = None) -> bool:
        """Try to acquire the lock. Blocks up to ``timeout_seconds`` if busy.

        Returns True when this caller owns the lock. Fail-open to the local
        in-process lock when Redis is unavailable.
        """
        token = uuid.uuid4().hex
        try:
            client = await self.backend.get_client()
        except Exception as e:
            logger.warning("Redis lock unavailable, using in-memory fallback: %s", e)
            return self._memory_acquire(token)
        if client is None:
            return self._memory_acquire(token)

        deadline = None if timeout_seconds is None else time.monotonic() + timeout_seconds
        try:
            while True:
                acquired = await client.set(self._redis_key, token, nx=True, ex=self.ttl_seconds)
                if acquired:
                    self._token = token
                    return True
                if deadline is not None and time.monotonic() >= deadline:
                    return False
                await asyncio.sleep(self.poll_interval)
        except (ConnectionError, TimeoutError, CircuitBreakerOpenError) as e:
            logger.warning("Redis lock unavailable, using in-memory fallback: %s", e)
            return self._memory_acquire(token)

    async def release(self) -> bool:
        """Release the lock. Returns True if this caller actually held it."""
        if self._token is None:
            return False
        token = self._token
        self._token = None

        try:
            client = await self.backend.get_client()
        except Exception as e:
            logger.warning("Redis lock release unavailable, using in-memory fallback: %s", e)
            return self._memory_release(token)
        if client is None:
            return self._memory_release(token)
        try:
            result = await client.eval(_RELEASE_LUA, 1, self._redis_key, token)
            return bool(result)
        except (ConnectionError, TimeoutError, CircuitBreakerOpenError) as e:
            logger.warning("Redis lock release unavailable, using in-memory fallback: %s", e)
            return self._memory_release(token)

    def _memory_acquire(self, token: str) -> bool:
        now = time.monotonic()
        existing = _memory_locks.get(self.name)
        if existing is not None and existing[1] > now:
            return False
        if len(_memory_locks) > MEMORY_MAX_LOCKS:
            _memory_locks.clear()
        _memory_locks[self.name] = (token, now + self.ttl_seconds)
        self._token = token
        logger.debug("Acquired in-memory lock %s", self.name)
        return True

    def _memory_release(self, token: str) -> bool:
        existing = _memory_locks.get(self.name)
        if existing is None or existing[0] != token:
            return False
        del _memory_locks[self.name]
        logger.debug("Released in-memory lock %s", self.name)
        return True
