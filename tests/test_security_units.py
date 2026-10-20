import os
import time
from datetime import timedelta
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from ecommerce_ops.utils import utc_now

os.environ["ENV"] = "testing"
os.environ["DATABASE_URL"] = "sqlite+aiosqlite://"
os.environ["API_KEY"] = "test-key"
os.environ["DEEPSEEK_API_KEY"] = "sk-test-key"


class TestSecurityModels:
    def test_permission_enum_count(self):
        from ecommerce_ops.security.models import Permission

        assert len(Permission) > 20

    def test_permission_values_are_strings(self):
        from ecommerce_ops.security.models import Permission

        for p in Permission:
            assert isinstance(p.value, str)
            assert ":" in p.value

    def test_role_enum_values(self):
        from ecommerce_ops.security.models import Role

        assert Role.SUPER_ADMIN.value == "super_admin"
        assert Role.ADMIN.value == "admin"
        assert Role.OPERATOR.value == "operator"
        assert Role.VIEWER.value == "viewer"
        assert Role.API_ONLY.value == "api_only"

    def test_user_is_admin_super_admin(self):
        from ecommerce_ops.security.models import Role, User

        user = User(id="1", email="a@b.com", role=Role.SUPER_ADMIN)
        assert user.is_admin is True
        assert user.is_super_admin is True

    def test_user_is_admin_admin(self):
        from ecommerce_ops.security.models import Role, User

        user = User(id="1", email="a@b.com", role=Role.ADMIN)
        assert user.is_admin is True
        assert user.is_super_admin is False

    def test_user_is_admin_operator(self):
        from ecommerce_ops.security.models import Role, User

        user = User(id="1", email="a@b.com", role=Role.OPERATOR)
        assert user.is_admin is False

    def test_user_is_admin_viewer(self):
        from ecommerce_ops.security.models import Role, User

        user = User(id="1", email="a@b.com", role=Role.VIEWER)
        assert user.is_admin is False

    def test_api_key_is_expired_with_past_date(self):
        from ecommerce_ops.security.models import APIKey, Role

        key = APIKey(
            id="1",
            key="raw",
            name="test",
            user_id="u1",
            role=Role.VIEWER,
            expires_at=utc_now() - timedelta(days=1),
        )
        assert key.is_expired is True

    def test_api_key_is_expired_with_future_date(self):
        from ecommerce_ops.security.models import APIKey, Role

        key = APIKey(
            id="1",
            key="raw",
            name="test",
            user_id="u1",
            role=Role.VIEWER,
            expires_at=utc_now() + timedelta(days=1),
        )
        assert key.is_expired is False

    def test_api_key_is_expired_no_expiry(self):
        from ecommerce_ops.security.models import APIKey, Role

        key = APIKey(
            id="1",
            key="raw",
            name="test",
            user_id="u1",
            role=Role.VIEWER,
            expires_at=None,
        )
        assert key.is_expired is False

    def test_role_definition_model(self):
        from ecommerce_ops.security.models import Permission, Role, RoleDefinition

        rd = RoleDefinition(
            name=Role.VIEWER,
            display_name="Viewer",
            description="Read-only",
            permissions={Permission.DASHBOARD_VIEW},
        )
        assert rd.is_system is True
        assert Permission.DASHBOARD_VIEW in rd.permissions

    def test_permission_check_model(self):
        from ecommerce_ops.security.models import PermissionCheck

        pc = PermissionCheck(allowed=True, role=None)
        assert pc.allowed is True
        assert pc.missing_permissions == []

    def test_access_context_model(self):
        from ecommerce_ops.security.models import AccessContext

        ctx = AccessContext(user_id="u1", role=None, permissions=set())
        assert ctx.user_id == "u1"
        assert ctx.ip_address is None

    def test_security_event_model(self):
        from ecommerce_ops.security.models import SecurityEvent

        event = SecurityEvent(
            event_type="auth",
            action="login",
            resource="user",
            success=True,
        )
        assert event.success is True
        assert event.details == {}

    def test_default_roles_cover_all_roles(self):
        from ecommerce_ops.security.models import DEFAULT_ROLES, Role

        assert Role.SUPER_ADMIN in DEFAULT_ROLES
        assert Role.ADMIN in DEFAULT_ROLES
        assert Role.OPERATOR in DEFAULT_ROLES
        assert Role.VIEWER in DEFAULT_ROLES
        assert Role.API_ONLY in DEFAULT_ROLES

    def test_default_roles_have_permissions(self):
        from ecommerce_ops.security.models import DEFAULT_ROLES, Permission

        for _role, defn in DEFAULT_ROLES.items():
            assert len(defn.permissions) > 0
            assert all(isinstance(p, Permission) for p in defn.permissions)


