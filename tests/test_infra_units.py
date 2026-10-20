from ecommerce_ops.utils import utc_now
import os

os.environ["ENV"] = "testing"
os.environ["DATABASE_URL"] = "sqlite+aiosqlite://"
os.environ["API_KEY"] = "test-key"
os.environ["DEEPSEEK_API_KEY"] = "sk-test-key"

import asyncio
from datetime import UTC, datetime, timedelta

import pytest


class TestTaskQueue:
    def test_init(self):
        from ecommerce_ops.infra.task_queue import TaskQueue
        tq = TaskQueue(num_workers=2, max_queue_size=10)
        assert tq._num_workers == 2
        assert tq._running is False

    def test_task_model(self):
        from ecommerce_ops.infra.task_queue import Task, TaskStatus
        t = Task("id-1", "test_task", lambda: None)
        assert t.status == TaskStatus.PENDING
        assert t.result is None
        assert t.error is None
        assert t.created_at is not None

    @pytest.mark.asyncio
    async def test_start_and_stop(self):
        from ecommerce_ops.infra.task_queue import TaskQueue
        tq = TaskQueue(num_workers=1, max_queue_size=5)
        await tq.start()
        assert tq._running is True
        assert len(tq._workers) == 1
        await tq.stop()
        assert tq._running is False

    @pytest.mark.asyncio
    async def test_start_idempotent(self):
        from ecommerce_ops.infra.task_queue import TaskQueue
        tq = TaskQueue(num_workers=1, max_queue_size=5)
        await tq.start()
        workers_before = len(tq._workers)
        await tq.start()
        assert len(tq._workers) == workers_before
        await tq.stop()

    @pytest.mark.asyncio
    async def test_enqueue_and_get_task(self):
        from ecommerce_ops.infra.task_queue import TaskQueue
        tq = TaskQueue(num_workers=1, max_queue_size=5)
        await tq.start()

        async def dummy():
            return 42

        task_id = await tq.enqueue("test", dummy)
        assert task_id is not None
        task = tq.get_task(task_id)
        assert task is not None
        assert task.name == "test"
        await tq.stop()

    @pytest.mark.asyncio
    async def test_enqueue_and_executes(self):
        from ecommerce_ops.infra.task_queue import TaskQueue, TaskStatus
        tq = TaskQueue(num_workers=1, max_queue_size=5)
        await tq.start()

        async def compute():
            return 99

        task_id = await tq.enqueue("compute", compute)
        await asyncio.sleep(0.5)
        task = tq.get_task(task_id)
        assert task.status == TaskStatus.COMPLETED
        assert task.result == 99
        await tq.stop()

    @pytest.mark.asyncio
    async def test_enqueue_failure(self):
        from ecommerce_ops.infra.task_queue import TaskQueue, TaskStatus
        tq = TaskQueue(num_workers=1, max_queue_size=5)
        await tq.start()

        async def fail():
            raise ValueError("boom")

        task_id = await tq.enqueue("fail_task", fail)
        await asyncio.sleep(0.5)
        task = tq.get_task(task_id)
        assert task.status == TaskStatus.FAILED
        assert "boom" in task.error
        await tq.stop()

    def test_get_task_not_found(self):
        from ecommerce_ops.infra.task_queue import TaskQueue
        tq = TaskQueue()
        assert tq.get_task("nonexistent") is None

    def test_evict_expired(self):
        from ecommerce_ops.infra.task_queue import Task, TaskQueue, TaskStatus
        tq = TaskQueue()
        old_task = Task("old", "test", lambda: None)
        old_task.status = TaskStatus.COMPLETED
        old_task.created_at = utc_now() - timedelta(hours=25)
        tq._tasks["old"] = old_task
        tq._evict_expired()
        assert "old" not in tq._tasks

    def test_evict_expired_keeps_fresh(self):
        from ecommerce_ops.infra.task_queue import Task, TaskQueue
        tq = TaskQueue()
        fresh_task = Task("fresh", "test", lambda: None)
        tq._tasks["fresh"] = fresh_task
        tq._evict_expired()
        assert "fresh" in tq._tasks

    def test_evict_expired_with_int_timestamp(self):
        from ecommerce_ops.infra.task_queue import Task, TaskQueue, TaskStatus
        tq = TaskQueue()
        old_task = Task("old", "test", lambda: None)
        old_task.status = TaskStatus.COMPLETED
        old_task.created_at = (utc_now() - timedelta(hours=25)).timestamp()
        tq._tasks["old"] = old_task
        tq._evict_expired()
        assert "old" not in tq._tasks

    def test_evict_expired_with_naive_datetime(self):
        from ecommerce_ops.infra.task_queue import Task, TaskQueue, TaskStatus
        tq = TaskQueue()
        old_task = Task("old", "test", lambda: None)
        old_task.status = TaskStatus.COMPLETED
        old_task.created_at = utc_now() - timedelta(hours=25)
        tq._tasks["old"] = old_task
        tq._evict_expired()
        assert "old" not in tq._tasks

