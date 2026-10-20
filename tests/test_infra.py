"""Tests for Rate Limiter and Task Queue."""

import asyncio
import time
from unittest.mock import AsyncMock, MagicMock

import pytest

from ecommerce_ops.infra.distributed_lock import DistributedLock
from ecommerce_ops.infra.rate_limiter import (
    _memory_block_until,
    _memory_check,
    _memory_store,
)
from ecommerce_ops.utils import utc_now

# ── Distributed Lock Tests ────────────────────────────────


def test_local_lock_acquire_and_release():
    from ecommerce_ops.infra.distributed_lock import _memory_locks

    _memory_locks.clear()
    lock = DistributedLock("test-lock", ttl_seconds=30)

    assert asyncio.run(lock.acquire()) is True
    assert lock._token is not None
    assert asyncio.run(lock.release()) is True
    assert lock._token is None


def test_local_lock_excludes_second_owner():
    from ecommerce_ops.infra.distributed_lock import _memory_locks

    _memory_locks.clear()
    a = DistributedLock("test-lock", ttl_seconds=30)
    b = DistributedLock("test-lock", ttl_seconds=30)

    assert asyncio.run(a.acquire()) is True
    assert asyncio.run(b.acquire()) is False
    assert asyncio.run(b.release()) is False  # never held

    assert asyncio.run(a.release()) is True
    assert asyncio.run(b.acquire()) is True
    asyncio.run(b.release())


def test_local_lock_expires():
    from ecommerce_ops.infra.distributed_lock import _memory_locks

    _memory_locks.clear()
    a = DistributedLock("test-lock", ttl_seconds=0.01)
    b = DistributedLock("test-lock", ttl_seconds=0.01)

    assert asyncio.run(a.acquire()) is True
    time.sleep(0.05)
    assert asyncio.run(b.acquire()) is True
    asyncio.run(b.release())


def test_local_lock_release_wrong_owner_fails():
    from ecommerce_ops.infra.distributed_lock import _memory_locks

    _memory_locks.clear()
    a = DistributedLock("test-lock", ttl_seconds=30)
    b = DistributedLock("test-lock", ttl_seconds=30)

    assert asyncio.run(a.acquire()) is True
    assert asyncio.run(b.release()) is False
    # Original owner can still release.
    assert asyncio.run(a.release()) is True


def test_redis_lock_uses_set_nx_and_lua_release():
    backend = MagicMock()
    client = MagicMock()
    backend.get_client = AsyncMock(return_value=client)

    client.set = AsyncMock(return_value=True)
    client.eval = AsyncMock(return_value=1)

    lock = DistributedLock("redis-lock", ttl_seconds=10, backend=backend)
    assert asyncio.run(lock.acquire()) is True
    client.set.assert_called_once_with("lock:redis-lock", lock._token, nx=True, ex=10)

    assert asyncio.run(lock.release()) is True
    assert client.eval.call_args[0][0].strip().startswith("if redis.call")


def test_redis_lock_busy_then_acquires():
    backend = MagicMock()
    client = MagicMock()
    backend.get_client = AsyncMock(return_value=client)
    client.set = AsyncMock(side_effect=[None, True])  # busy once, then free
    client.eval = AsyncMock(return_value=1)

    lock = DistributedLock("redis-lock", ttl_seconds=10, backend=backend, poll_interval=0.001)
    assert asyncio.run(lock.acquire(timeout_seconds=1)) is True
    assert client.set.call_count == 2
    asyncio.run(lock.release())


def test_redis_lock_timeout_when_always_busy():
    backend = MagicMock()
    client = MagicMock()
    backend.get_client = AsyncMock(return_value=client)
    client.set = AsyncMock(return_value=None)

    lock = DistributedLock("redis-lock", ttl_seconds=10, backend=backend, poll_interval=0.001)
    assert asyncio.run(lock.acquire(timeout_seconds=0.01)) is False


def test_redis_lock_falls_back_on_redis_error():
    from ecommerce_ops.infra.distributed_lock import _memory_locks

    _memory_locks.clear()
    backend = MagicMock()
    backend.get_client = AsyncMock(side_effect=Exception("redis down"))

    lock = DistributedLock("fallback-lock", ttl_seconds=30, backend=backend)
    assert asyncio.run(lock.acquire()) is True
    assert asyncio.run(lock.release()) is True


# ── Rate Limiter Tests ────────────────────────────────────


def test_memory_check_allows_under_limit():
    _memory_store.clear()
    _memory_block_until.clear()

    allowed, count = _memory_check("test_key", 5, 60)
    assert allowed is True
    assert count == 1


