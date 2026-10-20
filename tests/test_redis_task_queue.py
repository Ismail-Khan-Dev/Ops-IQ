"""Tests for redis_task_queue module."""
import json
import time
from unittest.mock import AsyncMock

import pytest

from ecommerce_ops.infra.redis_task_queue import (
    LEASE_TTL_SECONDS,
    MAX_TASK_TIMEOUT_SECONDS,
    QueueFullError,
    RedisTaskQueue,
    Task,
    TaskPriority,
    TaskStatus,
)

# -- Task dataclass --


def test_task_defaults():
    t = Task(name="test_task")
    assert t.name == "test_task"
    assert t.status == TaskStatus.PENDING
    assert t.priority == TaskPriority.NORMAL
    assert t.retry_count == 0
    assert t.max_retries == 3
    assert t.timeout_seconds == 300.0
    assert t.tags == []
    assert t.id


def test_task_to_dict_roundtrip():
    t = Task(
        name="my_task",
        payload={"key": "value", "num": 42},
        priority=TaskPriority.HIGH,
        timeout_seconds=120.0,
        max_retries=5,
        tags=["urgent", "billing"],
    )
    d = t.to_dict()
    assert d["name"] == "my_task"
    assert d["payload"] == {"key": "value", "num": 42}
    assert d["priority"] == "high"
    assert d["timeout_seconds"] == 120.0

    t2 = Task.from_dict(d)
    assert t2.name == t.name
    assert t2.payload == t.payload
    assert t2.priority == t.priority
    assert t2.timeout_seconds == t.timeout_seconds
    assert t2.max_retries == 5
    assert t2.tags == ["urgent", "billing"]


def test_task_from_dict_defaults():
    t = Task.from_dict({})
    assert t.name == ""
    assert t.payload == {}
    assert t.status == TaskStatus.PENDING
    assert t.priority == TaskPriority.NORMAL


def test_task_from_dict_string_values():
    """Test from_dict with actual Python values."""
    t = Task.from_dict({
        "id": "abc-123",
        "name": "task_name",
        "payload": {"a": 1},
        "status": "completed",
        "priority": "critical",
        "created_at": 1000.0,
        "started_at": 1001.0,
        "completed_at": 1010.0,
        "result": "done",
        "error": None,
        "retry_count": 2,
        "max_retries": 5,
        "timeout_seconds": 60.0,
        "tags": ["a"],
    })
    assert t.id == "abc-123"
    assert t.name == "task_name"
    assert t.payload == {"a": 1}
    assert t.status == TaskStatus.COMPLETED
    assert t.priority == TaskPriority.CRITICAL
    assert t.result == "done"
    assert t.retry_count == 2
    assert t.max_retries == 5
    assert t.tags == ["a"]


# -- Priority scoring --


def test_priority_scores():
    assert RedisTaskQueue._priority_score(TaskPriority.CRITICAL) == 1000
    assert RedisTaskQueue._priority_score(TaskPriority.HIGH) == 100
    assert RedisTaskQueue._priority_score(TaskPriority.NORMAL) == 10
    assert RedisTaskQueue._priority_score(TaskPriority.LOW) == 1


# -- Serialization --


def test_serialize_task():
    t = Task(name="x", payload={"k": [1, 2]})
    s = RedisTaskQueue._serialize_task(t)
    assert isinstance(s["payload"], str)
    assert json.loads(s["payload"]) == {"k": [1, 2]}
    assert s["status"] == "pending"


def test_dict_to_task():
    d = {
        "id": "id-1",
        "name": "n",
        "payload": '{"v": 1}',
        "status": "pending",
        "priority": "high",
        "created_at": "100.0",
        "started_at": None,
        "completed_at": None,
        "result": None,
        "error": None,
        "retry_count": "0",
        "max_retries": "3",
        "timeout_seconds": "300",
        "tags": "[]",
    }
    t = RedisTaskQueue._dict_to_task(d)
    assert t.id == "id-1"
    assert t.payload == {"v": 1}
    assert t.priority == TaskPriority.HIGH


# -- QueueFullError --


def test_queue_full_error():
    with pytest.raises(QueueFullError, match="maximum capacity"):
        raise QueueFullError("Task queue at maximum capacity (1000).")


# -- RedisTaskQueue --


