"""
Redis-Backed Task Queue
Replaces in-memory asyncio.Queue for production use.

Hardening (H3):
- Lease/TTL on dequeue: tasks carry a lease expiration tied to the worker.
  If the worker dies, the task is requeued.
- Startup requeue: on startup, scan the processing set for tasks whose
  lease has expired and re-enqueue them.
- Graceful drain on shutdown: wait for in-flight tasks to finish (bounded
  by a drain timeout) instead of force-cancelling mid-execution.
- 503-on-full enqueue: reject enqueue with QueueFullError when the pending
  queue reaches max_queue_size (never silently block or drop).
- Budget-aligned timeout: per-task timeout is capped to the pipeline budget
  (max 300 s) so a single slow task cannot stall a worker indefinitely.
"""

import asyncio
import contextlib
import json
import logging
import time
import uuid
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any, Callable, Coroutine, Dict, List, Optional, Set

logger = logging.getLogger("ecommerce_ops.infra.redis_task_queue")

# Maximum per-task timeout (pipeline budget). A single task can never
# monopolise a worker for longer than this.
MAX_TASK_TIMEOUT_SECONDS = 300.0
# How long a task lease lasts before it is considered abandoned.
LEASE_TTL_SECONDS = 120.0
# How often the stale-lease sweeper runs.
LEASE_SWEEP_INTERVAL_SECONDS = 30.0
# Grace period added to the drain timeout during shutdown.
DRAIN_GRACE_SECONDS = 5.0


class QueueFullError(Exception):
    """Raised when the task queue is at capacity and cannot accept new tasks."""


class TaskStatus(StrEnum):
    PENDING = "pending"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"
    RETRY = "retry"
    CANCELLED = "cancelled"


class TaskPriority(StrEnum):
    LOW = "low"
    NORMAL = "normal"
    HIGH = "high"
    CRITICAL = "critical"


@dataclass
class Task:
    """Task definition."""

    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    name: str = ""
    payload: Dict[str, Any] = field(default_factory=dict)
    status: TaskStatus = TaskStatus.PENDING
    priority: TaskPriority = TaskPriority.NORMAL
    created_at: float = field(default_factory=time.time)
    started_at: Optional[float] = None
    completed_at: Optional[float] = None
    result: Optional[Any] = None
    error: Optional[str] = None
    retry_count: int = 0
    max_retries: int = 3
    timeout_seconds: float = 300.0
    tags: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "payload": self.payload,
            "status": self.status.value,
            "priority": self.priority.value,
            "created_at": self.created_at,
            "started_at": self.started_at,
            "completed_at": self.completed_at,
            "result": self.result,
            "error": self.error,
            "retry_count": self.retry_count,
            "max_retries": self.max_retries,
            "timeout_seconds": self.timeout_seconds,
            "tags": self.tags,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "Task":
        return cls(
            id=data.get("id", str(uuid.uuid4())),
            name=data.get("name", ""),
            payload=data.get("payload", {}),
            status=TaskStatus(data.get("status", "pending")),
            priority=TaskPriority(data.get("priority", "normal")),
            created_at=data.get("created_at", time.time()),
            started_at=data.get("started_at"),
            completed_at=data.get("completed_at"),
            result=data.get("result"),
            error=data.get("error"),
            retry_count=data.get("retry_count", 0),
            max_retries=data.get("max_retries", 3),
            timeout_seconds=data.get("timeout_seconds", 300),
            tags=data.get("tags", []),
        )


