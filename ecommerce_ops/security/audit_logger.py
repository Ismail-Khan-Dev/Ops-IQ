"""
Audit Logger Service
Records all system actions to the immutable audit_log table.
"""
import json
import logging
import uuid
from typing import Any, Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ecommerce_ops.models.audit import AuditLog
from ecommerce_ops.utils import utc_now

logger = logging.getLogger("ecommerce_ops.security.audit")


class AuditLogger:
    """Service for writing immutable audit log entries."""

    def __init__(self):
        self._disabled = False

    def disable(self):
        self._disabled = True

    def enable(self):
        self._disabled = False

    async def log(
        self,
        session: AsyncSession,
        *,
        actor: str,
        actor_role: str = "unknown",
        action: str,
        resource_type: str,
        resource_id: str = "",
        outcome: str = "success",
        risk_level: str = "low",
        confidence_score: float = 0.0,
        details: Optional[dict[str, Any]] = None,
        ip_address: str = "",
        user_agent: str = "",
        session_id: str = "",
        request_id: str = "",
    ) -> str:
        if self._disabled:
            return ""

        log_id = f"audit_{uuid.uuid4().hex[:16]}"

        entry = AuditLog(
            id=log_id,
            timestamp=utc_now(),
            actor=actor,
            actor_role=actor_role,
            action=action,
            resource_type=resource_type,
            resource_id=resource_id,
            outcome=outcome,
            risk_level=risk_level,
            confidence_score=confidence_score,
            details=json.dumps(details or {}),
            ip_address=ip_address,
            user_agent=user_agent,
            session_id=session_id,
            request_id=request_id,
        )

        session.add(entry)
        await session.flush()

        logger.info(
            "AUDIT: %s %s %s/%s by %s (%s) - %s",
            action, resource_type, resource_id, outcome, actor, actor_role, log_id,
        )

        return log_id

    async def query(
        self,
        session: AsyncSession,
        *,
        actor: Optional[str] = None,
        action: Optional[str] = None,
        resource_type: Optional[str] = None,
        outcome: Optional[str] = None,
        limit: int = 100,
        offset: int = 0,
    ) -> list[AuditLog]:
        stmt = select(AuditLog)

        if actor:
            stmt = stmt.where(AuditLog.actor == actor)
        if action:
            stmt = stmt.where(AuditLog.action == action)
        if resource_type:
            stmt = stmt.where(AuditLog.resource_type == resource_type)
        if outcome:
            stmt = stmt.where(AuditLog.outcome == outcome)

        stmt = stmt.order_by(AuditLog.timestamp.desc()).offset(offset).limit(limit)
        result = await session.execute(stmt)
        return list(result.scalars().all())


audit_logger = AuditLogger()