@pytest.fixture
def mock_redis():
    redis = AsyncMock()
    redis.zcard = AsyncMock(return_value=0)
    redis.hset = AsyncMock()
    redis.expire = AsyncMock()
    redis.zadd = AsyncMock()
    redis.zpopmax = AsyncMock(return_value=[])
    redis.hgetall = AsyncMock(return_value={})
    redis.sadd = AsyncMock()
    redis.smembers = AsyncMock(return_value=[])
    redis.srem = AsyncMock()
    redis.hget = AsyncMock(return_value=None)
    redis.zrem = AsyncMock(return_value=1)
    redis.setex = AsyncMock()
    return redis


def _make_queue(redis):
    q = RedisTaskQueue(redis, num_workers=0)
    q._worker_id = "test-worker-1"
    return q


def _task_to_redis_hash(task):
    """Convert Task to a dict with serialized values (mimicking Redis hgetall)."""
    result = {}
    for k, v in task.to_dict().items():
        if isinstance(v, (dict, list)):
            result[k] = json.dumps(v)
        elif v is None:
            result[k] = ""
        else:
            result[k] = str(v)
    return result


@pytest.mark.asyncio
async def test_enqueue_task(mock_redis):
    q = _make_queue(mock_redis)
    task_id = await q.enqueue("my_task", {"data": 42}, priority=TaskPriority.HIGH)
    assert isinstance(task_id, str)
    assert len(task_id) > 0
    mock_redis.hset.assert_called_once()
    mock_redis.zadd.assert_called_once()
    assert q._stats["enqueued"] == 1


@pytest.mark.asyncio
async def test_enqueue_rejects_full_queue(mock_redis):
    mock_redis.zcard = AsyncMock(return_value=1000)
    q = _make_queue(mock_redis)
    q.max_queue_size = 1000
    with pytest.raises(QueueFullError):
        await q.enqueue("task", {})


@pytest.mark.asyncio
async def test_enqueue_caps_timeout(mock_redis):
    q = _make_queue(mock_redis)
    await q.enqueue("task", {}, timeout_seconds=9999)
    call_args = mock_redis.hset.call_args
    mapping = call_args[1]["mapping"]
    assert float(mapping["timeout_seconds"]) <= MAX_TASK_TIMEOUT_SECONDS


@pytest.mark.asyncio
async def test_dequeue_returns_none_on_empty(mock_redis):
    mock_redis.zpopmax = AsyncMock(return_value=[])
    q = _make_queue(mock_redis)
    task = await q.dequeue()
    assert task is None


@pytest.mark.asyncio
async def test_dequeue_returns_task(mock_redis):
    original_task = Task(name="test", payload={"x": 1})
    hash_data = _task_to_redis_hash(original_task)
    mock_redis.zpopmax = AsyncMock(return_value=[("task-1", 10)])
    mock_redis.hgetall = AsyncMock(return_value=hash_data)
    q = _make_queue(mock_redis)
    task = await q.dequeue()
    assert task is not None
    assert task.status == TaskStatus.PROCESSING
    assert task.started_at is not None
    mock_redis.sadd.assert_called_once()


@pytest.mark.asyncio
async def test_complete_task(mock_redis):
    original_task = Task(id="t1", name="n", status=TaskStatus.PROCESSING)
    hash_data = _task_to_redis_hash(original_task)
    mock_redis.hgetall = AsyncMock(return_value=hash_data)
    q = _make_queue(mock_redis)
    q._inflight.add("t1")
    await q.complete_task("t1", result={"ok": True})
    mock_redis.hset.assert_called()
    mock_redis.srem.assert_called_with(RedisTaskQueue.PROCESSING_KEY, "t1")
    assert "t1" not in q._inflight
    assert q._stats["completed"] == 1


@pytest.mark.asyncio
async def test_fail_task_with_retry(mock_redis):
    task = Task(id="t2", name="n", retry_count=0, max_retries=3)
    hash_data = _task_to_redis_hash(task)
    mock_redis.hgetall = AsyncMock(return_value=hash_data)
    q = _make_queue(mock_redis)
    q._inflight.add("t2")
    await q.fail_task("t2", "error occurred", retry=True)
    assert q._stats["retried"] == 1
    mock_redis.zadd.assert_called()


@pytest.mark.asyncio
async def test_fail_task_exhausted_retries(mock_redis):
    task = Task(id="t3", name="n", retry_count=3, max_retries=3)
    hash_data = _task_to_redis_hash(task)
    mock_redis.hgetall = AsyncMock(return_value=hash_data)
    q = _make_queue(mock_redis)
    q._inflight.add("t3")
    await q.fail_task("t3", "exhausted", retry=True)
    assert q._stats["failed"] == 1
    assert q._stats["retried"] == 0


