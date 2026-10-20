"""Structured-logging tests.

Regression guards for the audit finding (H13): structlog is configured but the
codebase logs via stdlib ``logging.getLogger`` — so the stdlib root handler must
actually route through a structlog ProcessorFormatter, and in production it must
emit parseable JSON.
"""

import io
import json
import logging
from types import SimpleNamespace

import structlog

import ecommerce_ops.telemetry.logger as logger_mod


def test_root_handler_uses_structlog_processor_formatter():
    logger_mod.configure_logger()
    root = logging.getLogger()
    assert len(root.handlers) == 1
    assert isinstance(root.handlers[0].formatter, structlog.stdlib.ProcessorFormatter)


def test_production_stdlib_logs_emit_structured_json(monkeypatch):
    monkeypatch.setattr(
        logger_mod,
        "settings",
        SimpleNamespace(ENV="production", DEBUG=False),
    )
    logger_mod.configure_logger()

    root = logging.getLogger()
    handler = root.handlers[0]
    original_stream = handler.stream
    stream = io.StringIO()
    handler.stream = stream
    try:
        logging.getLogger("opsiq.metrics").warning("shop %s stock low", "acme")
    finally:
        handler.stream = original_stream

    lines = [line for line in stream.getvalue().strip().splitlines() if line.strip()]
    assert lines, "expected at least one log line"

    record = json.loads(lines[-1])
    assert record["event"] == "shop acme stock low"
    assert record["level"] == "warning"
    assert record["logger"] == "opsiq.metrics"
