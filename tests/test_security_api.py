"""Regression tests for /api/security management routes.

These routes were previously unexercised by the test suite, which is how the
`await audit_logger.log_event(...)` (awaited sync method + keyword-args to a
`SecurityEvent`-taking call) bug survived. Each test drives a route end-to-end
so every audit call site in `ecommerce_ops/api/security.py` is exercised.
"""
import uuid

import pytest
import pytest_asyncio
from sqlalchemy.pool import StaticPool

AUTH = {"Authorization": "Bearer opsiq-dev-key-2024"}


@pytest_asyncio.fixture
async def security_db(monkeypatch):
    """Fresh SQLite DB wired into role_manager + audit modules for one test.

    Uses StaticPool so the single in-memory connection keeps its tables; the
    global app engine otherwise spawns per-connection empty in-memory DBs.
    The operator principal is intentionally NOT seeded here so that the
    API-key flow exercises the operator auto-provisioning path.
    """
    from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

    from ecommerce_ops.models.db import Base

    engine = create_async_engine(
        "sqlite+aiosqlite://",
        poolclass=StaticPool,
        connect_args={"timeout": 15},
    )
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    factory = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)

    monkeypatch.setattr("ecommerce_ops.security.role_manager.async_session_factory", factory)
    monkeypatch.setattr("ecommerce_ops.security.audit.async_session_factory", factory)

    yield

    await engine.dispose()


@pytest.mark.asyncio
async def test_user_lifecycle_audits(security_db, http_client):
    """POST/GET/PATCH/DELETE /security/users — covers create/update/delete audit."""
    email = f"audit-user-{uuid.uuid4()}@example.com"

    created = await http_client.post(
        "/security/users",
        json={"email": email, "name": "Audit User", "role": "viewer"},
        headers=AUTH,
    )
    assert created.status_code == 200, created.text
    user_id = created.json()["id"]
    assert created.json()["role"] == "viewer"

    listed = await http_client.get("/security/users", headers=AUTH)
    assert listed.status_code == 200
    assert user_id in [u["id"] for u in listed.json()["users"]]

    fetched = await http_client.get(f"/security/users/{user_id}", headers=AUTH)
    assert fetched.status_code == 200
    assert fetched.json()["email"] == email

    updated = await http_client.patch(
        f"/security/users/{user_id}",
        json={"name": "Renamed Audit User", "role": "admin"},
        headers=AUTH,
    )
    assert updated.status_code == 200, updated.text
    assert updated.json()["updated"] is True

    after_update = await http_client.get(f"/security/users/{user_id}", headers=AUTH)
    assert after_update.json()["role"] == "admin"

    deleted = await http_client.delete(f"/security/users/{user_id}", headers=AUTH)
    assert deleted.status_code == 200, deleted.text
    assert deleted.json()["deleted"] is True

    gone = await http_client.get(f"/security/users/{user_id}", headers=AUTH)
    assert gone.status_code == 404


@pytest.mark.asyncio
async def test_api_key_lifecycle_audits(security_db, http_client):
    """POST/GET/rotate/DELETE /security/api-keys — covers create/rotate/revoke audit."""
    created = await http_client.post(
        "/security/api-keys",
        json={"name": f"audit-key-{uuid.uuid4()}", "role": "viewer", "expires_days": 30},
        headers=AUTH,
    )
    # operator ownership must be auto-provisioned (no 500, key has a valid owner)
    assert created.status_code == 200, created.text
    body = created.json()
    assert body["key"].startswith("eops_")
    first_key_id = body["id"]

    # The issued key must be fully usable: validates and resolves to the operator
    from ecommerce_ops.security.role_manager import role_manager

    validated = await role_manager.validate_api_key(body["key"])
    assert validated is not None
    owner = await role_manager.get_user(validated.user_id)
    assert owner is not None and owner.is_super_admin

    listed = await http_client.get("/security/api-keys", headers=AUTH)
    assert listed.status_code == 200
    assert first_key_id in [k["id"] for k in listed.json()["api_keys"]]

    rotated = await http_client.post(
        "/security/api-keys/rotate",
        json={"key_id": first_key_id},
        headers=AUTH,
    )
    assert rotated.status_code == 200, rotated.text
    second_key_id = rotated.json()["id"]
    assert rotated.json()["key"].startswith("eops_")
    assert rotated.json()["previous_key_revoked"] is True

    revoked = await http_client.delete(f"/security/api-keys/{second_key_id}", headers=AUTH)
    assert revoked.status_code == 200, revoked.text
    assert revoked.json()["revoked"] is True


@pytest.mark.asyncio
async def test_duplicate_user_email_rejected(security_db, http_client):
    email = f"dup-user-{uuid.uuid4()}@example.com"
    first = await http_client.post(
        "/security/users",
        json={"email": email, "name": "Dup", "role": "viewer"},
        headers=AUTH,
    )
    assert first.status_code == 200
    user_id = first.json()["id"]

    second = await http_client.post(
        "/security/users",
        json={"email": email, "name": "Dup 2", "role": "viewer"},
        headers=AUTH,
    )
    assert second.status_code == 400

    await http_client.delete(f"/security/users/{user_id}", headers=AUTH)


@pytest.mark.asyncio
async def test_permission_check_endpoint(security_db, http_client):
    resp = await http_client.post(
        "/security/check-permissions",
        json={"permissions": ["dashboard:view"]},
        headers=AUTH,
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["allowed"] is True
