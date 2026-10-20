"""Global secret-redaction for log records.

Registered as a structlog processor (see ``ecommerce_ops.telemetry.logger``)
so that *every* log line — including plain ``logging`` calls routed through
``ProcessorFormatter`` — has credentials, tokens, and long opaque secrets
stripped before it leaves the process. This is defense-in-depth: even a
developer who accidentally logs ``request.headers`` or an API key will never
emit the real secret to stdout/file.
"""

import logging
import re
from typing import Any

REDACTED = "***REDACTED***"

# key = value / key: value forms for well-known secret field names.
_SECRET_ASSIGN_RE = re.compile(
    r"(?i)("
    r"(?:api[_-]?key|access[_-]?token|refresh[_-]?token|client[_-]?secret|"
    r"secret|password|passwd|pwd|token|authorization|x-api-key)"
    r"\s*[:=]\s*[\"']?"
    r")([A-Za-z0-9_\-\.]{6,})"
)

# "Bearer <token>" / "bearer <token>" forms.
_BEARER_RE = re.compile(r"(?i)(Bearer\s+)([A-Za-z0-9_\-\.]{6,})")

# Long opaque tokens / JWTs / hashes that are very unlikely to be legitimate
# log content (>= 40 contiguous alphanumerics).
_LONG_TOKEN_RE = re.compile(r"\b[A-Za-z0-9_\-]{40,}\b")

# Field names whose values are always treated as secrets.
_SECRET_KEY_NAME_RE = re.compile(
    r"(?i)(api[_-]?key|access[_-]?token|refresh[_-]?token|client[_-]?secret|"
    r"secret|password|passwd|pwd|token|authorization|x-api-key)"
)


def _redact_text(value: str) -> str:
    # Bearer form first, so "Authorization: Bearer <token>" redacts the token
    # before the key=value rule can mistake "Bearer" for the value.
    value = _BEARER_RE.sub(lambda m: m.group(1) + REDACTED, value)
    value = _SECRET_ASSIGN_RE.sub(lambda m: m.group(1) + REDACTED, value)
    value = _LONG_TOKEN_RE.sub(REDACTED, value)
    return value


def redact_secrets(logger: Any, method_name: str, event_dict: dict) -> dict:
    """structlog processor that redacts secrets from the event and kwargs."""
    event = event_dict.get("event")
    if isinstance(event, str):
        event_dict["event"] = _redact_text(event)

    for key, val in list(event_dict.items()):
        if key in ("event", "logger", "level", "timestamp"):
            continue
        if isinstance(key, str) and _SECRET_KEY_NAME_RE.search(key):
            event_dict[key] = REDACTED
        elif isinstance(val, str):
            redacted = _redact_text(val)
            if redacted != val:
                event_dict[key] = redacted
        elif isinstance(val, (list, tuple)):
            new_vals = []
            changed = False
            for item in val:
                if isinstance(item, str):
                    r = _redact_text(item)
                    if r != item:
                        changed = True
                    new_vals.append(r)
                else:
                    new_vals.append(item)
            if changed:
                event_dict[key] = type(val)(new_vals)  # type: ignore[call-arg]
    return event_dict


# Register on the root logger so even handlers set up elsewhere inherit it.
class SecretRedactingFilter(logging.Filter):
    """stdlib logging filter mirror of :func:`redact_secrets`."""

    def filter(self, record: logging.LogRecord) -> bool:
        if isinstance(getattr(record, "msg", None), str):
            record.msg = _redact_text(record.msg)
        for attr in ("args",):
            val = getattr(record, attr, None)
            if isinstance(val, dict):
                for k, v in list(val.items()):
                    if isinstance(k, str) and _SECRET_KEY_NAME_RE.search(k):
                        val[k] = REDACTED
                    elif isinstance(v, str) and _redact_text(v) != v:
                        val[k] = _redact_text(v)
        return True
