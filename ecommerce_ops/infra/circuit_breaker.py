import logging
import time
from enum import Enum

from ecommerce_ops.infra.async_utils import LoopAwareLock

logger = logging.getLogger("ecommerce_ops.infra.circuit_breaker")


class CircuitState(Enum):
    CLOSED = "closed"
    OPEN = "open"
    HALF_OPEN = "half_open"


class CircuitBreaker:
    def __init__(
        self,
        name: str,
        failure_threshold: int = 5,
        recovery_timeout: float = 30.0,
        half_open_max_attempts: int = 1,
    ):
        self.name = name
        self.failure_threshold = failure_threshold
        self.recovery_timeout = recovery_timeout
        self.half_open_max_attempts = half_open_max_attempts

        self._state = CircuitState.CLOSED
        self._failure_count = 0
        self._last_failure_time = 0.0
        self._half_open_attempts = 0
        # LoopAwareLock: module-level CircuitBreaker singletons are shared across
        # event loops (uvicorn --reload, per-test loops), so a plain asyncio.Lock
        # would bind to the first loop it contends on and break the next one.
        self._lock = LoopAwareLock()

    @property
    def state(self) -> CircuitState:
        return self._state

    async def call(self, func, *args, **kwargs):
        async with self._lock:
            if self._state == CircuitState.OPEN:
                if time.monotonic() - self._last_failure_time >= self.recovery_timeout:
                    self._state = CircuitState.HALF_OPEN
                    self._half_open_attempts = 0
                    logger.info("Circuit %s: OPEN → HALF_OPEN", self.name)
                else:
                    raise CircuitBreakerOpenError(
                        f"Circuit '{self.name}' is OPEN (cooldown {self.recovery_timeout}s)"
                    )

            if self._state == CircuitState.HALF_OPEN:
                if self._half_open_attempts >= self.half_open_max_attempts:
                    raise CircuitBreakerOpenError(
                        f"Circuit '{self.name}' is HALF_OPEN (all probe attempts used)"
                    )
                self._half_open_attempts += 1

        try:
            result = await func(*args, **kwargs)
        except Exception as e:
            async with self._lock:
                self._failure_count += 1
                self._last_failure_time = time.monotonic()
                if self._failure_count >= self.failure_threshold:
                    self._state = CircuitState.OPEN
                    logger.warning(
                        "Circuit %s: %s → OPEN (%d failures)",
                        self.name,
                        self._state.value,
                        self._failure_count,
                    )
                else:
                    logger.debug(
                        "Circuit %s: failure %d/%d",
                        self.name,
                        self._failure_count,
                        self.failure_threshold,
                    )
            raise e

        async with self._lock:
            if self._state == CircuitState.HALF_OPEN:
                logger.info("Circuit %s: HALF_OPEN → CLOSED (probe succeeded)", self.name)
            self._state = CircuitState.CLOSED
            self._failure_count = 0
            self._half_open_attempts = 0

        return result

    async def reset(self):
        async with self._lock:
            self._state = CircuitState.CLOSED
            self._failure_count = 0
            self._half_open_attempts = 0
            logger.info("Circuit %s: reset to CLOSED", self.name)


class CircuitBreakerOpenError(Exception):
    pass
