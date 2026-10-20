import os

os.environ.setdefault("ENV", "testing")
os.environ.setdefault("API_KEY", "test-key")
os.environ.setdefault("DATABASE_URL", "sqlite+aiosqlite://")
os.environ.setdefault("DEEPSEEK_API_KEY", "sk-test-key")

import json

import pytest
from sqlalchemy import select

from ecommerce_ops.models.audit import AuditLog
from ecommerce_ops.security.audit_logger import AuditLogger
from ecommerce_ops.utils import utc_now


class TestAuditLogModel:
    def test_audit_log_creation(self):
        entry = AuditLog(
            id="audit_abc123",
            timestamp=utc_now(),
            actor="admin@example.com",
            actor_role="admin",
            action="login",
            resource_type="auth",
            resource_id="session-1",
            outcome="success",
            risk_level="low",
            confidence_score=0.95,
            details=json.dumps({"browser": "chrome"}),
            ip_address="127.0.0.1",
            user_agent="Mozilla/5.0",
            session_id="sess-1",
            request_id="req-1",
        )
        assert entry.id == "audit_abc123"
        assert entry.actor == "admin@example.com"
        assert entry.actor_role == "admin"
        assert entry.action == "login"
        assert entry.resource_type == "auth"
        assert entry.resource_id == "session-1"
        assert entry.outcome == "success"
        assert entry.risk_level == "low"
        assert entry.confidence_score == 0.95
        assert entry.ip_address == "127.0.0.1"
        assert entry.user_agent == "Mozilla/5.0"
        assert entry.session_id == "sess-1"
        assert entry.request_id == "req-1"

    @pytest.mark.asyncio
    async def test_audit_log_defaults(self, db_session):
        entry = AuditLog(id="audit_def456", actor="user@test.com", action="read", resource_type="doc")
        db_session.add(entry)
        await db_session.flush()
        row = (await db_session.execute(
            select(AuditLog).where(AuditLog.id == "audit_def456")
        )).scalar_one()
        assert row.outcome == "success"
        assert row.risk_level == "low"
        assert row.confidence_score == 0.0
        assert row.details == "{}"
        assert row.ip_address == ""
        assert row.user_agent == ""
        assert row.session_id == ""
        assert row.request_id == ""
        assert row.resource_id == ""
        assert row.actor_role == "unknown"

    def test_audit_log_repr(self):
        entry = AuditLog(id="audit_xyz", action="write", resource_type="order", resource_id="ord-42")
        assert repr(entry) == "<AuditLog audit_xyz write order/ord-42>"


@pytest.mark.asyncio
class TestAuditLogger:
    async def test_audit_logger_log(self, db_session):
        logger = AuditLogger()
        log_id = await logger.log(
            db_session,
            actor="tester",
            actor_role="operator",
            action="create",
            resource_type="order",
            resource_id="ord-100",
            outcome="success",
            risk_level="medium",
            confidence_score=0.88,
            details={"key": "value"},
            ip_address="10.0.0.1",
            user_agent="test-agent",
            session_id="s1",
            request_id="r1",
        )
        assert log_id.startswith("audit_")
        await db_session.flush()
        rows = await logger.query(db_session, actor="tester")
        assert len(rows) == 1
        assert rows[0].id == log_id
        assert rows[0].action == "create"
        assert rows[0].resource_type == "order"
        assert rows[0].resource_id == "ord-100"

    async def test_audit_logger_log_disabled(self, db_session):
        logger = AuditLogger()
        logger.disable()
        log_id = await logger.log(
            db_session,
            actor="tester",
            action="delete",
            resource_type="item",
        )
        assert log_id == ""
        rows = await logger.query(db_session, actor="tester")
        assert len(rows) == 0

    async def test_audit_logger_query_filters(self, db_session):
        logger = AuditLogger()
        await logger.log(db_session, actor="alice", action="login", resource_type="auth")
        await logger.log(db_session, actor="bob", action="logout", resource_type="auth")
        await logger.log(db_session, actor="alice", action="read", resource_type="doc")
        await db_session.flush()

        alice_entries = await logger.query(db_session, actor="alice")
        assert len(alice_entries) == 2

        login_entries = await logger.query(db_session, action="login")
        assert len(login_entries) == 1
        assert login_entries[0].actor == "alice"

        auth_entries = await logger.query(db_session, resource_type="auth")
        assert len(auth_entries) == 2

    async def test_audit_logger_query_empty(self, db_session):
        logger = AuditLogger()
        rows = await logger.query(db_session, actor="nonexistent")
        assert rows == []