class TestRoleManager:
    def test_get_role_by_enum(self):
        from ecommerce_ops.security.models import Role
        from ecommerce_ops.security.role_manager import RoleManager

        rm = RoleManager()
        defn = rm.get_role(Role.ADMIN)
        assert defn is not None
        assert defn.name == Role.ADMIN

    def test_get_role_by_string(self):
        from ecommerce_ops.security.role_manager import RoleManager

        rm = RoleManager()
        defn = rm.get_role("admin")
        assert defn is not None

    def test_get_role_not_found(self):
        from ecommerce_ops.security.role_manager import RoleManager

        rm = RoleManager()
        assert rm.get_role("nonexistent") is None

    def test_list_roles(self):
        from ecommerce_ops.security.role_manager import RoleManager

        rm = RoleManager()
        roles = rm.list_roles()
        assert len(roles) == 5

    def test_create_role(self):
        from ecommerce_ops.security.models import Permission
        from ecommerce_ops.security.role_manager import RoleManager

        rm = RoleManager()
        defn = rm.create_role(
            name="custom_role",
            display_name="Custom",
            description="Custom role",
            permissions={Permission.DASHBOARD_VIEW},
        )
        assert defn.display_name == "Custom"
        assert Permission.DASHBOARD_VIEW in defn.permissions

    def test_create_role_duplicate_raises(self):
        from ecommerce_ops.security.models import Permission
        from ecommerce_ops.security.role_manager import RoleManager

        rm = RoleManager()
        rm.create_role("dup_role", "Dup", "Dup role", {Permission.DASHBOARD_VIEW})
        with pytest.raises(ValueError, match="already exists"):
            rm.create_role("dup_role", "Dup2", "Dup2", {Permission.DASHBOARD_VIEW})

    def test_update_role_permissions(self):
        from ecommerce_ops.security.models import Permission, Role, RoleDefinition
        from ecommerce_ops.security.role_manager import RoleManager

        rm = RoleManager()
        rm._roles["custom_role"] = RoleDefinition(
            name=Role.VIEWER,
            display_name="Custom",
            description="Custom role",
            permissions=set(),
            is_system=False,
            created_at=utc_now(),
            updated_at=utc_now(),
        )
        result = rm.update_role_permissions("custom_role", {Permission.AGENTS_VIEW})
        assert result is True

    def test_update_role_permissions_not_found(self):
        from ecommerce_ops.security.models import Permission
        from ecommerce_ops.security.role_manager import RoleManager

        rm = RoleManager()
        result = rm.update_role_permissions("nonexistent", {Permission.AGENTS_VIEW})
        assert result is False

    def test_update_system_role_denied(self):
        from ecommerce_ops.security.models import Permission, Role
        from ecommerce_ops.security.role_manager import RoleManager

        rm = RoleManager()
        result = rm.update_role_permissions(Role.ADMIN, {Permission.DASHBOARD_VIEW})
        assert result is False

    def test_delete_role(self):
        from ecommerce_ops.security.models import Permission
        from ecommerce_ops.security.role_manager import RoleManager

        rm = RoleManager()
        rm.create_role("to_delete", "Delete", "To delete", {Permission.DASHBOARD_VIEW})
        assert rm.delete_role("to_delete") is True

    def test_delete_role_not_found(self):
        from ecommerce_ops.security.role_manager import RoleManager

        rm = RoleManager()
        assert rm.delete_role("nonexistent") is False

    def test_delete_system_role_denied(self):
        from ecommerce_ops.security.models import Role
        from ecommerce_ops.security.role_manager import RoleManager

        rm = RoleManager()
        assert rm.delete_role(Role.ADMIN) is False

    def test_check_permission_active_user_with_role_perm(self):
        from ecommerce_ops.security.models import Permission, Role, User
        from ecommerce_ops.security.role_manager import RoleManager

        rm = RoleManager()
        user = User(id="u1", email="a@b.com", role=Role.VIEWER, is_active=True)
        result = rm.check_permission(user, Permission.DASHBOARD_VIEW)
        assert result.allowed is True

    def test_check_permission_inactive_user(self):
        from ecommerce_ops.security.models import Permission, Role, User
        from ecommerce_ops.security.role_manager import RoleManager

        rm = RoleManager()
        user = User(id="u1", email="a@b.com", role=Role.VIEWER, is_active=False)
        result = rm.check_permission(user, Permission.DASHBOARD_VIEW)
        assert result.allowed is False
        assert "inactive" in result.reason

    def test_check_permission_denied(self):
        from ecommerce_ops.security.models import Permission, Role, User
        from ecommerce_ops.security.role_manager import RoleManager

        rm = RoleManager()
        user = User(id="u1", email="a@b.com", role=Role.VIEWER, is_active=True)
        result = rm.check_permission(user, Permission.AUDIT_EXPORT)
        assert result.allowed is False

    def test_check_permission_user_level_override(self):
        from ecommerce_ops.security.models import Permission, Role, User
        from ecommerce_ops.security.role_manager import RoleManager

        rm = RoleManager()
        user = User(
            id="u1",
            email="a@b.com",
            role=Role.VIEWER,
            is_active=True,
            permissions={Permission.AUDIT_EXPORT},
        )
        result = rm.check_permission(user, Permission.AUDIT_EXPORT)
        assert result.allowed is True

    def test_check_permissions_multiple(self):
        from ecommerce_ops.security.models import Permission, Role, User
        from ecommerce_ops.security.role_manager import RoleManager

        rm = RoleManager()
        user = User(id="u1", email="a@b.com", role=Role.VIEWER, is_active=True)
        result = rm.check_permissions(user, {Permission.DASHBOARD_VIEW, Permission.APPROVALS_VIEW})
        assert result.allowed is True

    def test_check_permissions_one_missing(self):
        from ecommerce_ops.security.models import Permission, Role, User
        from ecommerce_ops.security.role_manager import RoleManager

        rm = RoleManager()
        user = User(id="u1", email="a@b.com", role=Role.VIEWER, is_active=True)
        result = rm.check_permissions(user, {Permission.DASHBOARD_VIEW, Permission.AUDIT_EXPORT})
        assert result.allowed is False

    def test_get_user_permissions(self):
        from ecommerce_ops.security.models import Permission, Role, User
        from ecommerce_ops.security.role_manager import RoleManager

        rm = RoleManager()
        user = User(id="u1", email="a@b.com", role=Role.VIEWER, is_active=True)
        perms = rm.get_user_permissions(user)
        assert Permission.DASHBOARD_VIEW in perms
        assert Permission.AUDIT_EXPORT not in perms

    def test_hash_api_key(self):
        from ecommerce_ops.security.role_manager import _hash_api_key, _verify_api_key_hash

        result = _hash_api_key("test_key")
        assert result.startswith("pbkdf2_sha256$")
        assert _verify_api_key_hash("test_key", result) is True
        assert _verify_api_key_hash("wrong_key", result) is False

    @pytest.mark.asyncio
    async def test_rotate_api_key_revokes_old_and_issues_new(self):
        from ecommerce_ops.security.models import Role
        from ecommerce_ops.security.role_manager import RoleManager

        rm = RoleManager()
        user = await rm.create_user(email="rotate@example.com", role=Role.ADMIN)
        original = await rm.create_api_key(user_id=user.id, name="rotate-me", role=Role.ADMIN)
        rotated = await rm.rotate_api_key(original.id)
        assert rotated is not None
        assert rotated.id != original.id
        assert rotated.key != original.key

        keys = await rm.list_api_keys(user_id=user.id)
        active = [k for k in keys if k.is_active]
        assert len(active) == 1
        assert active[0].id == rotated.id

    @pytest.mark.asyncio
    async def test_rotate_api_key_missing_returns_none(self):
        from ecommerce_ops.security.role_manager import RoleManager

        rm = RoleManager()
        assert await rm.rotate_api_key("does-not-exist") is None

    @pytest.mark.asyncio
    async def test_rotate_api_key_already_inactive_returns_none(self):
        from ecommerce_ops.security.models import Role
        from ecommerce_ops.security.role_manager import RoleManager

        rm = RoleManager()
        user = await rm.create_user(email="rotate2@example.com", role=Role.VIEWER)
        key = await rm.create_api_key(user_id=user.id, name="already-inactive", role=Role.VIEWER)
        assert await rm.revoke_api_key(key.id) is True
        assert await rm.rotate_api_key(key.id) is None


