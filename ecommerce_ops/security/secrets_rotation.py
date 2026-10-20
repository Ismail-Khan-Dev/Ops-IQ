"""Credential-rotation tracker.

Operationalises the audit finding that ``GOOGLE_API_KEY`` was exposed in a
transcript and that there is no system-level reminder to rotate secrets
on a schedule.  The tracker is intentionally lightweight:

* Secrets are discovered from ``Settings`` at init time (only those that
  are **non-None** are tracked — an unset secret is not "due for rotation").
* Each tracked secret carries a configurable *rotation period* (default 90
  days).  ``check_all()`` compares ``last_rotated_at`` against the period
  and returns an ``overdue`` flag.
* The module does **not** reach out to any provider — it only tracks
  state.  ``mark_rotated(name)`` is the single mutation, intended to be
  called from the credential-rotation API or a migration script.
* A Prometheus gauge (``secret_overdue``) is emitted on every ``check``
  so that alerting can fire on stale credentials.

Usage::

    from ecommerce_ops.security.secrets_rotation import secret_rotation
    report = secret_rotation.check_all()
"""

from __future__ import annotations

import logging
from datetime import timedelta
from enum import StrEnum
from typing import TYPE_CHECKING, Any, Dict, List, Optional

from pydantic import BaseModel

from ecommerce_ops.api.metrics import METRIC_SECRET_OVERDUE, METRIC_SECRET_ROTATED
from ecommerce_ops.security.audit import SecurityEvent, audit_logger
from ecommerce_ops.utils import utc_now

if TYPE_CHECKING:
    from ecommerce_ops.config import Settings

logger = logging.getLogger("ecommerce_ops.security.secrets_rotation")


class RotationStatus(StrEnum):
    ACTIVE = "active"
    OVERDUE = "overdue"
    UNKNOWN = "unknown"


class SecretRotationEntry(BaseModel):
    """Single tracked secret."""

    name: str
    provider: str = ""
    rotation_period_days: int = 90
    last_rotated_at: Optional[str] = None  # ISO-8601 (naive UTC)
    last_checked_at: Optional[str] = None
    status: RotationStatus = RotationStatus.UNKNOWN
    config_key: str = ""  # env-var name in Settings


# Default rotation periods per config-key prefix.  Infrastructure secrets
# (DATABASE_URL, REDIS_URL) get a longer window.
_DEFAULT_PERIODS: Dict[str, int] = {
    "GOOGLE_API_KEY": 90,
    "DEEPSEEK_API_KEY": 90,
    "SHOPIFY_ACCESS_TOKEN": 90,
    "SHOPIFY_CLIENT_SECRET": 90,
    "SHOPIFY_PASSWORD": 90,
    "API_KEY": 90,
    "SLACK_BOT_TOKEN": 90,
    "RESEND_API_KEY": 90,
    "DATABASE_URL": 180,
    "REDIS_URL": 180,
}

_PROVIDER_MAP: Dict[str, str] = {
    "GOOGLE_API_KEY": "Google (Gemini)",
    "DEEPSEEK_API_KEY": "DeepSeek",
    "SHOPIFY_ACCESS_TOKEN": "Shopify OAuth",
    "SHOPIFY_CLIENT_SECRET": "Shopify OAuth",
    "SHOPIFY_PASSWORD": "Shopify (legacy)",
    "API_KEY": "OpsIQ master",
    "SLACK_BOT_TOKEN": "Slack",
    "RESEND_API_KEY": "Resend (email)",
    "DATABASE_URL": "PostgreSQL",
    "REDIS_URL": "Redis",
}


