"""Regression tests for loop-safe asyncio primitives.

Background
----------
``asyncio.Lock`` binds to the running event loop the first time it is
*contended*, then raises ``RuntimeError: ... is bound to a different event
loop`` if the same instance is used from another loop. Process-level
singletons (WebSocket manager, circuit breakers, pipeline locks) are shared
across event loops — ``uvicorn --reload``, multiple workers, and
pytest-asyncio's fresh per-test loop — so they need ``LoopAwareLock``.
"""

import asyncio
import uuid

import pytest

from ecommerce_ops.infra.async_utils import LoopAwareLock
from ecommerce_ops.infra.circuit_breaker import CircuitBreaker
from ecommerce_ops.pipeline.runner import _get_pipeline_lock


def _contended(lock) -> None:
    """Run two tasks that contend for ``lock`` inside one event loop.

    The waiter forces the lock to bind to the loop it is running on.
    """

    async def run() -> None:
        async def holder() -> None:
            async with lock:
                await asyncio.sleep(0.01)

        async def waiter() -> None:
            async with lock:
                pass

        await asyncio.gather(holder(), waiter())

    asyncio.run(run())


# ── The bug, characterized ────────────────────────────────────────────


def test_plain_asyncio_lock_fails_across_event_loops():
    """Documents why LoopAwareLock exists: a shared asyncio.Lock poisons the
    second event loop it is contended on."""
    lock = asyncio.Lock()
    _contended(lock)  # binds to loop 1

    with pytest.raises(RuntimeError, match="bound to a different event loop"):
        _contended(lock)  # loop 2 -> RuntimeError


def test_loop_aware_lock_survives_event_loop_reuse():
    """The regression: a shared LoopAwareLock must rebind, not raise."""
    lock = LoopAwareLock()
    _contended(lock)  # binds to loop 1
    _contended(lock)  # rebinds to loop 2 — must not raise
    _contended(lock)  # and again, for good measure


# ── Correctness ───────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_loop_aware_lock_enforces_mutual_exclusion():
    lock = LoopAwareLock()
    active = 0
    max_active = 0

    async def worker() -> None:
        nonlocal active, max_active
        async with lock:
            active += 1
            max_active = max(max_active, active)
            await asyncio.sleep(0.005)
            active -= 1

    await asyncio.gather(*(worker() for _ in range(10)))
    assert max_active == 1


@pytest.mark.asyncio
async def test_loop_aware_lock_locked_reports_state():
    lock = LoopAwareLock()
    assert lock.locked() is False
    async with lock:
        assert lock.locked() is True
    assert lock.locked() is False


@pytest.mark.asyncio
async def test_loop_aware_lock_release_on_exception():
    lock = LoopAwareLock()
    with pytest.raises(ValueError):
        async with lock:
            raise ValueError("boom")
    assert lock.locked() is False


# ── The real singletons ───────────────────────────────────────────────


def test_circuit_breaker_reusable_across_event_loops():
    """Module-level CircuitBreaker singletons are shared across loops."""
    breaker = CircuitBreaker(name=f"loop-reuse-{uuid.uuid4().hex}")

    async def run() -> str:
        async def ok() -> str:
            return "ok"

        results = await asyncio.gather(breaker.call(ok), breaker.call(ok))
        return results[0]

    asyncio.run(run())  # binds to loop 1
    assert asyncio.run(run()) == "ok"  # rebinds — must not raise


def test_pipeline_lock_reusable_across_event_loops():
    """Per-run pipeline locks live in a module-level dict across loops."""
    run_id = f"loop-reuse-{uuid.uuid4().hex}"
    lock = _get_pipeline_lock(run_id)
    assert isinstance(lock, LoopAwareLock)

    _contended(lock)  # binds to loop 1
    _contended(lock)  # rebinds to loop 2 — must not raise
