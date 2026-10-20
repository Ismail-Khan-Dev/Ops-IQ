import asyncio
import logging
from datetime import UTC, datetime
from functools import wraps
from typing import Any, Callable, TypeVar

T = TypeVar("T")

logger = logging.getLogger("ecommerce_ops.utils")


def utc_now() -> datetime:
    """Return the current time as a naive UTC ``datetime``.

    We deliberately return a *naive* UTC datetime so it stays consistent
    with SQLAlchemy's naive ``DateTime`` columns when read back from SQLite
    (and other databases that do not preserve timezone info on read). This
    avoids comparing an aware timestamp against a naive value from the DB.
    """
    return datetime.now(UTC).replace(tzinfo=None)


def utc_now_iso() -> str:
    """Return the current time as an ISO-8601 UTC string."""
    return utc_now().isoformat()


def retry_async(
    func: Callable[..., Any],
    max_retries: int = 3,
    base_delay: float = 1.0,
    backoff: float = 2.0,
    exceptions: tuple = (Exception,),
) -> Callable[..., Any]:
    @wraps(func)
    async def wrapper(*args, **kwargs):
        last_exc = None
        delay = base_delay
        for attempt in range(1, max_retries + 1):
            try:
                return await func(*args, **kwargs)
            except exceptions as e:
                last_exc = e
                if attempt < max_retries:
                    logger.warning(
                        "Retry %d/%d for %s after error: %s",
                        attempt,
                        max_retries,
                        func.__name__,
                        e,
                    )
                    await asyncio.sleep(delay)
                    delay *= backoff
        raise last_exc

    return wrapper