def test_memory_check_allows_up_to_limit():
    _memory_store.clear()
    _memory_block_until.clear()

    for _ in range(4):
        allowed, count = _memory_check("test_key", 5, 60)
        assert allowed is True

    allowed, count = _memory_check("test_key", 5, 60)
    assert allowed is True
    assert count == 5


def test_memory_check_blocks_at_limit():
    _memory_store.clear()
    _memory_block_until.clear()

    for _ in range(5):
        _memory_check("test_key", 5, 60)

    allowed, _ = _memory_check("test_key", 5, 60)
    assert allowed is False


def test_memory_check_different_keys_independent():
    _memory_store.clear()
    _memory_block_until.clear()

    for _ in range(5):
        _memory_check("key1", 5, 60)

    allowed, _ = _memory_check("key2", 5, 60)
    assert allowed is True


def test_memory_check_evicts_old_entries():
    _memory_store.clear()
    _memory_block_until.clear()

    for _ in range(3):
        _memory_check("test_key", 5, 1)

    _memory_store["test_key"] = [time.time() - 10]

    allowed, _ = _memory_check("test_key", 5, 1)
    assert allowed is True


def test_memory_check_blocks_for_window():
    _memory_store.clear()
    _memory_block_until.clear()

    for _ in range(5):
        _memory_check("test_key", 5, 60)

    allowed, _ = _memory_check("test_key", 5, 60)
    assert allowed is False


def test_memory_check_eviction_keeps_recent_keys(monkeypatch):
    """When the store exceeds its cap, only the least-recent keys are evicted —
    active clients must keep their sliding windows (regression for the full-clear
    bug that would flush every caller's state on a surge)."""
    import ecommerce_ops.infra.rate_limiter as rl

    monkeypatch.setattr(rl, "MEMORY_MAX_ENTRIES", 3)
    _memory_store.clear()
    _memory_block_until.clear()

    now = time.time()
    _memory_store["stale"] = [now - 100]
    _memory_store["active"] = [now]
    _memory_store["newer"] = [now]
    assert len(_memory_store) == 3  # at cap, nothing evicted

    # Crossing the cap evicts only the oldest key
    allowed, count = _memory_check("fresh", 50, 60)
    assert allowed is True
    assert count == 1
    assert "stale" not in _memory_store
    assert "active" in _memory_store and "newer" in _memory_store

    # The recently-active key keeps its sliding window and is still rate limited
    for _ in range(4):
        allowed, _ = _memory_check("active", 5, 60)
        assert allowed is True
    allowed, _ = _memory_check("active", 5, 60)
    assert allowed is False


def test_memory_check_eviction_drops_blocked_keys(monkeypatch):
    """Evicted keys also lose their block entries so they are not permanently stuck."""
    import ecommerce_ops.infra.rate_limiter as rl

    monkeypatch.setattr(rl, "MEMORY_MAX_ENTRIES", 2)
    _memory_store.clear()
    _memory_block_until.clear()

    now = time.time()
    _memory_store["stale"] = [now - 100]
    _memory_store["fresh"] = [now]
    _memory_block_until["stale"] = now + 60
    assert "stale" in _memory_block_until

    _memory_check("new", 50, 60)  # pushes store over the cap
    assert len(_memory_store) <= 2
    assert "stale" not in _memory_store
    assert "stale" not in _memory_block_until


# ── Rate Limit Contract Tests ─────────────────────────────


def test_memory_check_rate_allows_and_reports_remaining():
    from ecommerce_ops.infra.rate_limiter import _memory_check_rate

    _memory_store.clear()
    _memory_block_until.clear()

    info = _memory_check_rate("cli-1", 60, 60, 1000, 3600)
    assert info.allowed is True
    assert info.limit == 60
    assert info.remaining == 59
    assert info.hourly_limit == 1000
    assert info.hourly_remaining == 999
    assert info.reset_at > time.time()
    assert info.hourly_reset_at > time.time()


def test_memory_check_rate_hourly_cap_wins():
    from ecommerce_ops.infra.rate_limiter import _memory_check_rate

    _memory_store.clear()
    _memory_block_until.clear()

    for _ in range(1000):
        info = _memory_check_rate("cli-2", 100000, 60, 1000, 3600)
        assert info.allowed is True

    info = _memory_check_rate("cli-2", 100000, 60, 1000, 3600)
    assert info.allowed is False
    assert info.hourly_remaining == 0


def test_memory_check_rate_minute_cap_wins():
    from ecommerce_ops.infra.rate_limiter import _memory_check_rate

    _memory_store.clear()
    _memory_block_until.clear()

    for _ in range(60):
        info = _memory_check_rate("cli-3", 60, 60, 100000, 3600)
        assert info.allowed is True
        assert info.remaining == 60 - (_ + 1)

    info = _memory_check_rate("cli-3", 60, 60, 100000, 3600)
    assert info.allowed is False
    assert info.remaining == 0


