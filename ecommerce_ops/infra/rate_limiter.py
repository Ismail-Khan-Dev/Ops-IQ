"""
Rate Limiter
Redis-backed sliding window (minute + hour) with in-memory fallback.

The Redis path executes a single Lua script so the minute and hour windows
are updated atomically — a concurrent burst cannot race both counters.
"""

import hashlib
import logging
import math
import time
from collections import defaultdict
from dataclasses import dataclass

from redis.exceptions import ConnectionError, TimeoutError

from ecommerce_ops.infra.circuit_breaker import CircuitBreakerOpenError
from ecommerce_ops.memory.cache import cache

logger = logging.getLogger("ecommerce_ops.infra.rate_limiter")

WINDOW_SECONDS = 60
HOUR_SECONDS = 3600

# One EVAL from the request path, so the two windows advance atomically.
_RATE_LIMIT_LUA = """
local minute_key = KEYS[1]
local hour_key = KEYS[2]

local now = tonumber(ARGV[1])
local minute_cutoff = now - tonumber(ARGV[2])
local hour_cutoff = now - tonumber(ARGV[3])
local minute_max = tonumber(ARGV[4])
local hour_max = tonumber(ARGV[5])
local minute_expiry = tonumber(ARGV[6])
local hour_expiry = tonumber(ARGV[7])

redis.call('zremrangebyscore', minute_key, '-inf', minute_cutoff)
redis.call('zremrangebyscore', hour_key, '-inf', hour_cutoff)
local minute_count = tonumber(redis.call('zcard', minute_key))
local hour_count = tonumber(redis.call('zcard', hour_key))

if minute_count >= minute_max or hour_count >= hour_max then
  return {0, minute_count, hour_count}
end

redis.call('zadd', minute_key, now, now)
redis.call('expire', minute_key, minute_expiry)
redis.call('zadd', hour_key, now, now)
redis.call('expire', hour_key, hour_expiry)
return {1, minute_count + 1, hour_count + 1}
"""

# In-memory fallback: per-client sliding window
_memory_store: dict[str, list[float]] = defaultdict(list)
_memory_block_until: dict[str, float] = {}
MEMORY_MAX_ENTRIES = 10_000


@dataclass
class RateLimitInfo:
    """Result of a rate-limit check, ready to emit as HTTP headers."""

    allowed: bool
    limit: int
    remaining: int
    reset_at: float  # epoch seconds when the minute window resets
    hourly_limit: int
    hourly_remaining: int
    hourly_reset_at: float  # epoch seconds when the hour window resets


def _window_reset(now: float, window: int) -> float:
    """Next fixed-boundary reset (epoch seconds) for a window starting at now."""
    return math.ceil(now / window) * window


async def check_rate_limit(
    key: str,
    max_requests: int,
    window: int = WINDOW_SECONDS,
    max_requests_per_hour: int | None = None,
    hourly_window: int = HOUR_SECONDS,
) -> RateLimitInfo:
    if max_requests_per_hour is None:
        max_requests_per_hour = max_requests
    client = await cache.get_client()
    if client is None:
        return _memory_check_rate(
            key,
            max_requests,
            window,
            max_requests_per_hour,
            hourly_window,
        )

    digest = hashlib.sha256(key.encode()).hexdigest()
    minute_key = f"ratelimit:{digest}"
    hour_key = f"{minute_key}:hour"
    now = time.time()

    try:
        result = await client.eval(
            _RATE_LIMIT_LUA,
            2,
            minute_key,
            hour_key,
            now,
            window,
            hourly_window,
            max_requests,
            max_requests_per_hour,
            window * 2,
            hourly_window * 2,
        )
        allowed, minute_count, hour_count = (int(v) for v in result)
        return _build_info(
            allowed=bool(allowed),
            limit=max_requests,
            count=minute_count,
            window=window,
            hourly_limit=max_requests_per_hour,
            hourly_count=hour_count,
            hourly_window=hourly_window,
            now=now,
        )
    except (ConnectionError, TimeoutError, CircuitBreakerOpenError) as e:
        logger.warning("Redis rate limiter unavailable, using in-memory fallback: %s", e)
        return _memory_check_rate(
            key,
            max_requests,
            window,
            max_requests_per_hour,
            hourly_window,
        )


