"""Tests for Security — Role Manager, Auth, Audit."""

from datetime import datetime

import pytest

from ecommerce_ops.security.models import (
    DEFAULT_ROLES,
    APIKey,
    Permission,
    Role,
    User,
)
from ecommerce_ops.security.role_manager import (
    RoleManager,
    _hash_api_key,
    _legacy_hash_api_key,
    _verify_api_key_hash,
)

# ── Role Manager Unit Tests ───────────────────────────────


def test_legacy_hash_verified_with_warning_metric():
    from ecommerce_ops.api.metrics import METRIC_LEGACY_API_KEY_USES

    key = "legacy_key_000"
    legacy = _legacy_hash_api_key(key)
    before = METRIC_LEGACY_API_KEY_USES._value.get()
    assert _verify_api_key_hash(key, legacy) is True
    assert _verify_api_key_hash("wrong_key", legacy) is False
    assert METRIC_LEGACY_API_KEY_USES._value.get() > before


def test_legacy_hash_rejected_after_sunset(monkeypatch):
    import ecommerce_ops.security.role_manager as role_manager_module
    from ecommerce_ops.api.metrics import METRIC_LEGACY_API_KEY_REJECTED

    monkeypatch.setattr(
        role_manager_module,
        "LEGACY_HASH_SUNSET_UTC",
        datetime(2020, 1, 1),
    )
    key = "legacy_key_001"
    legacy = _legacy_hash_api_key(key)
    fresh = _hash_api_key(key)
    before = METRIC_LEGACY_API_KEY_REJECTED._value.get()
    assert _verify_api_key_hash(key, legacy) is False
    assert METRIC_LEGACY_API_KEY_REJECTED._value.get() > before
    # PBKDF2 keys are unaffected by the sunset
    assert _verify_api_key_hash(key, fresh) is True


# ── Role Manager Unit Tests ───────────────────────────────


def test_default_roles_exist():
    assert Role.SUPER_ADMIN in DEFAULT_ROLES
    assert Role.ADMIN in DEFAULT_ROLES
    assert Role.OPERATOR in DEFAULT_ROLES
    assert Role.VIEWER in DEFAULT_ROLES
    assert Role.API_ONLY in DEFAULT_ROLES


def test_super_admin_has_all_permissions():
    super_admin = DEFAULT_ROLES[Role.SUPER_ADMIN]
    assert len(super_admin.permissions) == len(Permission)


def test_viewer_has_read_only():
    viewer = DEFAULT_ROLES[Role.VIEWER]
    assert Permission.DASHBOARD_VIEW in viewer.permissions
    assert Permission.AGENTS_VIEW in viewer.permissions
    assert Permission.AGENTS_EXECUTE not in viewer.permissions
    assert Permission.USERS_CREATE not in viewer.permissions


def test_api_only_has_limited_permissions():
    api_only = DEFAULT_ROLES[Role.API_ONLY]
    assert Permission.AGENTS_EXECUTE in api_only.permissions
    assert Permission.DASHBOARD_VIEW not in api_only.permissions


def test_role_definitions_are_system_roles():
    for _role, definition in DEFAULT_ROLES.items():
        assert definition.is_system is True


def test_hash_api_key_is_salted_pbkdf2():
    key = "test_key_123"
    h1 = _hash_api_key(key)
    h2 = _hash_api_key(key)
    assert h1 != h2
    assert h1.startswith("pbkdf2_sha256$")
    assert _verify_api_key_hash(key, h1) is True
    assert _verify_api_key_hash("wrong_key", h1) is False


def test_hash_api_key_different_keys():
    h1 = _hash_api_key("key1")
    h2 = _hash_api_key("key2")
    assert h1 != h2


def test_role_manager_get_role():
    rm = RoleManager()
    role = rm.get_role(Role.ADMIN)
    assert role is not None
    assert role.name == Role.ADMIN


def test_role_manager_list_roles():
    rm = RoleManager()
    roles = rm.list_roles()
    assert len(roles) == 5


