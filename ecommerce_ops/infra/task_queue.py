"""
Task Queue
In-memory async task queue with size limits and task expiry.

Hardening (H5):
- Enqueue rejects with QueueFullError when MAX_TASKS is reached (503-style).
  Pending and running tasks are never evicted to make room.
"""

import asyncio
import logging
import uuid
from datetime import datetime, timedelta
from enum import StrEnum
from typing import Any, Callable, Optional

from ecommerce_ops.utils import utc_now

logger = logging.getLogger("ecommerce_ops.infra.task_queue")

MAX_TASKS = 500
TASK_EXPIRY_HOURS = 24


class QueueFullError(Exception):
    """Raised when the in-memory task queue is at capacity."""


class TaskStatus(StrEnum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"


class Task:
    def __init__(self, task_id: str, name: str, coro_factory: Callable, *args, **kwargs):
        self.id = task_id
        self.name = name
        self.coro_factory = coro_factory
        self.args = args
        self.kwargs = kwargs
        self.status = TaskStatus.PENDING
        self.result: Any = None
        self.error: Optional[str] = None
        self.created_at = utc_now()
        self.started_at: Optional[datetime] = None
        self.completed_at: Optional[datetime] = None


class TaskQueue:
    def __init__(self, num_workers: int = 2, max_queue_size: int = 100):
        self._queue: asyncio.Queue[Task] = asyncio.Queue(maxsize=max_queue_size)
        self._workers: list[asyncio.Task] = []
        self._num_workers = num_workers
        self._running = False
        self._tasks: dict[str, Task] = {}

    async def start(self):
        if self._running:
            return
        self._running = True
        self._workers = [
            asyncio.create_task(self._worker_loop(i), name=f"task-worker-{i}")
            for i in range(self._num_workers)
        ]
        logger.info("TaskQueue started with %d workers", self._num_workers)

    async def stop(self, wait: bool = True):
        self._running = False
        for _ in range(self._num_workers):
            await self._queue.put(None)
        if wait and self._workers:
            await asyncio.gather(*self._workers, return_exceptions=True)
        self._workers.clear()
        logger.info("TaskQueue stopped")

    async def enqueue(self, name: str, coro_factory: Callable, *args, **kwargs) -> str:
        self._evict_expired()

        # Never evict pending/running tasks — reject if at capacity.
        if len(self._tasks) >= MAX_TASKS:
            raise QueueFullError(
                f"Task queue at maximum capacity ({MAX_TASKS}). "
                "Please try again later or scale workers."
            )

        task_id = str(uuid.uuid4())
        task = Task(task_id, name, coro_factory, *args, **kwargs)
        self._tasks[task_id] = task
        await self._queue.put(task)
        logger.info("Task %s (%s) enqueued", task_id, name)
        return task_id

    def get_task(self, task_id: str) -> Optional[Task]:
        return self._tasks.get(task_id)

    def _evict_expired(self):
        now = utc_now()
        cutoff = now - timedelta(hours=TASK_EXPIRY_HOURS)
        expired = []
        for tid, t in self._tasks.items():
            ca = t.created_at
            if isinstance(ca, (int, float)):
                ca = datetime.fromtimestamp(ca)
            if ca < cutoff and t.status in (TaskStatus.COMPLETED, TaskStatus.FAILED):
                expired.append(tid)
        for tid in expired:
            del self._tasks[tid]
        if expired:
            logger.info("Evicted %d expired tasks", len(expired))

    async def _worker_loop(self, worker_id: int):
        logger.debug("Worker %d started", worker_id)
        while self._running:
            task = await self._queue.get()
            if task is None:
                self._queue.task_done()
                break
            try:
                task.status = TaskStatus.RUNNING
                task.started_at = utc_now()
                logger.info("Worker %d executing task %s (%s)", worker_id, task.id, task.name)
                coro = task.coro_factory(*task.args, **task.kwargs)
                task.result = await coro
                task.status = TaskStatus.COMPLETED
            except Exception as e:
                task.status = TaskStatus.FAILED
                task.error = str(e)
                logger.exception("Worker %d task %s (%s) failed", worker_id, task.id, task.name)
            finally:
                task.completed_at = utc_now()
                self._queue.task_done()
        logger.debug("Worker %d stopped", worker_id)
