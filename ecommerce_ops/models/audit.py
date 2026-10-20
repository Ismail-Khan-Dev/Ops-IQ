"""
Immutable Audit Log Model
Append-only table for compliance and forensics.
"""
from sqlalchemy import Column, DateTime, Float, String, Text

from ecommerce_ops.models.db import Base
from ecommerce_ops.utils import utc_now


class AuditLog(Base):
    """Append-only audit log. No UPDATE or DELETE operations allowed."""
    __tablename__ = "audit_log"

    id = Column(String, primary_key=True)
    timestamp = Column(DateTime, nullable=False, default=utc_now, index=True)
    actor = Column(String, nullable=False, index=True)
    actor_role = Column(String, nullable=False, default="unknown")
    action = Column(String, nullable=False, index=True)
    resource_type = Column(String, nullable=False, index=True)
    resource_id = Column(String, nullable=False, default="")
    outcome = Column(String, nullable=False, default="success")
    risk_level = Column(String, nullable=False, default="low")
    confidence_score = Column(Float, nullable=False, default=0.0)
    details = Column(Text, nullable=False, default="{}")
    ip_address = Column(String, nullable=False, default="")
    user_agent = Column(String, nullable=False, default="")
    session_id = Column(String, nullable=False, default="")
    request_id = Column(String, nullable=False, default="")

    def __repr__(self):
        return f"<AuditLog {self.id} {self.action} {self.resource_type}/{self.resource_id}>"