def test_role_manager_create_role():
    rm = RoleManager()
    role = rm.create_role(
        name="custom_role",
        display_name="Custom Role",
        description="A custom role",
        permissions={Permission.DASHBOARD_VIEW},
    )
    assert Permission.DASHBOARD_VIEW in role.permissions


def test_role_manager_duplicate_role_raises():
    rm = RoleManager()
    with pytest.raises(ValueError, match="already exists"):
        rm.create_role(
            name="admin",
            display_name="Admin",
            description="Duplicate",
            permissions=set(),
        )


def test_role_manager_delete_system_role_fails():
    rm = RoleManager()
    assert rm.delete_role(Role.ADMIN) is False


def test_role_manager_update_system_role_fails():
    rm = RoleManager()
    assert rm.update_role_permissions(Role.ADMIN, {Permission.DASHBOARD_VIEW}) is False


def test_role_manager_create_custom_role_then_delete():
    rm = RoleManager()
    rm.create_role("temp_role", "Temp", "Temporary", {Permission.DASHBOARD_VIEW})
    assert rm.delete_role("temp_role") is True


# ── Permission Check Tests ────────────────────────────────


def test_check_permission_active_user():
    rm = RoleManager()
    user = User(id="u1", email="test@test.com", role=Role.ADMIN, is_active=True)
    result = rm.check_permission(user, Permission.DASHBOARD_VIEW)
    assert result.allowed is True


def test_check_permission_inactive_user():
    rm = RoleManager()
    user = User(id="u1", email="test@test.com", role=Role.ADMIN, is_active=False)
    result = rm.check_permission(user, Permission.DASHBOARD_VIEW)
    assert result.allowed is False
    assert "inactive" in result.reason.lower()


def test_check_permission_viewer_execute_denied():
    rm = RoleManager()
    user = User(id="u1", email="test@test.com", role=Role.VIEWER)
    result = rm.check_permission(user, Permission.AGENTS_EXECUTE)
    assert result.allowed is False
    assert len(result.missing_permissions) > 0


def test_check_permissions_batch():
    rm = RoleManager()
    user = User(id="u1", email="test@test.com", role=Role.VIEWER)
    result = rm.check_permissions(user, {Permission.DASHBOARD_VIEW, Permission.AGENTS_VIEW})
    assert result.allowed is True


def test_check_permissions_batch_with_missing():
    rm = RoleManager()
    user = User(id="u1", email="test@test.com", role=Role.VIEWER)
    result = rm.check_permissions(user, {Permission.DASHBOARD_VIEW, Permission.USERS_CREATE})
    assert result.allowed is False


def test_get_user_permissions_merges_role_and_user():
    rm = RoleManager()
    user = User(
        id="u1", email="test@test.com", role=Role.VIEWER,
        permissions={Permission.USERS_CREATE},
    )
    perms = rm.get_user_permissions(user)
    assert Permission.DASHBOARD_VIEW in perms
    assert Permission.USERS_CREATE in perms


# ── User Model Tests ──────────────────────────────────────


def test_user_is_admin_super_admin():
    user = User(id="u1", email="t@t.com", role=Role.SUPER_ADMIN)
    assert user.is_admin is True
    assert user.is_super_admin is True


def test_user_is_admin_admin():
    user = User(id="u1", email="t@t.com", role=Role.ADMIN)
    assert user.is_admin is True
    assert user.is_super_admin is False


def test_user_is_not_admin_operator():
    user = User(id="u1", email="t@t.com", role=Role.OPERATOR)
    assert user.is_admin is False


def test_api_key_not_expired():
    key = APIKey(id="k1", key="raw", name="test", user_id="u1", role=Role.ADMIN)
    assert key.is_expired is False


def test_api_key_expired():
    key = APIKey(
        id="k1", key="raw", name="test", user_id="u1", role=Role.ADMIN,
        expires_at=datetime(2020, 1, 1),
    )
    assert key.is_expired is True
