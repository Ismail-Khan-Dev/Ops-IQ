import logging
from typing import Callable

from tenacity import (
    before_sleep_log,
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

logger = logging.getLogger("ecommerce_ops.infra.retry")

DEFAULT_MAX_ATTEMPTS = 3
DEFAULT_MIN_WAIT = 1.0
DEFAULT_MAX_WAIT = 10.0


def async_retry(
    exceptions: tuple = (Exception,),
    max_attempts: int = DEFAULT_MAX_ATTEMPTS,
    min_wait: float = DEFAULT_MIN_WAIT,
    max_wait: float = DEFAULT_MAX_WAIT,
):
    return retry(
        stop=stop_after_attempt(max_attempts),
        wait=wait_exponential(multiplier=min_wait, max=max_wait),
        retry=retry_if_exception_type(exceptions),
        before_sleep=before_sleep_log(logger, logging.WARNING),
        reraise=True,
    )


def async_retry_decorator(
    exceptions: tuple = (Exception,),
    max_attempts: int = DEFAULT_MAX_ATTEMPTS,
    min_wait: float = DEFAULT_MIN_WAIT,
    max_wait: float = DEFAULT_MAX_WAIT,
):
    def decorator(func: Callable) -> Callable:
        return async_retry(
            exceptions=exceptions,
            max_attempts=max_attempts,
            min_wait=min_wait,
            max_wait=max_wait,
        )(func)

    return decorator
