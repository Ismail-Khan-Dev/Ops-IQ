"""Tests for the transactional outbox retry poller (C5).

An ``OutboxMessage(status="pending")`` stuck past the orphan-age window means
the process crashed in the middle of a live Shopify call. The sweeper must
redeliver such rows (at least once), reconcile rows whose action already
landed, and dead-letter rows that can never succeed.
"""

from datetime import timedelta
from unittest.mock import AsyncMock, patch

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from ecommerce_ops.models.db import ApprovalAction, Base, OutboxMessage
from ecommerce_ops.pipeline.outbox import OutboxSweeper
from ecommerce_ops.utils import utc_now


@pytest_asyncio.fixture
async def db_factory():
    engine = create_async_engine("sqlite+aiosqlite://", echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)
    yield factory
    await engine.dispose()


def _action(action_id: str, status: str = "executing") -> ApprovalAction:
    return ApprovalAction(
        id=action_id,
        agent="FraudAgent",
        action_type="fraud_hold",
        status=status,
        risk_level="high",
        confidence_score=0.95,
        created_at=utc_now() - timedelta(hours=2),
        requires_hitl=False,
        shadow_mode=False,
        payload={"order_id": "9001"},
        evidence=[],
        impact={"financial_impact": 10.0, "reversible": True},
    )


def _outbox(action_id: str, status: str = "pending", age_hours: int = 2) -> OutboxMessage:
    return OutboxMessage(
        action_id=action_id,
        status=status,
        payload={"order_id": "9001"},
        created_at=utc_now() - timedelta(hours=age_hours),
        retry_count=0,
    )


async def _add(db_factory, *rows) -> None:
    async with db_factory() as s:
        for row in rows:
            s.add(row)
        await s.commit()


def _sweeper() -> OutboxSweeper:
    return OutboxSweeper(
        interval_seconds=3600,
        orphan_age_seconds=0,
        max_retry_count=2,
        batch_size=10,
    )


@pytest.mark.asyncio
async def test_missing_action_is_dead_lettered(db_factory):
    async with db_factory() as s:
        s.add(_outbox("ghost-action"))
        await s.commit()

    sweeper = _sweeper()
    with patch("ecommerce_ops.pipeline.outbox.async_session_factory", db_factory):
        processed = await sweeper.sweep_once()

    assert processed == 1
    async with db_factory() as s:
        row = await s.get(OutboxMessage, 1)
    assert row.status == "dead"
    assert "not found" in (row.error or "")


@pytest.mark.asyncio
async def test_already_executed_action_is_reconciled(db_factory):
    action = _action("a-exec", status="executed")
    outbox = _outbox("a-exec")
    await _add(db_factory, action, outbox)

    sweeper = _sweeper()
    with (
        patch("ecommerce_ops.pipeline.outbox.async_session_factory", db_factory),
        patch(
            "ecommerce_ops.pipeline.outbox.execute_shop_action",
            new_callable=AsyncMock,
        ) as mock_exec,
    ):
        processed = await sweeper.sweep_once()

    assert processed == 1
    mock_exec.assert_not_awaited()
    async with db_factory() as s:
        row = await s.get(OutboxMessage, outbox.id)
    assert row.status == "sent"
    assert row.sent_at is not None


@pytest.mark.asyncio
async def test_successful_redelivery_marks_sent(db_factory):
    action = _action("a-ok", status="executing")
    outbox = _outbox("a-ok")
    await _add(db_factory, action, outbox)

    sweeper = _sweeper()
    with (
        patch("ecommerce_ops.pipeline.outbox.async_session_factory", db_factory),
        patch(
            "ecommerce_ops.pipeline.outbox.execute_shop_action",
            new_callable=AsyncMock,
            return_value=(True, "Applied FRAUD_HOLD to order 9001"),
        ) as mock_exec,
    ):
        processed = await sweeper.sweep_once()

    assert processed == 1
    mock_exec.assert_awaited_once()
    async with db_factory() as s:
        row = await s.get(OutboxMessage, outbox.id)
        action_refreshed = await s.get(ApprovalAction, "a-ok")
    assert row.status == "sent"
    assert row.retry_count == 1
    # The sweeper only records the outbox outcome; the action's own status is
    # left alone unless the pipeline is re-run for it.
    assert action_refreshed.status == "executing"


