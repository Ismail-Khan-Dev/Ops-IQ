"""
Audit Logging (PostgreSQL-backed)
Comprehensive audit logging for security events with persistent storage.
"""

import asyncio
import logging
from datetime import datetime, timedelta
from typing import Any, ClassVar, Dict, List, Optional, Set

from pydantic import BaseModel, Field
from sqlalchemy import func, select

from ecommerce_ops.api.metrics import METRIC_SECURITY_AUDIT_DROPPED
from ecommerce_ops.models.db import SecurityAuditLog, async_session_factory
from ecommerce_ops.security.models import SecurityEvent
from ecommerce_ops.utils import utc_now

logger = logging.getLogger("ecommerce_ops.security.audit")


class AuditEntry(BaseModel):
    """Single audit log entry (read model)."""

    id: int
    timestamp: datetime = Field(default_factory=utc_now)
    event_type: str
    action: str
    resource: str
    resource_id: Optional[str] = None
    user_id: Optional[str] = None
    user_email: Optional[str] = None
    api_key_id: Optional[str] = None
    role: Optional[str] = None
    success: bool = True
    ip_address: Optional[str] = None
    user_agent: Optional[str] = None
    details: Dict[str, Any] = Field(default_factory=dict)
    risk_level: str = "low"

    class Config:
        extra = "allow"