class TestAuth:
    def test_middleware_public_paths(self):
        from ecommerce_ops.security.auth import AuthenticationMiddleware

        mw = AuthenticationMiddleware(app=MagicMock())
        assert mw._is_public_path("/") is True
        assert mw._is_public_path("/health") is True

    def test_middleware_docs_and_metrics_public_only_in_dev(self):
        from ecommerce_ops.config import Environment
        from ecommerce_ops.config import settings as app_settings
        from ecommerce_ops.security.auth import AuthenticationMiddleware

        mw = AuthenticationMiddleware(app=MagicMock())
        with patch.object(app_settings, "ENV", Environment.PRODUCTION):
            # Docs/schema/metrics must never be anonymous in production.
            assert mw._is_public_path("/docs") is False
            assert mw._is_public_path("/openapi.json") is False
            assert mw._is_public_path("/redoc") is False
            assert mw._is_public_path("/metrics") is False
        with patch.object(app_settings, "ENV", Environment.DEVELOPMENT):
            assert mw._is_public_path("/docs") is True
            assert mw._is_public_path("/openapi.json") is True
            assert mw._is_public_path("/redoc") is True
            assert mw._is_public_path("/metrics") is True

    def test_middleware_static_paths(self):
        from ecommerce_ops.security.auth import AuthenticationMiddleware

        mw = AuthenticationMiddleware(app=MagicMock())
        assert mw._is_public_path("/static/app.js") is True
        assert mw._is_public_path("/page.css") is True
        assert mw._is_public_path("/favicon.ico") is True

    def test_middleware_private_path(self):
        from ecommerce_ops.security.auth import AuthenticationMiddleware

        mw = AuthenticationMiddleware(app=MagicMock())
        assert mw._is_public_path("/api/orders") is False
        assert mw._is_public_path("/admin") is False

    @pytest.mark.asyncio
    async def test_middleware_dispatch_public_path(self):
        from ecommerce_ops.security.auth import AuthenticationMiddleware

        mw = AuthenticationMiddleware(app=MagicMock())
        mock_request = MagicMock()
        mock_request.url.path = "/health"
        mock_request.method = "GET"
        mock_request.state = MagicMock()
        mock_response = MagicMock()
        mock_response.status_code = 200
        call_next = AsyncMock(return_value=mock_response)
        result = await mw.dispatch(mock_request, call_next)
        assert result == mock_response

    @pytest.mark.asyncio
    async def test_middleware_dispatch_invalid_api_key(self):
        from ecommerce_ops.security.auth import AuthenticationMiddleware

        mw = AuthenticationMiddleware(app=MagicMock())
        mock_request = MagicMock()
        mock_request.url.path = "/api/data"
        mock_request.method = "GET"
        mock_request.headers = {"X-API-Key": "bad-key"}
        mock_request.state = MagicMock()
        mock_request.client = MagicMock()
        mock_request.client.host = "127.0.0.1"

        with patch("ecommerce_ops.security.auth.role_manager") as mock_rm:
            mock_rm.validate_api_key = AsyncMock(return_value=None)
            call_next = AsyncMock()
            result = await mw.dispatch(mock_request, call_next)
            assert result.status_code == 401

    @pytest.mark.asyncio
    async def test_middleware_dispatch_no_credentials(self):
        from ecommerce_ops.security.auth import AuthenticationMiddleware

        mw = AuthenticationMiddleware(app=MagicMock())
        mock_request = MagicMock()
        mock_request.url.path = "/api/data"
        mock_request.method = "GET"
        mock_request.headers = {}
        mock_request.state = MagicMock()
        mock_request.client = MagicMock()
        mock_request.client.host = "127.0.0.1"

        mock_response = MagicMock()
        mock_response.status_code = 200
        call_next = AsyncMock(return_value=mock_response)
        result = await mw.dispatch(mock_request, call_next)
        assert result.status_code == 401
        call_next.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_middleware_dispatch_valid_api_key(self):
        from ecommerce_ops.security.auth import AuthenticationMiddleware

        mw = AuthenticationMiddleware(app=MagicMock())
        mock_request = MagicMock()
        mock_request.url.path = "/api/data"
        mock_request.method = "GET"
        mock_request.headers = {"X-API-Key": "valid-key"}
        mock_request.state = MagicMock()
        mock_request.client = MagicMock()
        mock_request.client.host = "127.0.0.1"

        mock_api_key = MagicMock()
        mock_api_key.user_id = "u1"
        mock_api_key.id = "key-1"
        mock_user = MagicMock()
        mock_user.id = "u1"

        with patch("ecommerce_ops.security.auth.role_manager") as mock_rm:
            mock_rm.validate_api_key = AsyncMock(return_value=mock_api_key)
            mock_rm.get_user = AsyncMock(return_value=mock_user)
            mock_response = MagicMock()
            mock_response.status_code = 200
            call_next = AsyncMock(return_value=mock_response)
            result = await mw.dispatch(mock_request, call_next)
            assert result == mock_response

    @pytest.mark.asyncio
    async def test_middleware_dispatch_bearer_token(self):
        from ecommerce_ops.security.auth import AuthenticationMiddleware

        mw = AuthenticationMiddleware(app=MagicMock())
        mock_request = MagicMock()
        mock_request.url.path = "/api/data"
        mock_request.method = "GET"
        mock_request.headers = {"Authorization": "Bearer some-token"}
        mock_request.state = MagicMock()
        mock_request.client = MagicMock()
        mock_request.client.host = "127.0.0.1"

        with patch("ecommerce_ops.security.auth.role_manager") as mock_rm:
            mock_api_key = MagicMock()
            mock_api_key.user_id = "u1"
            mock_api_key.id = "k1"
            mock_user = MagicMock()
            mock_user.id = "u1"
            mock_rm.validate_api_key = AsyncMock(return_value=mock_api_key)
            mock_rm.get_user = AsyncMock(return_value=mock_user)
            mock_response = MagicMock()
            mock_response.status_code = 200
            call_next = AsyncMock(return_value=mock_response)
            result = await mw.dispatch(mock_request, call_next)
            assert result == mock_response

    @pytest.mark.asyncio
    async def test_middleware_dispatch_api_key_exception(self):

        from ecommerce_ops.security.auth import AuthenticationMiddleware

        mw = AuthenticationMiddleware(app=MagicMock())
        mock_request = MagicMock()
        mock_request.url.path = "/api/data"
        mock_request.method = "GET"
        mock_request.headers = {"X-API-Key": "valid-key"}
        mock_request.state = MagicMock()
        mock_request.client = MagicMock()
        mock_request.client.host = "127.0.0.1"

        with patch("ecommerce_ops.security.auth.role_manager") as mock_rm:
            mock_rm.validate_api_key = AsyncMock(side_effect=Exception("DB error"))
            mock_response = MagicMock()
            mock_response.status_code = 200
            call_next = AsyncMock(return_value=mock_response)
            result = await mw.dispatch(mock_request, call_next)
            assert result.status_code == 503

    @pytest.mark.asyncio
    async def test_require_auth_no_credentials(self):
        from fastapi import HTTPException

        from ecommerce_ops.security.auth import require_auth

        mock_request = MagicMock()
        mock_request.state.user = None
        with pytest.raises(HTTPException) as exc_info:
            await require_auth(mock_request)
        assert exc_info.value.status_code == 401

    @pytest.mark.asyncio
    async def test_require_auth_valid(self):
        from ecommerce_ops.security.auth import require_auth
        from ecommerce_ops.security.models import Role, User

        mock_user = User(id="u1", email="a@b.com", role=Role.VIEWER)
        mock_request = MagicMock()
        mock_request.state.user = mock_user
        result = await require_auth(mock_request)
        assert result == mock_user

    @pytest.mark.asyncio
    async def test_require_auth_invalid_key(self):
        from fastapi import HTTPException

        from ecommerce_ops.security.auth import require_auth

        mock_request = MagicMock()
        mock_request.state.user = None
        with pytest.raises(HTTPException) as exc_info:
            await require_auth(mock_request)
        assert exc_info.value.status_code == 401

    @pytest.mark.asyncio
    async def test_require_auth_inactive_user(self):
        from fastapi import HTTPException

        from ecommerce_ops.security.auth import require_auth
        from ecommerce_ops.security.models import Role, User

        mock_user = User(id="u1", email="a@b.com", role=Role.VIEWER, is_active=False)
        mock_request = MagicMock()
        mock_request.state.user = mock_user
        with pytest.raises(HTTPException) as exc_info:
            await require_auth(mock_request)
        assert exc_info.value.status_code == 401

    def test_require_permission_factory(self):
        from ecommerce_ops.security.auth import require_permission
        from ecommerce_ops.security.models import Permission

        dep = require_permission(Permission.DASHBOARD_VIEW)
        assert callable(dep)

    def test_require_role_factory(self):
        from ecommerce_ops.security.auth import require_role
        from ecommerce_ops.security.models import Role

        dep = require_role(Role.ADMIN)
        assert callable(dep)

    @pytest.mark.asyncio
    async def test_require_admin_no_user(self):
        from fastapi import HTTPException

        from ecommerce_ops.security.auth import require_admin

        mock_request = MagicMock()
        mock_request.state.user = None
        with pytest.raises(HTTPException) as exc_info:
            await require_admin(mock_request)
        assert exc_info.value.status_code == 401

    @pytest.mark.asyncio
    async def test_require_admin_not_admin(self):
        from fastapi import HTTPException

        from ecommerce_ops.security.auth import require_admin
        from ecommerce_ops.security.models import Role, User

        user = User(id="u1", email="a@b.com", role=Role.VIEWER)
        mock_request = MagicMock()
        mock_request.state.user = user
        with pytest.raises(HTTPException) as exc_info:
            await require_admin(mock_request)
        assert exc_info.value.status_code == 403

    @pytest.mark.asyncio
    async def test_require_admin_is_admin(self):
        from ecommerce_ops.security.auth import require_admin
        from ecommerce_ops.security.models import Role, User

        user = User(id="u1", email="a@b.com", role=Role.ADMIN)
        mock_request = MagicMock()
        mock_request.state.user = user
        result = await require_admin(mock_request)
        assert result == user

    @pytest.mark.asyncio
    async def test_get_current_user_no_credentials(self):
        from ecommerce_ops.security.auth import get_current_user

        mock_request = MagicMock()
        mock_request.state.user = None
        result = await get_current_user(mock_request)
        assert result is None

    @pytest.mark.asyncio
    async def test_get_current_user_valid(self):
        from ecommerce_ops.security.auth import get_current_user
        from ecommerce_ops.security.models import Role, User

        mock_user = User(id="u1", email="a@b.com", role=Role.VIEWER)
        mock_request = MagicMock()
        mock_request.state.user = mock_user
        result = await get_current_user(mock_request)
        assert result == mock_user

    @pytest.mark.asyncio
    async def test_get_current_user_invalid(self):
        from ecommerce_ops.security.auth import get_current_user

        mock_request = MagicMock()
        mock_request.state.user = None
        result = await get_current_user(mock_request)
        assert result is None

    @pytest.mark.asyncio
    async def test_get_access_context(self):
        from ecommerce_ops.security.auth import get_access_context
        from ecommerce_ops.security.models import Role

        mock_request = MagicMock()
        mock_request.state = MagicMock()
        mock_request.state.user = MagicMock()
        mock_request.state.user.id = "u1"
        mock_request.state.user.role = Role.VIEWER
        mock_request.state.api_key_id = "key-1"
        mock_request.client = MagicMock()
        mock_request.client.host = "127.0.0.1"
        mock_request.headers = {"user-agent": "test-agent"}

        with patch("ecommerce_ops.security.auth.role_manager") as mock_rm:
            mock_rm.get_user_permissions = MagicMock(return_value=set())
            ctx = await get_access_context(mock_request)
            assert ctx.user_id == "u1"
            assert ctx.api_key_id == "key-1"

    @pytest.mark.asyncio
    async def test_get_access_context_no_user(self):
        from ecommerce_ops.security.auth import get_access_context

        mock_request = MagicMock()
        mock_request.state = MagicMock()
        mock_request.state.user = None
        mock_request.state.api_key_id = None
        mock_request.client = None
        mock_request.headers = {}

        ctx = await get_access_context(mock_request)
        assert ctx.user_id is None

    def test_log_request(self):
        from ecommerce_ops.security.auth import AuthenticationMiddleware

        mw = AuthenticationMiddleware(app=MagicMock())
        mock_request = MagicMock()
        mock_request.method = "GET"
        mock_request.url.path = "/api/test"
        mock_request.state = MagicMock()
        mock_request.state.user_id = "u1"
        mock_response = MagicMock()
        mock_response.status_code = 200
        mw._log_request(mock_request, mock_response, time.time() - 0.1)


