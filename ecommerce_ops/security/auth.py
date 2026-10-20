"""
Authentication Middleware
FastAPI middleware for authentication and authorization.
"""

import hmac
import logging
import time
from typing import ClassVar, Optional, Set

from fastapi import HTTPException, Request
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.responses import JSONResponse, Response

from ecommerce_ops.config import Environment
from ecommerce_ops.config import settings as app_settings
from ecommerce_ops.security.models import (
    AccessContext,
    Permission,
    Role,
    User,
)
from ecommerce_ops.security.role_manager import role_manager

logger = logging.getLogger("ecommerce_ops.security.auth")


class AuthenticationMiddleware(BaseHTTPMiddleware):
    """Middleware for request authentication and logging."""

    PUBLIC_PATHS: ClassVar[Set[str]] = {
        "/",
        "/health",
        "/live",
        "/ready",
    }

    # Paths public only in development (docs + raw metrics). In testing and
    # production these require the operator API key (docs are also disabled at
    # the FastAPI layer). Prometheus authenticates via its scrape token.
    DEV_ONLY_PUBLIC_PATHS: ClassVar[Set[str]] = {
        "/metrics",
        "/docs",
        "/openapi.json",
        "/redoc",
    }

    # Paths that authenticate inside the handler (no bearer precondition):
    #  - /api/auth/login     verifies the API key from the request body
    #  - /shopify/callback   OAuth callback (HMAC + single-use state), called by Shopify
    #  - /ws/queue           WebSocket handshake (ticket/API key validated in ws.py)
    # Note: /shopify/install is NOT here — generating the OAuth install URL is an
    # operator action and is gated by SHOPIFY_CONFIGURE at the route layer.
    SELF_AUTH_PATHS: ClassVar[Set[str]] = {
        "/api/auth/login",
        "/shopify/callback",
        "/ws/queue",
    }

    # Shopify webhooks are authenticated via the X-Shopify-Hmac-SHA256 header
    # inside the handler, so they must never be gated by a bearer token.
    API_KEY_PATHS: ClassVar[Set[str]] = {
        "/shopify/webhooks",
        "/api/shopify/webhooks",
    }

    def _matches_configured_key(self, token: str) -> bool:
        """True if token matches the operator API key configured in settings."""
        configured = getattr(app_settings, "API_KEY", None)
        if not configured:
            return False
        try:
            expected = configured.get_secret_value()
        except AttributeError:
            expected = str(configured)
        if not expected:
            return False
        return hmac.compare_digest(token, expected)

    def _operator_user(self) -> "User":
        """Synthetic SUPER_ADMIN principal for the configured operator key.

        The operator (master) API key is granted full privileges so that
        per-route RBAC checks work uniformly for both the operator key and
        RBAC-issued keys.
        """
        return User(
            id="operator",
            email="operator@local",
            name="Operator",
            role=Role.SUPER_ADMIN,
            is_active=True,
            permissions=set(Permission),
        )

    async def dispatch(
        self,
        request: Request,
        call_next: RequestResponseEndpoint,
    ) -> Response:
        start_time = time.time()

        request_id = str(time.time_ns())
        request.state.request_id = request_id

        if self._is_anon_safe(request.url.path) or request.method == "OPTIONS":
            response = await call_next(request)
            self._log_request(request, response, start_time)
            return response

        api_key = request.headers.get("X-API-Key")
        auth_header = request.headers.get("Authorization")

        user = None
        api_key_id = None
        authenticated = False

        if api_key:
            try:
                if self._matches_configured_key(api_key):
                    authenticated = True
                    user = self._operator_user()
                    api_key_id = "operator-master"
                else:
                    api_key_obj = await role_manager.validate_api_key(api_key)
                    if api_key_obj:
                        authenticated = True
                        user = await role_manager.get_user(api_key_obj.user_id)
                        api_key_id = api_key_obj.id
                    else:
                        return JSONResponse(
                            status_code=401,
                            content={"detail": "Invalid API key"},
                        )
            except Exception:
                logger.error("Auth failed: API key validation error")
                return JSONResponse(
                    status_code=503,
                    content={"detail": "Authentication service unavailable"},
                )
        elif auth_header and auth_header.startswith("Bearer "):
            token = auth_header[7:]
            try:
                if self._matches_configured_key(token):
                    authenticated = True
                    user = self._operator_user()
                    api_key_id = "operator-master"
                else:
                    api_key_obj = await role_manager.validate_api_key(token)
                    if api_key_obj:
                        authenticated = True
                        user = await role_manager.get_user(api_key_obj.user_id)
                        api_key_id = api_key_obj.id
                    else:
                        return JSONResponse(
                            status_code=401,
                            content={"detail": "Invalid bearer token"},
                        )
            except Exception:
                logger.error("Auth failed: Bearer token validation error")
                return JSONResponse(
                    status_code=503,
                    content={"detail": "Authentication service unavailable"},
                )

        request.state.user = user
        request.state.api_key_id = api_key_id
        request.state.user_id = user.id if user else None

        if not authenticated:
            response = JSONResponse(
                status_code=401,
                content={"detail": "Authentication required"},
            )
            self._log_request(request, response, start_time)
            return response

        response = await call_next(request)
        self._log_request(request, response, start_time)

        return response

    def _is_anon_safe(self, path: str) -> bool:
        return (
            self._is_public_path(path)
            or path in self.SELF_AUTH_PATHS
            or any(path == p or path.startswith(p + "/") for p in self.API_KEY_PATHS)
        )

    def _is_public_path(self, path: str) -> bool:
        if path in self.PUBLIC_PATHS:
            return True
        if path in self.DEV_ONLY_PUBLIC_PATHS and app_settings.ENV == Environment.DEVELOPMENT:
            return True
        return path.startswith("/static/") or path.endswith((".js", ".css", ".ico"))

    def _log_request(
        self,
        request: Request,
        response: Response,
        start_time: float,
    ):
        duration_ms = (time.time() - start_time) * 1000
        logger.info(
            "Request: %s %s -> %d (%.1fms) [user=%s]",
            request.method,
            request.url.path,
            response.status_code,
            duration_ms,
            getattr(request.state, "user_id", "anonymous"),
        )