class AuditLogger:
    """Comprehensive audit logging service backed by PostgreSQL."""

    _sensitive_fields: ClassVar[Set[str]] = {
        "password",
        "api_key",
        "secret",
        "token",
        "credit_card",
        "ssn",
    }

    # Strong references to background persist tasks so they are not GC'd (RUF006).
    _background_tasks: ClassVar[Set["asyncio.Task"]] = set()

    def log_event(self, event: SecurityEvent) -> AuditEntry:
        """Log a security event to PostgreSQL."""
        risk_level = self._assess_risk_level(event)
        sanitized = self._sanitize_details(event.details)

        entry = AuditEntry(
            id=0,
            event_type=event.event_type,
            action=event.action,
            resource=event.resource,
            resource_id=event.resource_id,
            user_id=event.user_id,
            api_key_id=event.api_key_id,
            success=event.success,
            ip_address=event.ip_address,
            user_agent=event.user_agent,
            details=sanitized,
            risk_level=risk_level,
        )

        log_level = logging.WARNING if not event.success else logging.INFO
        logger.log(
            log_level,
            "Audit: %s %s on %s by %s (%s)",
            entry.action,
            entry.resource,
            entry.resource_id or "N/A",
            entry.user_id or "system",
            "success" if entry.success else "failure",
        )

        # Persist asynchronously (fire-and-forget for non-blocking)
        try:
            loop = asyncio.get_running_loop()
            task = loop.create_task(self._persist_entry(entry))
            task.add_done_callback(self._background_tasks.discard)
            self._background_tasks.add(task)
        except RuntimeError:
            # No event loop running — persist synchronously via helper
            logger.warning("No event loop; audit entry may not persist")

        return entry

    async def _persist_entry(self, entry: AuditEntry):
        """Write audit entry to PostgreSQL."""
        try:
            async with async_session_factory() as session:
                db_entry = SecurityAuditLog(
                    event_type=entry.event_type,
                    action=entry.action,
                    resource=entry.resource,
                    resource_id=entry.resource_id,
                    user_id=entry.user_id,
                    user_email=entry.user_email,
                    api_key_id=entry.api_key_id,
                    role=entry.role,
                    success=entry.success,
                    ip_address=entry.ip_address,
                    user_agent=entry.user_agent,
                    details=entry.details,
                    risk_level=entry.risk_level,
                )
                session.add(db_entry)
                await session.commit()
        except Exception as e:
            logger.error("Failed to persist audit entry: %s", e)
            METRIC_SECURITY_AUDIT_DROPPED.inc()

    # ── Convenience methods ────────────────────────────────

    def log_auth_event(
        self,
        action: str,
        user_id: Optional[str] = None,
        success: bool = True,
        ip_address: Optional[str] = None,
        details: Optional[Dict[str, Any]] = None,
    ) -> AuditEntry:
        return self.log_event(
            SecurityEvent(
                event_type="authentication",
                action=action,
                resource="auth",
                user_id=user_id,
                success=success,
                ip_address=ip_address,
                details=details or {},
            )
        )

    def log_permission_event(
        self,
        action: str,
        user_id: Optional[str] = None,
        resource: str = "unknown",
        success: bool = True,
        details: Optional[Dict[str, Any]] = None,
    ) -> AuditEntry:
        return self.log_event(
            SecurityEvent(
                event_type="authorization",
                action=action,
                resource=resource,
                user_id=user_id,
                success=success,
                details=details or {},
            )
        )

    def log_data_access(
        self,
        action: str,
        resource: str,
        resource_id: Optional[str] = None,
        user_id: Optional[str] = None,
        details: Optional[Dict[str, Any]] = None,
    ) -> AuditEntry:
        return self.log_event(
            SecurityEvent(
                event_type="data_access",
                action=action,
                resource=resource,
                resource_id=resource_id,
                user_id=user_id,
                success=True,
                details=details or {},
            )
        )

    def log_config_change(
        self,
        action: str,
        user_id: Optional[str] = None,
        changes: Optional[Dict[str, Any]] = None,
    ) -> AuditEntry:
        return self.log_event(
            SecurityEvent(
                event_type="config_change",
                action=action,
                resource="config",
                user_id=user_id,
                success=True,
                details={"changes": changes or {}},
            )
        )

    def log_security_violation(
        self,
        action: str,
        resource: str,
        user_id: Optional[str] = None,
        ip_address: Optional[str] = None,
        details: Optional[Dict[str, Any]] = None,
    ) -> AuditEntry:
        return self.log_event(
            SecurityEvent(
                event_type="security_violation",
                action=action,
                resource=resource,
                user_id=user_id,
                success=False,
                ip_address=ip_address,
                details=details or {},
            )
        )

    # ── Query methods (PostgreSQL) ─────────────────────────

    async def get_entries(
        self,
        event_type: Optional[str] = None,
        user_id: Optional[str] = None,
        resource: Optional[str] = None,
        success: Optional[bool] = None,
        risk_level: Optional[str] = None,
        limit: int = 100,
    ) -> List[AuditEntry]:
        async with async_session_factory() as session:
            stmt = select(SecurityAuditLog)
            if event_type:
                stmt = stmt.where(SecurityAuditLog.event_type == event_type)
            if user_id:
                stmt = stmt.where(SecurityAuditLog.user_id == user_id)
            if resource:
                stmt = stmt.where(SecurityAuditLog.resource == resource)
            if success is not None:
                stmt = stmt.where(SecurityAuditLog.success == success)
            if risk_level:
                stmt = stmt.where(SecurityAuditLog.risk_level == risk_level)

            stmt = stmt.order_by(SecurityAuditLog.timestamp.desc()).limit(limit)
            result = await session.execute(stmt)

            return [
                AuditEntry(
                    id=row.id,
                    timestamp=row.timestamp,
                    event_type=row.event_type,
                    action=row.action,
                    resource=row.resource,
                    resource_id=row.resource_id,
                    user_id=row.user_id,
                    user_email=row.user_email,
                    api_key_id=row.api_key_id,
                    role=row.role,
                    success=row.success,
                    ip_address=row.ip_address,
                    user_agent=row.user_agent,
                    details=row.details or {},
                    risk_level=row.risk_level,
                )
                for row in result.scalars().all()
            ]

    async def get_security_summary(self, hours: int = 24) -> Dict[str, Any]:
        """Get security summary for the last N hours from PostgreSQL."""
        cutoff = utc_now() - timedelta(hours=hours)

        async with async_session_factory() as session:
            base = select(SecurityAuditLog).where(SecurityAuditLog.timestamp >= cutoff)

            total_q = await session.execute(select(func.count()).select_from(base.subquery()))
            total = total_q.scalar() or 0

            failures_q = await session.execute(
                select(func.count()).select_from(
                    base.where(not SecurityAuditLog.success).subquery()
                )
            )
            failures = failures_q.scalar() or 0

            violations_q = await session.execute(
                select(func.count()).select_from(
                    base.where(SecurityAuditLog.event_type == "security_violation").subquery()
                )
            )
            violations = violations_q.scalar() or 0

            # Group by type
            type_q = await session.execute(
                select(SecurityAuditLog.event_type, func.count())
                .where(SecurityAuditLog.timestamp >= cutoff)
                .group_by(SecurityAuditLog.event_type)
            )
            by_type = {row[0]: row[1] for row in type_q.all()}

            # Group by risk
            risk_q = await session.execute(
                select(SecurityAuditLog.risk_level, func.count())
                .where(SecurityAuditLog.timestamp >= cutoff)
                .group_by(SecurityAuditLog.risk_level)
            )
            by_risk = {row[0]: row[1] for row in risk_q.all()}

            return {
                "period_hours": hours,
                "total_events": total,
                "successful": total - failures,
                "failures": failures,
                "security_violations": violations,
                "failure_rate": round(failures / total, 3) if total > 0 else 0,
                "events_by_type": by_type,
                "events_by_risk": by_risk,
            }

    # ── Internal helpers ───────────────────────────────────

    def _assess_risk_level(self, event: SecurityEvent) -> str:
        if event.event_type == "security_violation":
            return "critical"
        if not event.success:
            return "high"
        if event.event_type in ("config_change", "authorization"):
            return "medium"
        return "low"

    def _sanitize_details(self, details: Dict[str, Any]) -> Dict[str, Any]:
        sanitized = {}
        for key, value in details.items():
            if any(s in key.lower() for s in self._sensitive_fields):
                sanitized[key] = "***REDACTED***"
            elif isinstance(value, dict):
                sanitized[key] = self._sanitize_details(value)
            else:
                sanitized[key] = value
        return sanitized


# Singleton
audit_logger = AuditLogger()
