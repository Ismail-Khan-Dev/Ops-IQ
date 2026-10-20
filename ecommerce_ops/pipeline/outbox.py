"""Transactional outbox retry poller (C5).

The pipeline writes an ``OutboxMessage(status="pending")`` in the same
transaction as its ``ApprovalAction`` BEFORE the live Shopify call. If the
process crashes mid-call, the row stays ``pending`` forever. This poller
sweeps such orphaned rows and redelivers them so the external side effect is
applied at least once, then dead-letters rows that keep failing.

Semantics are at-least-once: a rare duplicate is possible if a call genuinely
outlives the orphan age window, which the Shopify-side idempotency on
``action_id`` is expected to absorb.
"""

import asyncio
import contextlib
import logging
from datetime import timedelta
from typing import Any, Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ecommerce_ops.api.metrics import METRIC_OUTBOX_DEAD_LETTERS
from ecommerce_ops.infra.distributed_lock import DistributedLock
from ecommerce_ops.models import ApprovalAction, OutboxMessage, async_session_factory
from ecommerce_ops.pipeline.runner import execute_shop_action
from ecommerce_ops.utils import utc_now

logger = logging.getLogger("ecommerce_ops.pipeline.outbox")

OUTBOX_SWEEP_INTERVAL_SECONDS = 30
OUTBOX_ORPHAN_AGE_SECONDS = 60
OUTBOX_MAX_RETRY_COUNT = 5
OUTBOX_BATCH_SIZE = 50
OUTBOX_LEADER_TTL_SECONDS = 90


class OutboxSweeper:
    """Periodically redelivers outbox rows stuck in ``pending``/``retrying``."""

    def __init__(
        self,
        interval_seconds: float = OUTBOX_SWEEP_INTERVAL_SECONDS,
        orphan_age_seconds: float = OUTBOX_ORPHAN_AGE_SECONDS,
        max_retry_count: int = OUTBOX_MAX_RETRY_COUNT,
        batch_size: int = OUTBOX_BATCH_SIZE,
        leader_lock: Optional[DistributedLock] = None,
    ) -> None:
        self._interval_seconds = interval_seconds
        self._orphan_age_seconds = orphan_age_seconds
        self._max_retry_count = max_retry_count
        self._batch_size = batch_size
        self._leader_lock = leader_lock or DistributedLock(
            "outbox-sweeper",
            ttl_seconds=OUTBOX_LEADER_TTL_SECONDS,
        )
        self._task: Optional[asyncio.Task[Any]] = None

    async def start(self) -> None:
        """Start the background sweep loop (idempotent)."""
        if self._task is None:
            self._task = asyncio.create_task(self._run(), name="outbox-sweeper")
            logger.info("Outbox sweeper started (interval=%ss)", self._interval_seconds)

    async def stop(self) -> None:
        """Cancel the sweep loop and wait for it to exit."""
        task = self._task
        self._task = None
        if task is not None:
            task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await task

    async def _run(self) -> None:
        while True:
            try:
                acquired = await self._leader_lock.acquire()
                if not acquired:
                    logger.debug("Outbox sweep skipped: another instance is leader")
                    await asyncio.sleep(self._interval_seconds)
                    continue
                try:
                    redelivered = await self.sweep_once()
                    if redelivered:
                        logger.info("Outbox sweep redelivered %d message(s)", redelivered)
                finally:
                    await self._leader_lock.release()
            except asyncio.CancelledError:
                raise
            except Exception:
                logger.exception("Outbox sweep failed")
            await asyncio.sleep(self._interval_seconds)

    async def sweep_once(self) -> int:
        """Sweep one batch of orphaned rows and redeliver them.

        Returns the number of rows processed. Rows are claimed with a
        ``FOR UPDATE SKIP LOCKED`` on PostgreSQL so concurrent sweepers do not
        double-process; SQLite renders a plain SELECT (single-process, safe).
        """
        cutoff = utc_now() - timedelta(seconds=self._orphan_age_seconds)
        async with async_session_factory() as session:
            rows = (
                (
                    await session.execute(
                        select(OutboxMessage)
                        .where(
                            OutboxMessage.status.in_(("pending", "retrying")),
                            OutboxMessage.created_at < cutoff,
                        )
                        .order_by(OutboxMessage.created_at)
                        .limit(self._batch_size)
                        .with_for_update(skip_locked=True)
                    )
                )
                .scalars()
                .all()
            )

        processed = 0
        for row in rows:
            try:
                await self._redeliver(row)
                processed += 1
            except Exception:
                logger.exception("Outbox redelivery failed for message %s", row.id)
        return processed

    async def _dead_letter(self, fresh: OutboxMessage, reason: str, session: AsyncSession) -> None:
        """Mark an outbox row dead and record its dead-letter metric."""
        fresh.status = "dead"
        fresh.error = reason
        await session.commit()
        action_type = str((fresh.payload or {}).get("action_type", "unknown"))
        METRIC_OUTBOX_DEAD_LETTERS.labels(outbox_type=action_type).inc()
        logger.warning("Dead-lettered outbox %s: %s", fresh.id, reason)

    async def _redeliver(self, row: OutboxMessage) -> None:
        """Claim and redeliver a single orphaned outbox row.

        The passed-in row is detached (it was selected in ``sweep_once``'s
        session), so every mutation re-loads the row by id inside its own
        transaction.
        """
        async with async_session_factory() as session:
            fresh = await session.get(OutboxMessage, row.id)
            if fresh is None:
                return
            action = await session.get(ApprovalAction, row.action_id)
            if action is None:
                await self._dead_letter(
                    fresh, "approval_action not found; cannot redeliver", session
                )
                return
            if action.status == "executed":
                # The side effect already landed; just reconcile the outbox row.
                fresh.status = "sent"
                fresh.sent_at = fresh.sent_at or utc_now()
                await session.commit()
                logger.info("Outbox %s reconciled (action already executed)", row.id)
                return
            if fresh.retry_count >= self._max_retry_count:
                await self._dead_letter(fresh, "max retry count exceeded", session)
                return
            fresh.retry_count += 1
            fresh.status = "retrying"
            await session.commit()

        executed_ok, execution_msg = await execute_shop_action(action)

        async with async_session_factory() as session:
            fresh = await session.get(OutboxMessage, row.id)
            if fresh is None:
                return
            if executed_ok:
                fresh.status = "sent"
                fresh.sent_at = utc_now()
                fresh.error = None
            else:
                fresh.status = "failed"
                fresh.error = execution_msg
            await session.commit()

        logger.info(
            "Outbox redelivery message=%s action=%s → %s",
            row.id,
            row.action_id,
            "sent" if executed_ok else f"failed: {execution_msg}",
        )