async def get_authenticated_user(request: Request) -> User:
    """Return the authenticated principal set by ``AuthenticationMiddleware``.

    Works for both the operator (master) key and RBAC-issued keys because the
    middleware populates ``request.state.user`` for every authenticated request.
    """
    user = getattr(request.state, "user", None)
    if user is None:
        raise HTTPException(status_code=401, detail="Authentication required")
    if not user.is_active:
        raise HTTPException(status_code=401, detail="User not found or inactive")
    return user


async def require_auth(request: Request) -> User:
    """Dependency requiring authentication (returns the principal)."""
    return await get_authenticated_user(request)


def require_permission(permission: Permission):
    """Dependency factory enforcing a specific permission (RBAC)."""

    async def dependency(request: Request) -> User:
        user = await get_authenticated_user(request)
        result = role_manager.check_permission(user, permission)
        if not result.allowed:
            raise HTTPException(
                status_code=403,
                detail=f"Permission denied: {permission.value}",
            )
        return user

    return dependency


def require_role(role: Role):
    """Dependency factory enforcing a specific role (or super admin)."""

    async def dependency(request: Request) -> User:
        user = await get_authenticated_user(request)
        if user.role != role and not user.is_super_admin:
            raise HTTPException(
                status_code=403,
                detail=f"Role required: {role.value}",
            )
        return user

    return dependency


async def require_admin(request: Request) -> User:
    """Dependency requiring an admin or super-admin role."""
    user = await get_authenticated_user(request)
    if not user.is_admin:
        raise HTTPException(status_code=403, detail="Admin access required")
    return user


async def get_current_user(request: Request) -> Optional[User]:
    """Dependency returning the current principal (optional auth)."""
    return getattr(request.state, "user", None)


async def get_access_context(request: Request) -> AccessContext:
    """Get access context from request."""
    user = getattr(request.state, "user", None)
    api_key_id = getattr(request.state, "api_key_id", None)

    return AccessContext(
        user_id=user.id if user else None,
        api_key_id=api_key_id,
        role=user.role if user else None,
        permissions=role_manager.get_user_permissions(user) if user else set(),
        ip_address=request.client.host if request.client else None,
        user_agent=request.headers.get("user-agent"),
    )