@pytest.mark.asyncio
async def test_fail_task_nonexistent(mock_redis):
    mock_redis.hgetall = AsyncMock(return_value={})
    q = _make_queue(mock_redis)
    await q.fail_task("nonexistent", "err")
    assert q._stats["failed"] == 0


@pytest.mark.asyncio
async def test_get_task(mock_redis):
    task = Task(id="t4", name="n", payload={"a": 1})
    hash_data = _task_to_redis_hash(task)
    mock_redis.hgetall = AsyncMock(return_value=hash_data)
    q = _make_queue(mock_redis)
    result = await q.get_task("t4")
    assert result is not None
    assert result.id == "t4"


@pytest.mark.asyncio
async def test_get_task_not_found(mock_redis):
    mock_redis.hgetall = AsyncMock(return_value={})
    q = _make_queue(mock_redis)
    result = await q.get_task("missing")
    assert result is None


@pytest.mark.asyncio
async def test_cancel_task_pending(mock_redis):
    q = _make_queue(mock_redis)
    mock_redis.zrem = AsyncMock(return_value=1)
    result = await q.cancel_task("t5")
    assert result is True
    mock_redis.zrem.assert_called_once_with(RedisTaskQueue.QUEUE_KEY, "t5")


@pytest.mark.asyncio
async def test_cancel_task_not_pending(mock_redis):
    q = _make_queue(mock_redis)
    mock_redis.zrem = AsyncMock(return_value=0)
    result = await q.cancel_task("t5")
    assert result is False


@pytest.mark.asyncio
async def test_heartbeat(mock_redis):
    q = _make_queue(mock_redis)
    await q.heartbeat("t6")
    mock_redis.hset.assert_called_once()
    call_kwargs = mock_redis.hset.call_args
    assert "lease_expires_at" in call_kwargs[1]["mapping"]


@pytest.mark.asyncio
async def test_requeue_stale(mock_redis):
    mock_redis.smembers = AsyncMock(return_value=[b"stale-task"])
    mock_redis.hget = AsyncMock(side_effect=[
        b"100.0",  # lease_expires_at (expired)
        b"normal",  # priority
    ])
    q = _make_queue(mock_redis)
    count = await q.requeue_stale_processing()
    assert count == 1
    mock_redis.zadd.assert_called_once()
    mock_redis.srem.assert_called_once()


@pytest.mark.asyncio
async def test_requeue_stale_valid_lease(mock_redis):
    mock_redis.smembers = AsyncMock(return_value=[b"active-task"])
    future = str(time.time() + 3600)
    mock_redis.hget = AsyncMock(return_value=future.encode())
    q = _make_queue(mock_redis)
    count = await q.requeue_stale_processing()
    assert count == 0


@pytest.mark.asyncio
async def test_requeue_stale_empty(mock_redis):
    mock_redis.smembers = AsyncMock(return_value=[])
    q = _make_queue(mock_redis)
    count = await q.requeue_stale_processing()
    assert count == 0


def test_get_stats(mock_redis):
    q = RedisTaskQueue(mock_redis, num_workers=4)
    q._handlers["task_a"] = lambda: None
    q._inflight.add("x")
    stats = q.get_stats()
    assert stats["workers"] == 4
    assert stats["inflight"] == 1
    assert "task_a" in stats["handlers"]
    assert "enqueued" in stats
    assert "completed" in stats


def test_register_handler(mock_redis):
    q = RedisTaskQueue(mock_redis, num_workers=0)

    async def my_handler(payload):
        return "ok"

    q.register_handler("my_task", my_handler)
    assert "my_task" in q._handlers


def test_constants():
    assert MAX_TASK_TIMEOUT_SECONDS == 300.0
    assert LEASE_TTL_SECONDS == 120.0
    assert MAX_TASK_TIMEOUT_SECONDS > 0
    assert LEASE_TTL_SECONDS > 0


def test_task_status_enum():
    assert TaskStatus.PENDING == "pending"
    assert TaskStatus.PROCESSING == "processing"
    assert TaskStatus.COMPLETED == "completed"
    assert TaskStatus.FAILED == "failed"
    assert TaskStatus.RETRY == "retry"
    assert TaskStatus.CANCELLED == "cancelled"


def test_task_priority_enum():
    assert TaskPriority.LOW == "low"
    assert TaskPriority.NORMAL == "normal"
    assert TaskPriority.HIGH == "high"
    assert TaskPriority.CRITICAL == "critical"