def _discover_secrets(settings: Settings) -> List[SecretRotationEntry]:
    """Build the initial registry from whatever ``Settings`` has set."""
    now_iso = utc_now().isoformat()
    entries: List[SecretRotationEntry] = []

    for key, period in _DEFAULT_PERIODS.items():
        value = getattr(settings, key, None)
        # SecretStr → extract; plain str → use directly; None → skip
        raw: Any = None
        if value is None:
            continue
        raw = value.get_secret_value() if hasattr(value, "get_secret_value") else value
        if not raw:
            continue

        entries.append(
            SecretRotationEntry(
                name=key,
                provider=_PROVIDER_MAP.get(key, key),
                rotation_period_days=period,
                last_rotated_at=now_iso,
                config_key=key,
                status=RotationStatus.ACTIVE,
            )
        )
    return entries


class SecretRotationTracker:
    """Registry + checker for credential rotation health."""

    def __init__(self) -> None:
        self._entries: Dict[str, SecretRotationEntry] = {}
        self._initialized = False

    def _ensure_init(self) -> None:
        if self._initialized:
            return
        try:
            from ecommerce_ops.config import settings

            for entry in _discover_secrets(settings):
                self._entries[entry.name] = entry
        except Exception:
            logger.debug("Could not discover secrets from Settings", exc_info=True)
        self._initialized = True

    # ── Public API ──────────────────────────────────────────

    def check_all(self) -> Dict[str, Any]:
        """Check every tracked secret and return a summary dict."""
        self._ensure_init()
        now = utc_now()
        overdue_count = 0
        entries: List[Dict[str, Any]] = []

        for _name, entry in self._entries.items():
            if entry.last_rotated_at:
                last = entry.last_rotated_at
                try:
                    from datetime import datetime as _dt

                    last_dt = _dt.fromisoformat(last)
                except (ValueError, TypeError):
                    entry.status = RotationStatus.UNKNOWN
                else:
                    cutoff = now - timedelta(days=entry.rotation_period_days)
                    if last_dt < cutoff:
                        entry.status = RotationStatus.OVERDUE
                        overdue_count += 1
                    else:
                        entry.status = RotationStatus.ACTIVE
            else:
                entry.status = RotationStatus.UNKNOWN

            entry.last_checked_at = now.isoformat()
            entries.append(entry.model_dump())

        # Emit Prometheus gauge so alerting can fire.
        METRIC_SECRET_OVERDUE.set(overdue_count)

        return {
            "total_tracked": len(self._entries),
            "overdue_count": overdue_count,
            "secrets": entries,
        }

    def mark_rotated(self, name: str) -> bool:
        """Record that *name* was just rotated.  Returns False if unknown."""
        self._ensure_init()
        entry = self._entries.get(name)
        if entry is None:
            return False

        now_iso = utc_now().isoformat()
        entry.last_rotated_at = now_iso
        entry.status = RotationStatus.ACTIVE
        METRIC_SECRET_ROTATED.labels(secret_name=name).inc()

        audit_logger.log_event(
            SecurityEvent(
                event_type="credential_rotation",
                action="mark_rotated",
                resource="secret",
                resource_id=name,
                user_id="system",
                success=True,
                details={"secret_name": name},
            )
        )
        logger.info("Secret %s marked as rotated", name)
        return True

    def get_entry(self, name: str) -> Optional[SecretRotationEntry]:
        self._ensure_init()
        return self._entries.get(name)

    def list_entries(self) -> List[SecretRotationEntry]:
        self._ensure_init()
        return list(self._entries.values())

    def register(
        self,
        name: str,
        *,
        provider: str = "",
        rotation_period_days: int = 90,
        config_key: str = "",
    ) -> None:
        """Register a secret manually (for tests or non-Settings secrets)."""
        now_iso = utc_now().isoformat()
        self._entries[name] = SecretRotationEntry(
            name=name,
            provider=provider,
            rotation_period_days=rotation_period_days,
            last_rotated_at=now_iso,
            config_key=config_key or name,
            status=RotationStatus.ACTIVE,
        )

    def reset(self) -> None:
        """Drop all entries (for testing)."""
        self._entries.clear()
        self._initialized = False


# Module-level singleton.
secret_rotation = SecretRotationTracker()