def test_redis_rate_limit_uses_lua_and_reports_contract(monkeypatch):
    import ecommerce_ops.infra.rate_limiter as rl

    client = MagicMock()
    client.eval = AsyncMock(return_value=[0, 61, 500])
    backend = MagicMock()
    backend.get_client = AsyncMock(return_value=client)
    monkeypatch.setattr(rl.cache, "get_client", backend.get_client)

    info = asyncio.run(rl.check_rate_limit("cli-4", 60, max_requests_per_hour=1000))
    assert info.allowed is False
    assert info.limit == 60
    assert info.remaining == 0
    assert info.hourly_remaining == 500
    script = client.eval.call_args[0][0]
    assert "zremrangebyscore" in script and "zadd" in script


def test_rate_limit_result_fallback_feed_results_into_headers(monkeypatch):
    import ecommerce_ops.infra.rate_limiter as rl

    client = MagicMock()
    client.eval = AsyncMock(return_value=[1, 2, 7])
    backend = MagicMock()
    backend.get_client = AsyncMock(return_value=client)
    monkeypatch.setattr(rl.cache, "get_client", backend.get_client)

    info = asyncio.run(rl.check_rate_limit("cli-5", 60, max_requests_per_hour=1000))
    assert info.allowed is True
    assert info.remaining == 58
    assert info.hourly_remaining == 993
    headers = {
        "X-RateLimit-Limit": str(info.limit),
        "X-RateLimit-Remaining": str(info.remaining),
        "X-RateLimit-Reset": str(int(info.reset_at)),
    }
    assert headers["X-RateLimit-Limit"] == "60"
    assert headers["X-RateLimit-Remaining"] == "58"
    assert int(headers["X-RateLimit-Reset"]) >= int(time.time())


# ── Task Queue Tests ──────────────────────────────────────


@pytest.mark.asyncio
async def test_task_queue_enqueue():
    from ecommerce_ops.infra.task_queue import TaskQueue

    tq = TaskQueue(num_workers=0)
    task_id = await tq.enqueue("test_task", AsyncMock)
    assert task_id is not None
    assert tq.get_task(task_id) is not None


@pytest.mark.asyncio
async def test_task_queue_max_tasks():

    from ecommerce_ops.infra.task_queue import (
        MAX_TASKS,
        QueueFullError,
        Task,
        TaskQueue,
        TaskStatus,
    )

    tq = TaskQueue(num_workers=0)
    tq._tasks = {str(i): Task(str(i), "test", AsyncMock) for i in range(MAX_TASKS)}
    for t in tq._tasks.values():
        t.status = TaskStatus.RUNNING

    with pytest.raises(QueueFullError, match="maximum capacity"):
        await tq.enqueue("test", AsyncMock)


@pytest.mark.asyncio
async def test_task_queue_evicts_expired():
    from datetime import timedelta

    from ecommerce_ops.infra.task_queue import Task, TaskQueue, TaskStatus

    tq = TaskQueue(num_workers=0)
    old_task = Task("old", "test", AsyncMock)
    old_task.created_at = utc_now() - timedelta(hours=25)
    old_task.status = TaskStatus.COMPLETED
    tq._tasks["old"] = old_task

    tq._evict_expired()
    assert "old" not in tq._tasks


@pytest.mark.asyncio
async def test_task_queue_worker_executes():
    from ecommerce_ops.infra.task_queue import TaskQueue, TaskStatus

    async def dummy():
        return "done"

    tq = TaskQueue(num_workers=1)
    await tq.start()

    task_id = await tq.enqueue("worker_test", dummy)
    await asyncio.sleep(0.5)

    task = tq.get_task(task_id)
    assert task.status == TaskStatus.COMPLETED
    assert task.result == "done"

    await tq.stop()


@pytest.mark.asyncio
async def test_task_queue_worker_handles_failure():
    from ecommerce_ops.infra.task_queue import TaskQueue, TaskStatus

    async def failing():
        raise ValueError("boom")

    tq = TaskQueue(num_workers=1)
    await tq.start()

    task_id = await tq.enqueue("fail_test", failing)
    await asyncio.sleep(0.5)

    task = tq.get_task(task_id)
    assert task.status == TaskStatus.FAILED
    assert "boom" in task.error

    await tq.stop()


@pytest.mark.asyncio
async def test_task_queue_stop():
    from ecommerce_ops.infra.task_queue import TaskQueue

    tq = TaskQueue(num_workers=2)
    await tq.start()
    assert tq._running is True

    await tq.stop()
    assert tq._running is False
