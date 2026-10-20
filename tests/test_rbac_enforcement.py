"""P4-A verification: route-level RBAC enforcement and secret redaction."""

import types

import pytest

from ecommerce_ops.security.auth import require_admin, require_permission
from ecommerce_ops.security.models import Permission, Role, User
from ecommerce_ops.security.secrets_redact import _redact_text


def _make_request(user):
    req = types.SimpleNamespace()
    req.state = types.SimpleNamespace(user=user)
    return req


def _viewer():
    return User(id="v1", email="viewer@x.com", role=Role.VIEWER)


def _super():
    return User(
        id="s1",
        email="super@x.com",
        role=Role.SUPER_ADMIN,
        permissions=set(Permission),
    )


@pytest.mark.asyncio
async def test_viewer_denied_approve():
    with pytest.raises(Exception) as exc:
        await require_permission(Permission.APPROVALS_APPROVE)(_make_request(_viewer()))
    assert exc.value.status_code == 403


@pytest.mark.asyncio
async def test_viewer_denied_reject():
    with pytest.raises(Exception) as exc:
        await require_permission(Permission.APPROVALS_REJECT)(_make_request(_viewer()))
    assert exc.value.status_code == 403


@pytest.mark.asyncio
async def test_viewer_denied_admin():
    with pytest.raises(Exception) as exc:
        await require_admin(_make_request(_viewer()))
    assert exc.value.status_code == 403


@pytest.mark.asyncio
async def test_superadmin_allowed_approve():
    user = await require_permission(Permission.APPROVALS_APPROVE)(_make_request(_super()))
    assert user.role == Role.SUPER_ADMIN


@pytest.mark.asyncio
async def test_viewer_denied_memory_view():
    with pytest.raises(Exception) as exc:
        await require_permission(Permission.MEMORY_VIEW)(_make_request(_viewer()))
    assert exc.value.status_code == 403


@pytest.mark.asyncio
async def test_viewer_denied_audit_view():
    with pytest.raises(Exception) as exc:
        await require_permission(Permission.AUDIT_VIEW)(_make_request(_viewer()))
    assert exc.value.status_code == 403


@pytest.mark.asyncio
async def test_viewer_denied_dashboard_edit():
    with pytest.raises(Exception) as exc:
        await require_permission(Permission.DASHBOARD_EDIT)(_make_request(_viewer()))
    assert exc.value.status_code == 403


@pytest.mark.asyncio
async def test_viewer_allowed_shopify_view():
    user = await require_permission(Permission.SHOPIFY_VIEW)(_make_request(_viewer()))
    assert user.role == Role.VIEWER


@pytest.mark.asyncio
async def test_viewer_allowed_dashboard_view():
    user = await require_permission(Permission.DASHBOARD_VIEW)(_make_request(_viewer()))
    assert user.role == Role.VIEWER


def test_redact_secrets_key_value():
    s = "api_key=sk_dummy_key_1234567890 token=xxxxxx"
    assert "sk_dummy_key_1234567890" not in _redact_text(s)
    assert "xxxxxx" not in _redact_text(s)
    assert "***REDACTED***" in _redact_text(s)


def test_redact_secrets_bearer():
    s = "Authorization: Bearer aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"
    assert "aaaaaaaa" not in _redact_text(s)
    assert "***REDACTED***" in _redact_text(s)


def test_redact_secrets_benign_untouched():
    assert _redact_text("order total is 42 items") == "order total is 42 items"