@pytest.mark.asyncio
async def test_failed_redelivery_marks_failed_with_error(db_factory):
    action = _action("a-fail", status="executing")
    outbox = _outbox("a-fail")
    await _add(db_factory, action, outbox)

    sweeper = _sweeper()
    with (
        patch("ecommerce_ops.pipeline.outbox.async_session_factory", db_factory),
        patch(
            "ecommerce_ops.pipeline.outbox.execute_shop_action",
            new_callable=AsyncMock,
            return_value=(False, "Shopify not configured"),
        ),
    ):
        processed = await sweeper.sweep_once()

    assert processed == 1
    async with db_factory() as s:
        row = await s.get(OutboxMessage, outbox.id)
    assert row.status == "failed"
    assert row.error == "Shopify not configured"


@pytest.mark.asyncio
async def test_max_retry_count_dead_letters_without_executing(db_factory):
    action = _action("a-max", status="executing")
    outbox = _outbox("a-max")
    outbox.retry_count = 2  # max_retry_count == 2 → cannot retry again
    await _add(db_factory, action, outbox)

    sweeper = _sweeper()
    with (
        patch("ecommerce_ops.pipeline.outbox.async_session_factory", db_factory),
        patch(
            "ecommerce_ops.pipeline.outbox.execute_shop_action",
            new_callable=AsyncMock,
        ) as mock_exec,
    ):
        processed = await sweeper.sweep_once()

    assert processed == 1
    mock_exec.assert_not_awaited()
    async with db_factory() as s:
        row = await s.get(OutboxMessage, outbox.id)
    assert row.status == "dead"
    assert "max retry count" in (row.error or "")


@pytest.mark.asyncio
async def test_recent_pending_rows_are_not_swept(db_factory):
    action = _action("a-recent", status="executing")
    outbox = _outbox("a-recent", age_hours=0)  # just created → inside orphan window
    await _add(db_factory, action, outbox)

    sweeper = OutboxSweeper(
        interval_seconds=3600,
        orphan_age_seconds=3600,  # only sweep rows older than 1h
        max_retry_count=2,
        batch_size=10,
    )
    with (
        patch("ecommerce_ops.pipeline.outbox.async_session_factory", db_factory),
        patch(
            "ecommerce_ops.pipeline.outbox.execute_shop_action",
            new_callable=AsyncMock,
        ) as mock_exec,
    ):
        processed = await sweeper.sweep_once()

    assert processed == 0
    mock_exec.assert_not_awaited()
    async with db_factory() as s:
        row = await s.get(OutboxMessage, outbox.id)
    assert row.status == "pending"


@pytest.mark.asyncio
async def test_stuck_retrying_row_is_picked_up_again(db_factory):
    action = _action("a-stuck", status="executing")
    outbox = _outbox("a-stuck", status="retrying")
    await _add(db_factory, action, outbox)

    sweeper = _sweeper()
    with (
        patch("ecommerce_ops.pipeline.outbox.async_session_factory", db_factory),
        patch(
            "ecommerce_ops.pipeline.outbox.execute_shop_action",
            new_callable=AsyncMock,
            return_value=(True, "ok"),
        ),
    ):
        processed = await sweeper.sweep_once()

    assert processed == 1
    async with db_factory() as s:
        row = await s.get(OutboxMessage, outbox.id)
    assert row.status == "sent"


@pytest.mark.asyncio
async def test_start_stop_lifecycle_cancels_cleanly():
    sweeper = _sweeper()
    await sweeper.start()
    assert sweeper._task is not None
    await sweeper.stop()
    assert sweeper._task is None