def _build_info(
    *,
    allowed: bool,
    limit: int,
    count: int,
    window: int,
    hourly_limit: int,
    hourly_count: int,
    hourly_window: int,
    now: float,
) -> RateLimitInfo:
    return RateLimitInfo(
        allowed=allowed,
        limit=limit,
        remaining=max(0, limit - count),
        reset_at=_window_reset(now, window),
        hourly_limit=hourly_limit,
        hourly_remaining=max(0, hourly_limit - hourly_count),
        hourly_reset_at=_window_reset(now, hourly_window),
    )


def _memory_check_rate(
    key: str,
    max_requests: int,
    window: int,
    max_requests_per_hour: int,
    hourly_window: int,
) -> RateLimitInfo:
    """In-memory fallback for both windows, mirroring the Lua semantics."""
    now = time.time()

    # Check the hour window first: a denied request must not be recorded in
    # either window (matching the Lua path, which rejects before any zadd).
    hour_allowed, hour_count = _memory_check(f"{key}:hourly", max_requests_per_hour, hourly_window)
    if not hour_allowed:
        return _build_info(
            allowed=False,
            limit=max_requests,
            count=max_requests,
            window=window,
            hourly_limit=max_requests_per_hour,
            hourly_count=hour_count,
            hourly_window=hourly_window,
            now=now,
        )

    minute_allowed, minute_count = _memory_check(key, max_requests, window)
    if not minute_allowed:
        return _build_info(
            allowed=False,
            limit=max_requests,
            count=minute_count,
            window=window,
            hourly_limit=max_requests_per_hour,
            hourly_count=hour_count,
            hourly_window=hourly_window,
            now=now,
        )

    return _build_info(
        allowed=True,
        limit=max_requests,
        count=minute_count,
        window=window,
        hourly_limit=max_requests_per_hour,
        hourly_count=hour_count,
        hourly_window=hourly_window,
        now=now,
    )


def _evict_lru():
    """Bound the in-memory store by evicting only the least-recently-active keys.

    A naive cap that clears *all* entries would let a surge of distinct clients
    immediately reset every caller's window, driving an unrestricted traffic
    burst. Evict just the oldest keys until the store is back under the cap so
    active clients keep their state.
    """
    if len(_memory_store) <= MEMORY_MAX_ENTRIES:
        return
    by_recency = sorted(
        _memory_store,
        key=lambda k: _memory_store[k][-1] if _memory_store[k] else 0,
    )
    remove_count = len(_memory_store) - MEMORY_MAX_ENTRIES
    for key in by_recency[:remove_count]:
        _memory_store.pop(key, None)
        _memory_block_until.pop(key, None)


def _memory_check(key: str, max_requests: int, window: int) -> tuple[bool, int]:
    """In-memory sliding window rate limiter (per-process)."""
    now = time.time()
    cutoff = now - window

    # Check block
    block_until = _memory_block_until.get(key, 0)
    if now < block_until:
        return False, max_requests

    # Sliding window
    timestamps = _memory_store[key]
    _memory_store[key] = [t for t in timestamps if t > cutoff]
    count = len(_memory_store[key])

    if count >= max_requests:
        _memory_block_until[key] = now + window
        logger.warning("In-memory rate limit hit for %s", key[:16])
        return False, count

    _memory_store[key].append(now)
    # Keep the store bounded, evicting only stale/least-recent keys. Runs after
    # the append so the entry that pushed us over the cap is what triggers it.
    if len(_memory_store) > MEMORY_MAX_ENTRIES:
        _evict_lru()
    return True, count + 1