class RedisTaskQueue:
    """
    Redis-backed task queue with priority, retry, and timeout support.
    Works across multiple worker instances with lease-based ownership.
    """

    QUEUE_KEY = "taskqueue:pending"
    PROCESSING_KEY = "taskqueue:processing"
    RESULTS_PREFIX = "taskqueue:result:"
    TASK_PREFIX = "taskqueue:task:"

    def __init__(self, redis_client, num_workers: int = 2, max_queue_size: int = 1000):
        self.redis = redis_client
        self.num_workers = num_workers
        self.max_queue_size = max_queue_size
        self._handlers: Dict[str, Callable] = {}
        self._workers: List[asyncio.Task] = []
        self._sweeper_task: Optional[asyncio.Task] = None
        self._running = False
        self._inflight: Set[str] = set()  # task IDs currently being processed by this worker set
        self._stats = {"enqueued": 0, "completed": 0, "failed": 0, "retried": 0}

    def register_handler(self, task_name: str, handler: Callable[..., Coroutine]):
        """Register a handler for a task type."""
        self._handlers[task_name] = handler
        logger.info(f"Registered handler for task: {task_name}")

    async def enqueue(
        self,
        task_name: str,
        payload: Dict[str, Any],
        priority: TaskPriority = TaskPriority.NORMAL,
        timeout_seconds: float = 300.0,
        max_retries: int = 3,
        tags: Optional[List[str]] = None,
    ) -> str:
        """Enqueue a task. Returns task ID.

        Raises QueueFullError if the pending queue is at capacity.
        """
        # Check queue size BEFORE accepting the task (503-on-full).
        queue_len = await self.redis.zcard(self.QUEUE_KEY)
        if queue_len >= self.max_queue_size:
            logger.warning(
                "Queue full: %d/%d tasks pending. Rejecting enqueue.",
                queue_len,
                self.max_queue_size,
            )
            raise QueueFullError(
                f"Task queue at maximum capacity ({self.max_queue_size}). "
                "Please try again later or scale workers."
            )

        # Budget-align timeout: never exceed the pipeline budget.
        timeout_seconds = min(timeout_seconds, MAX_TASK_TIMEOUT_SECONDS)

        task = Task(
            name=task_name,
            payload=payload,
            priority=priority,
            timeout_seconds=timeout_seconds,
            max_retries=max_retries,
            tags=tags or [],
        )

        try:
            await self.redis.hset(
                f"{self.TASK_PREFIX}{task.id}",
                mapping=self._serialize_task(task),
            )
            await self.redis.expire(f"{self.TASK_PREFIX}{task.id}", 86400)  # 24h TTL

            score = self._priority_score(priority)
            await self.redis.zadd(self.QUEUE_KEY, {task.id: score})

            self._stats["enqueued"] += 1
            logger.info(f"Enqueued task {task.id} ({task_name}) with priority {priority.value}")
            return task.id

        except Exception as e:
            logger.error(f"Failed to enqueue task: {e}")
            raise

    async def dequeue(self) -> Optional[Task]:
        """Dequeue the highest priority task and claim it with a lease."""
        try:
            # Atomic claim: ZPOPMAX + verify task still exists in pending
            # is not atomic, but ZPOPMAX removes from the sorted set so no
            # other worker will get the same task.
            result = await self.redis.zpopmax(self.QUEUE_KEY, count=1)
            if not result:
                return None

            task_id = result[0][0]
            if isinstance(task_id, bytes):
                task_id = task_id.decode()

            # Get task data
            task_data = await self.redis.hgetall(f"{self.TASK_PREFIX}{task_id}")
            if not task_data:
                return None

            task = self._dict_to_task(task_data)
            task.status = TaskStatus.PROCESSING
            task.started_at = time.time()

            worker_id = self._worker_id
            lease_expiry = time.time() + LEASE_TTL_SECONDS

            # Move to processing with lease info
            await self.redis.hset(
                f"{self.TASK_PREFIX}{task.id}",
                mapping={
                    "status": "processing",
                    "started_at": str(task.started_at),
                    "leased_by": worker_id,
                    "lease_expires_at": str(lease_expiry),
                },
            )
            await self.redis.sadd(self.PROCESSING_KEY, task.id)
            self._inflight.add(task.id)

            return task

        except Exception as e:
            logger.error(f"Failed to dequeue task: {e}")
            return None

    async def heartbeat(self, task_id: str):
        """Extend the lease on an in-flight task."""
        lease_expiry = time.time() + LEASE_TTL_SECONDS
        await self.redis.hset(
            f"{self.TASK_PREFIX}{task_id}",
            mapping={
                "lease_expires_at": str(lease_expiry),
            },
        )

    async def complete_task(self, task_id: str, result: Any = None):
        """Mark a task as completed."""
        try:
            await self.redis.hset(
                f"{self.TASK_PREFIX}{task_id}",
                mapping={
                    "status": "completed",
                    "completed_at": str(time.time()),
                    "result": json.dumps(result) if result else "",
                    "leased_by": "",
                    "lease_expires_at": "",
                },
            )
            await self.redis.srem(self.PROCESSING_KEY, task_id)
            await self.redis.setex(
                f"{self.RESULTS_PREFIX}{task_id}", 3600, json.dumps(result) if result else ""
            )
            self._inflight.discard(task_id)

            self._stats["completed"] += 1
            logger.info(f"Task {task_id} completed")

        except Exception as e:
            logger.error(f"Failed to complete task: {e}")

    async def fail_task(self, task_id: str, error: str, retry: bool = True):
        """Mark a task as failed, optionally retrying."""
        try:
            task_data = await self.redis.hgetall(f"{self.TASK_PREFIX}{task_id}")
            if not task_data:
                return

            task = self._dict_to_task(task_data)

            if retry and task.retry_count < task.max_retries:
                task.retry_count += 1
                task.status = TaskStatus.RETRY
                await self.redis.hset(
                    f"{self.TASK_PREFIX}{task_id}",
                    mapping={
                        "status": "retry",
                        "retry_count": str(task.retry_count),
                        "error": error,
                        "leased_by": "",
                        "lease_expires_at": "",
                    },
                )
                # Re-enqueue with exponential backoff score (lower priority)
                await self.redis.zadd(
                    self.QUEUE_KEY, {task_id: self._priority_score(TaskPriority.LOW)}
                )
                self._stats["retried"] += 1
                logger.info(f"Task {task_id} retrying ({task.retry_count}/{task.max_retries})")
            else:
                task.status = TaskStatus.FAILED
                await self.redis.hset(
                    f"{self.TASK_PREFIX}{task_id}",
                    mapping={
                        "status": "failed",
                        "completed_at": str(time.time()),
                        "error": error,
                        "leased_by": "",
                        "lease_expires_at": "",
                    },
                )
                self._stats["failed"] += 1
                logger.error(f"Task {task_id} failed: {error}")

            await self.redis.srem(self.PROCESSING_KEY, task_id)
            self._inflight.discard(task_id)

        except Exception as e:
            logger.error(f"Failed to handle task failure: {e}")

    async def get_task(self, task_id: str) -> Optional[Task]:
        """Get task by ID."""
        try:
            task_data = await self.redis.hgetall(f"{self.TASK_PREFIX}{task_id}")
            if not task_data:
                return None
            return self._dict_to_task(task_data)
        except Exception as e:
            logger.error(f"Failed to get task: {e}")
            return None

    async def get_result(self, task_id: str, timeout: float = 30.0) -> Any:
        """Wait for and get task result."""
        start = time.time()
        while time.time() - start < timeout:
            task = await self.get_task(task_id)
            if task and task.status in [TaskStatus.COMPLETED, TaskStatus.FAILED]:
                return task.result if task.status == TaskStatus.COMPLETED else None
            await asyncio.sleep(0.1)
        return None

    async def cancel_task(self, task_id: str) -> bool:
        """Cancel a pending task."""
        try:
            removed = await self.redis.zrem(self.QUEUE_KEY, task_id)
            if removed:
                await self.redis.hset(
                    f"{self.TASK_PREFIX}{task_id}",
                    mapping={"status": "cancelled"},
                )
                return True
            return False
        except Exception as e:
            logger.error(f"Failed to cancel task: {e}")
            return False

    async def requeue_stale_processing(self) -> int:
        """Find tasks in PROCESSING whose lease has expired and re-enqueue them.

        Returns the number of requeued tasks.
        """
        now = time.time()
        try:
            processing_ids = await self.redis.smembers(self.PROCESSING_KEY)
        except Exception:
            return 0

        requeued = 0
        for raw_id in processing_ids:
            task_id = raw_id.decode() if isinstance(raw_id, bytes) else raw_id
            try:
                lease_str = await self.redis.hget(
                    f"{self.TASK_PREFIX}{task_id}", "lease_expires_at"
                )
                if not lease_str:
                    continue
                lease = float(lease_str.decode() if isinstance(lease_str, bytes) else lease_str)
                if lease > now:
                    continue  # lease still valid

                # Lease expired — requeue
                priority_str = await self.redis.hget(f"{self.TASK_PREFIX}{task_id}", "priority")
                priority_str = (
                    priority_str.decode() if isinstance(priority_str, bytes) else priority_str
                )
                try:
                    priority = TaskPriority(priority_str)
                except ValueError:
                    priority = TaskPriority.NORMAL

                await self.redis.hset(
                    f"{self.TASK_PREFIX}{task_id}",
                    mapping={
                        "status": "pending",
                        "leased_by": "",
                        "lease_expires_at": "",
                    },
                )
                await self.redis.zadd(self.QUEUE_KEY, {task_id: self._priority_score(priority)})
                await self.redis.srem(self.PROCESSING_KEY, task_id)
                requeued += 1
                logger.warning("Requeued stale task %s (expired lease)", task_id)
            except Exception as e:
                logger.error(f"Error requeuing stale task {task_id}: {e}")

        if requeued:
            logger.info("Requeued %d stale processing tasks", requeued)
        return requeued

    async def _lease_sweeper_loop(self):
        """Periodically scan for tasks whose lease has expired."""
        while self._running:
            try:
                await self.requeue_stale_processing()
            except Exception as e:
                logger.error(f"Lease sweeper error: {e}")
            try:
                await asyncio.sleep(LEASE_SWEEP_INTERVAL_SECONDS)
            except asyncio.CancelledError:
                break

    async def start(self):
        """Start worker tasks and sweeper."""
        if self._running:
            return
        self._running = True
        self._worker_id = str(uuid.uuid4())

        # Requeue any tasks left in PROCESSING from a previous run.
        requeued = await self.requeue_stale_processing()
        if requeued:
            logger.info("Startup: requeued %d stale tasks", requeued)

        for i in range(self.num_workers):
            worker = asyncio.create_task(self._worker_loop(f"worker-{i}"))
            self._workers.append(worker)

        # Start the lease-sweeper.
        self._sweeper_task = asyncio.create_task(self._lease_sweeper_loop())
        logger.info(f"Started {self.num_workers} workers")

    async def stop(self, wait: bool = True, drain_timeout: float = 30.0):
        """Stop worker tasks gracefully.

        If ``wait`` is True, waits up to ``drain_timeout`` seconds for
        in-flight tasks to complete before force-cancelling.
        """
        self._running = False

        # Signal workers to drain.
        for _ in range(self.num_workers):
            with contextlib.suppress(Exception):
                await self._queue_put_none()

        if self._sweeper_task:
            self._sweeper_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._sweeper_task

        if wait:
            # Give in-flight tasks a bounded time to finish.
            try:
                await asyncio.wait_for(
                    asyncio.gather(*self._workers, return_exceptions=True),
                    timeout=drain_timeout,
                )
            except TimeoutError:
                logger.warning("Drain timeout (%.1fs) exceeded; cancelling workers", drain_timeout)

        for worker in self._workers:
            if not worker.done():
                worker.cancel()

        await asyncio.gather(*self._workers, return_exceptions=True)
        self._workers.clear()
        self._inflight.clear()
        logger.info("Workers stopped")

    async def _queue_put_none(self):
        """Send a sentinel to one worker's input queue (no-op for Redis)."""
        pass

    async def _worker_loop(self, worker_id: str):
        """Worker loop that processes tasks with lease-based ownership."""
        logger.info(f"{worker_id} started")
        while self._running:
            try:
                task = await self.dequeue()
                if not task:
                    await asyncio.sleep(0.5)
                    continue

                handler = self._handlers.get(task.name)
                if not handler:
                    await self.fail_task(task.id, f"No handler for task: {task.name}", retry=False)
                    continue

                # Budget-aligned timeout for this task.
                effective_timeout = min(task.timeout_seconds, MAX_TASK_TIMEOUT_SECONDS)

                try:
                    # Run with heartbeat to keep the lease alive while executing.
                    result = await self._execute_with_lease_heartbeat(
                        task, handler, effective_timeout
                    )
                    await self.complete_task(task.id, result)
                except TimeoutError:
                    await self.fail_task(task.id, f"Task timed out after {effective_timeout}s")
                except Exception as e:
                    await self.fail_task(task.id, str(e))

            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"{worker_id} error: {e}")
                await asyncio.sleep(1)

        logger.info(f"{worker_id} stopped")

    async def _execute_with_lease_heartbeat(self, task: Task, handler: Callable, timeout: float):
        """Execute a task handler with periodic lease heartbeats."""
        heartbeat_interval = min(LEASE_TTL_SECONDS / 3, 20.0)
        heartbeat_task = asyncio.create_task(self._periodic_heartbeat(task.id, heartbeat_interval))
        try:
            return await asyncio.wait_for(handler(task.payload), timeout=timeout)
        finally:
            heartbeat_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await heartbeat_task

    async def _periodic_heartbeat(self, task_id: str, interval: float):
        """Send lease heartbeats while a task is executing."""
        while True:
            try:
                await asyncio.sleep(interval)
                await self.heartbeat(task_id)
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.debug(f"Heartbeat to task {task_id} failed: {e}")

    def get_stats(self) -> Dict[str, Any]:
        """Get queue statistics."""
        return {
            **self._stats,
            "handlers": list(self._handlers.keys()),
            "workers": self.num_workers,
            "inflight": len(self._inflight),
        }

    @staticmethod
    def _priority_score(priority: TaskPriority) -> float:
        """Convert priority to score (higher = processed first)."""
        scores = {
            TaskPriority.CRITICAL: 1000,
            TaskPriority.HIGH: 100,
            TaskPriority.NORMAL: 10,
            TaskPriority.LOW: 1,
        }
        return scores.get(priority, 10)

    @staticmethod
    def _serialize_task(task: Task) -> Dict[str, Any]:
        """Serialize a Task to a Redis hash-friendly dict."""
        return {
            k: json.dumps(v) if isinstance(v, (dict, list)) else str(v)
            for k, v in task.to_dict().items()
        }

    @staticmethod
    def _dict_to_task(data: Dict[str, Any]) -> Task:
        """Convert Redis hash to Task."""

        def get(key, default=""):
            val = data.get(key, default)
            return val.decode() if isinstance(val, bytes) else val

        return Task(
            id=get("id"),
            name=get("name"),
            payload=json.loads(get("payload", "{}")),
            status=TaskStatus(get("status", "pending")),
            priority=TaskPriority(get("priority", "normal")),
            created_at=float(get("created_at", time.time())),
            started_at=float(get("started_at")) if get("started_at") else None,
            completed_at=float(get("completed_at")) if get("completed_at") else None,
            result=json.loads(get("result", "null")) if get("result") else None,
            error=get("error") or None,
            retry_count=int(get("retry_count", 0)),
            max_retries=int(get("max_retries", 3)),
            timeout_seconds=float(get("timeout_seconds", 300)),
            tags=json.loads(get("tags", "[]")),
        )
