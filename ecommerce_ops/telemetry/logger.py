import logging
import sys
from typing import Any

import structlog

from ecommerce_ops.config import settings
from ecommerce_ops.security.secrets_redact import (
    SecretRedactingFilter,
    redact_secrets,
)


def configure_logger() -> None:
    """Configure stdlib logging so that every logger emits structured output.

    The codebase logs through vanilla ``logging.getLogger(...)``, so instead of
    rewriting every call site we route the stdlib root handler through
    structlog's ``ProcessorFormatter``: production emits JSON lines, dev emits
    colored console output. This keeps the audit claim ("structured JSON logs
    in production") true rather than dead configuration.
    """

    shared_processors: list[Any] = [
        structlog.stdlib.add_log_level,
        structlog.stdlib.add_logger_name,
        structlog.contextvars.merge_contextvars,
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.StackInfoRenderer(),
        structlog.processors.format_exc_info,
        structlog.processors.UnicodeDecoder(),
        redact_secrets,
    ]

    renderer: Any = (
        structlog.processors.JSONRenderer()
        if settings.ENV == "production"
        else structlog.dev.ConsoleRenderer(colors=True)
    )

    formatter = structlog.stdlib.ProcessorFormatter(
        processor=renderer,
        foreign_pre_chain=shared_processors,
    )

    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(formatter)
    handler.addFilter(SecretRedactingFilter())

    root = logging.getLogger()
    root.handlers = [handler]
    root.setLevel(logging.INFO if not settings.DEBUG else logging.DEBUG)

    structlog.configure(
        processors=[
            *shared_processors,
            structlog.stdlib.ProcessorFormatter.wrap_for_formatter,
        ],
        context_class=dict,
        logger_factory=structlog.stdlib.LoggerFactory(),
        wrapper_class=structlog.stdlib.BoundLogger,
        cache_logger_on_first_use=True,
    )


# Runs on import so every entry point (e.g. ``uvicorn ecommerce_ops.api.app:app``)
# gets structured logging before any records are emitted.
configure_logger()