class TestHardening:
    @pytest.mark.asyncio
    async def test_security_headers_options_allowed_origin(self):
        from ecommerce_ops.security.hardening import SecurityHeadersMiddleware

        mw = SecurityHeadersMiddleware(app=MagicMock())
        mock_request = MagicMock()
        mock_request.method = "OPTIONS"
        mock_request.headers = {"origin": "http://localhost:3000"}
        result = await mw.dispatch(mock_request, AsyncMock())
        assert result.status_code == 200
        assert "Access-Control-Allow-Origin" in result.headers

    @pytest.mark.asyncio
    async def test_security_headers_options_disallowed_origin(self):
        from ecommerce_ops.security.hardening import SecurityHeadersMiddleware

        mw = SecurityHeadersMiddleware(app=MagicMock())
        mock_request = MagicMock()
        mock_request.method = "OPTIONS"
        mock_request.headers = {"origin": "http://evil.com"}
        result = await mw.dispatch(mock_request, AsyncMock())
        assert "Access-Control-Allow-Origin" not in result.headers

    @pytest.mark.asyncio
    async def test_security_headers_normal_request(self):
        from ecommerce_ops.security.hardening import SecurityHeadersMiddleware

        mw = SecurityHeadersMiddleware(app=MagicMock())
        mock_request = MagicMock()
        mock_request.method = "GET"
        mock_request.headers = {"origin": "http://localhost:3000"}
        mock_response = MagicMock()
        mock_response.headers = {}
        call_next = AsyncMock(return_value=mock_response)
        result = await mw.dispatch(mock_request, call_next)
        assert "X-Content-Type-Options" in result.headers
        assert "X-Frame-Options" in result.headers
        assert "Strict-Transport-Security" in result.headers
        assert "Content-Security-Policy" in result.headers

    @pytest.mark.asyncio
    async def test_security_headers_no_origin(self):
        from ecommerce_ops.security.hardening import SecurityHeadersMiddleware

        mw = SecurityHeadersMiddleware(app=MagicMock())
        mock_request = MagicMock()
        mock_request.method = "GET"
        mock_request.headers = {}
        mock_response = MagicMock()
        mock_response.headers = {}
        call_next = AsyncMock(return_value=mock_response)
        result = await mw.dispatch(mock_request, call_next)
        assert "X-Content-Type-Options" in result.headers

    @pytest.mark.asyncio
    async def test_input_sanitization_blocks_script(self):
        from ecommerce_ops.security.hardening import InputSanitizationMiddleware

        mw = InputSanitizationMiddleware(app=MagicMock())
        mock_request = MagicMock()
        mock_request.method = "GET"
        mock_request.url = "http://localhost/api?x=<script>alert(1)</script>"
        mock_request.headers = {}
        mock_request.client = MagicMock()
        mock_request.client.host = "127.0.0.1"
        result = await mw.dispatch(mock_request, AsyncMock())
        assert result.status_code == 400

    @pytest.mark.asyncio
    async def test_input_sanitization_blocks_dangerous_header(self):
        from ecommerce_ops.security.hardening import InputSanitizationMiddleware

        mw = InputSanitizationMiddleware(app=MagicMock())
        mock_request = MagicMock()
        mock_request.method = "GET"
        mock_request.url = "http://localhost/api"
        mock_request.headers = {"X-Injected": "javascript:alert(1)"}
        mock_request.client = MagicMock()
        mock_request.client.host = "127.0.0.1"
        result = await mw.dispatch(mock_request, AsyncMock())
        assert result.status_code == 400

    @pytest.mark.asyncio
    async def test_input_sanitization_allows_clean_request(self):
        from ecommerce_ops.security.hardening import InputSanitizationMiddleware

        mw = InputSanitizationMiddleware(app=MagicMock())
        mock_request = MagicMock()
        mock_request.method = "GET"
        mock_request.url = "http://localhost/api/products"
        mock_request.headers = {"Content-Type": "application/json"}
        mock_response = MagicMock()
        call_next = AsyncMock(return_value=mock_response)
        result = await mw.dispatch(mock_request, call_next)
        assert result == mock_response

    @pytest.mark.asyncio
    async def test_request_logging_middleware(self):
        from ecommerce_ops.security.hardening import RequestLoggingMiddleware

        mw = RequestLoggingMiddleware(app=MagicMock())
        mock_request = MagicMock()
        mock_request.method = "GET"
        mock_request.url.path = "/api/test"
        mock_request.client = MagicMock()
        mock_request.client.host = "127.0.0.1"
        mock_response = MagicMock()
        mock_response.status_code = 200
        call_next = AsyncMock(return_value=mock_response)
        result = await mw.dispatch(mock_request, call_next)
        assert result == mock_response
