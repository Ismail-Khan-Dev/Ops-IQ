"""
RBAC Middleware
Enforces role-based access control per endpoint.
"""
import logging
from enum import Enum

from fastapi import HTTPException, Request
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.responses import Response

from ecommerce_ops.security.models import Role

logger = logging.getLogger("ecommerce_ops.security.rbac")


class AccessLevel(Enum):
    PUBLIC = "public"
    VIEWER = "viewer"
    OPERATOR = "operator"
    ADMIN = "admin"
    SUPER_ADMIN = "super_admin"


ROLE_HIERARCHY = {
    Role.VIEWER: AccessLevel.VIEWER,
    Role.OPERATOR: AccessLevel.OPERATOR,
    Role.ADMIN: AccessLevel.ADMIN,
    Role.SUPER_ADMIN: AccessLevel.SUPER_ADMIN,
}

PATH_ACCESS_LEVELS: dict[str, AccessLevel] = {
    "/health": AccessLevel.PUBLIC,
    "/live": AccessLevel.PUBLIC,
    "/ready": AccessLevel.PUBLIC,
    "/metrics": AccessLevel.PUBLIC,
    "/api/auth/login": AccessLevel.PUBLIC,
    "/api/auth/sso/providers": AccessLevel.PUBLIC,
    "/api/auth/sso/login": AccessLevel.PUBLIC,
    "/api/auth/sso/callback": AccessLevel.PUBLIC,
    "/api/agents/status": AccessLevel.VIEWER,
    "/api/analytics": AccessLevel.VIEWER,
    "/api/approvals": AccessLevel.VIEWER,
    "/api/settings": AccessLevel.VIEWER,
    "/api/audit": AccessLevel.VIEWER,
    "/api/audit/export": AccessLevel.VIEWER,
    "/observability/traces": AccessLevel.VIEWER,
    "/observability/health": AccessLevel.VIEWER,
    "/observability/metrics": AccessLevel.VIEWER,
    "/observability/slos": AccessLevel.VIEWER,
    "/observability/registry": AccessLevel.VIEWER,
    "/memory/health": AccessLevel.VIEWER,
    "/memory/memories": AccessLevel.VIEWER,
    "/memory/sessions": AccessLevel.VIEWER,
    "/cart-recovery/health": AccessLevel.VIEWER,
    "/cart-recovery/analytics": AccessLevel.VIEWER,
    "/support/health": AccessLevel.VIEWER,
    "/support/tickets": AccessLevel.VIEWER,
    "/support/analytics": AccessLevel.VIEWER,
    "/api/run": AccessLevel.OPERATOR,
    "/cart-recovery/analyze": AccessLevel.OPERATOR,
    "/cart-recovery/recover": AccessLevel.OPERATOR,
    "/security/roles": AccessLevel.ADMIN,
    "/security/users": AccessLevel.ADMIN,
    "/security/events": AccessLevel.ADMIN,
    "/observability/registry/reload": AccessLevel.ADMIN,
    "/api/agents": AccessLevel.ADMIN,
}


def get_required_access_level(path: str) -> AccessLevel:
    if path in PATH_ACCESS_LEVELS:
        return PATH_ACCESS_LEVELS[path]

    for prefix, level in PATH_ACCESS_LEVELS.items():
        if path.startswith(prefix + "/"):
            return level

    return AccessLevel.OPERATOR


class RBACMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        path = request.url.path
        required_level = get_required_access_level(path)

        if required_level == AccessLevel.PUBLIC:
            return await call_next(request)

        user = getattr(request.state, "user", None)
        if user is None:
            return await call_next(request)

        if hasattr(user, "is_super_admin") and user.is_super_admin:
            return await call_next(request)

        user_role = getattr(user, "role", Role.VIEWER)
        user_level = ROLE_HIERARCHY.get(user_role, AccessLevel.VIEWER)

        level_order = [
            AccessLevel.VIEWER,
            AccessLevel.OPERATOR,
            AccessLevel.ADMIN,
            AccessLevel.SUPER_ADMIN,
        ]

        if level_order.index(user_level) < level_order.index(required_level):
            logger.warning(
                "RBAC denied: user=%s role=%s path=%s required=%s",
                getattr(user, "id", "unknown"),
                user_role.value if hasattr(user_role, "value") else str(user_role),
                path,
                required_level.value,
            )
            raise HTTPException(
                status_code=403,
                detail=f"Insufficient permissions. Required: {required_level.value}",
            )

        return await call_next(request)
