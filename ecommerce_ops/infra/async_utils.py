"""
Loop-safe asyncio primitives for process-level singletons.

Why this exists
---------------
``asyncio.Lock`` binds to the running event loop the first time it is
*contended*, and raises ``RuntimeError: ... is bound to a different event
loop`` if the same instance is later used from another loop. Several
components in this project are process-level singletons that are shared
across event loops:

* the WebSocket ``ConnectionManager`` (``api/ws.py``)
* module-level ``CircuitBreaker`` instances (``infra/circuit_breaker.py``)
* the per-run pipeline locks (``pipeline/runner.py``)

Under ``uvicorn --reload``, multiple workers, or pytest-asyncio's fresh
per-test event loop, those locks bind to the first loop they contend on and
then poison every subsequent loop.

``LoopAwareLock`` is a drop-in replacement: it transparently rebinds to the
current running loop, so a singleton can be shared safely across loops while
still providing correct mutual exclusion *within* a single loop.
"""

import asyncio
from typing import Optional


class LoopAwareLock:
    """An ``asyncio.Lock`` that rebinds when used from a new event loop.

    Drop-in replacement — use ``async with lock:`` exactly as you would with
    ``asyncio.Lock``. Mutual exclusion is preserved within one event loop; when
    the running loop changes, a fresh lock is bound to it.
    """

    __slots__ = ("_lock", "_loop")

    def __init__(self) -> None:
        self._lock: Optional[asyncio.Lock] = None
        self._loop: Optional[asyncio.AbstractEventLoop] = None

    async def __aenter__(self) -> "LoopAwareLock":
        loop = asyncio.get_running_loop()
        if self._lock is None or self._loop is not loop:
            self._lock = asyncio.Lock()
            self._loop = loop
        await self._lock.acquire()
        return self

    async def __aexit__(self, exc_type, exc, tb) -> None:
        self._lock.release()

    def locked(self) -> bool:
        return self._lock is not None and self._lock.locked()
