"""
Security API Routes
Endpoints for RBAC, API keys, and security management.
"""

import logging
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel

from ecommerce_ops.security.audit import audit_logger
from ecommerce_ops.security.auth import require_admin, require_auth
from ecommerce_ops.security.credential_store import credential_store
from ecommerce_ops.security.models import (
    Permission,
    Role,
    SecurityEvent,
    User,
)
from ecommerce_ops.security.role_manager import OPERATOR_USER_ID, role_manager
from ecommerce_ops.security.secrets_rotation import secret_rotation
from ecommerce_ops.utils import utc_now

logger = logging.getLogger("ecommerce_ops.api.security")

router = APIRouter(prefix="/security", tags=["security"])


class UserCreateRequest(BaseModel):
    email: str
    name: Optional[str] = None
    role: Role = Role.VIEWER
    permissions: Optional[List[Permission]] = None


class UserUpdateRequest(BaseModel):
    name: Optional[str] = None
    role: Optional[Role] = None
    is_active: Optional[bool] = None
    permissions: Optional[List[Permission]] = None


class APIKeyCreateRequest(BaseModel):
    name: str
    role: Role = Role.VIEWER
    expires_days: int = 90
    permissions: Optional[List[Permission]] = None


class APIKeyRotateRequest(BaseModel):
    key_id: str


class PermissionCheckRequest(BaseModel):
    permissions: List[Permission]


class ServerKeyRotateRequest(BaseModel):
    grace_days: int = 7


# ── Server Credential Rotation (week 9) ────────────────────


@router.post("/rotate/server-key")
async def rotate_server_key(
    req: ServerKeyRotateRequest,
    admin: User = Depends(require_admin),
):
    """Rotate the server API key with a zero-downtime grace window.

    Issues a new active credential and demotes every previously active
    credential to ``rotated`` (still accepted until ``valid_until``).
    The raw key is returned exactly once.
    """
    grace = max(1, min(req.grace_days, 30))
    raw_key, key_prefix = await credential_store.start_rotation(grace_days=grace)

    audit_logger.log_event(
        SecurityEvent(
            event_type="credential_rotation",
            action="rotate_server_key",
            resource="server_credential",
            resource_id=key_prefix,
            user_id=admin.id,
            success=True,
            details={"grace_days": grace, "key_prefix": key_prefix},
        )
    )

    return {
        "key": raw_key,  # Only shown once!
        "key_prefix": key_prefix,
        "grace_days": grace,
        "message": (
            f"Previous credentials remain valid for {grace} day(s). "
            "Deploy the new key to all clients, then call "
            "POST /security/rotate/server-key/finalize to cut over."
        ),
    }


@router.post("/rotate/server-key/finalize")
async def finalize_server_key_rotation(admin: User = Depends(require_admin)):
    """Revoke all rotated credentials immediately (cutover)."""
    revoked = await credential_store.finalize_rotation()

    audit_logger.log_event(
        SecurityEvent(
            event_type="credential_rotation",
            action="finalize_server_key_rotation",
            resource="server_credential",
            user_id=admin.id,
            success=True,
            details={"revoked_count": revoked},
        )
    )

    return {"revoked_count": revoked, "message": "Rotation finalized; old keys revoked."}


@router.get("/server-key/status")
async def server_key_status(admin: User = Depends(require_admin)):
    """Show the rotation ledger (prefixes + statuses, never raw keys)."""
    credentials = await credential_store.list_credentials()
    return {"credentials": credentials, "total": len(credentials)}


# ── Secret-rotation hygiene (audit remediation) ───────────


class SecretRotateRequest(BaseModel):
    name: str


@router.get("/secrets/rotation")
async def get_secrets_rotation(admin: User = Depends(require_admin)):
    """Return rotation health for all tracked secrets.

    Each entry carries ``status`` (``active`` / ``overdue`` / ``unknown``)
    and the last-checked timestamp.  An ``overdue_count > 0`` means at
    least one credential has exceeded its configured rotation period and
    should be rotated.
    """
    return secret_rotation.check_all()


@router.post("/secrets/rotate")
async def mark_secret_rotated(
    req: SecretRotateRequest,
    admin: User = Depends(require_admin),
):
    """Mark a tracked secret as just-rotated (updates last_rotated_at).

    This is the operator-facing mutation — call it after you have actually
    rotated the credential in the upstream provider / vault.
    """
    success = secret_rotation.mark_rotated(req.name)
    if not success:
        raise HTTPException(status_code=404, detail="Secret not tracked")
    return {"rotated": True, "name": req.name}


# ── Users ──────────────────────────────────────────────────


@router.post("/users")
async def create_user(req: UserCreateRequest, admin: User = Depends(require_admin)):
    """Create a new user."""
    try:
        user = await role_manager.create_user(
            email=req.email,
            name=req.name,
            role=req.role,
            permissions=set(req.permissions) if req.permissions else None,
        )

        audit_logger.log_event(
            SecurityEvent(
                event_type="user_management",
                action="create_user",
                resource="user",
                resource_id=user.id,
                user_id=admin.id,
                success=True,
                details={"email": req.email, "role": req.role.value},
            )
        )

        return {
            "id": user.id,
            "email": user.email,
            "role": user.role.value,
            "created_at": user.created_at.isoformat(),
        }

    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e


@router.get("/users")
async def list_users(
    role: Optional[Role] = None,
    is_active: Optional[bool] = None,
    admin: User = Depends(require_admin),
):
    """List users."""
    users = await role_manager.list_users(role=role, is_active=is_active)
    return {
        "users": [
            {
                "id": u.id,
                "email": u.email,
                "name": u.name,
                "role": u.role.value,
                "is_active": u.is_active,
                "created_at": u.created_at.isoformat(),
                "last_login": u.last_login.isoformat() if u.last_login else None,
            }
            for u in users
        ],
        "total": len(users),
    }


@router.get("/users/{user_id}")
async def get_user(user_id: str, admin: User = Depends(require_admin)):
    """Get user details."""
    user = await role_manager.get_user(user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    return {
        "id": user.id,
        "email": user.email,
        "name": user.name,
        "role": user.role.value,
        "is_active": user.is_active,
        "permissions": [p.value for p in user.permissions],
        "created_at": user.created_at.isoformat(),
        "last_login": user.last_login.isoformat() if user.last_login else None,
        "login_count": user.login_count,
    }


@router.patch("/users/{user_id}")
async def update_user(
    user_id: str,
    req: UserUpdateRequest,
    admin: User = Depends(require_admin),
):
    """Update user."""
    success = await role_manager.update_user(
        user_id=user_id,
        name=req.name,
        role=req.role,
        is_active=req.is_active,
        permissions=set(req.permissions) if req.permissions else None,
    )

    if not success:
        raise HTTPException(status_code=404, detail="User not found")

    audit_logger.log_event(
        SecurityEvent(
            event_type="user_management",
            action="update_user",
            resource="user",
            resource_id=user_id,
            user_id=admin.id,
            success=True,
            details=req.model_dump(exclude_none=True),
        )
    )

    return {"updated": True}


@router.delete("/users/{user_id}")
async def delete_user(user_id: str, admin: User = Depends(require_admin)):
    """Delete user."""
    success = await role_manager.delete_user(user_id)

    if not success:
        raise HTTPException(status_code=404, detail="User not found")

    audit_logger.log_event(
        SecurityEvent(
            event_type="user_management",
            action="delete_user",
            resource="user",
            resource_id=user_id,
            user_id=admin.id,
            success=True,
        )
    )

    return {"deleted": True}


# ── API Keys ───────────────────────────────────────────────


@router.post("/api-keys")
async def create_api_key(
    req: APIKeyCreateRequest,
    admin: User = Depends(require_admin),
):
    """Create API key."""
    if admin.id == OPERATOR_USER_ID:
        # The master key's principal has no DB row; materialize it so issued
        # keys have a resolvable owner (otherwise this endpoint 500s).
        await role_manager.ensure_operator_user()

    api_key = await role_manager.create_api_key(
        user_id=admin.id,
        name=req.name,
        role=req.role,
        expires_days=req.expires_days,
        permissions=set(req.permissions) if req.permissions else None,
    )

    audit_logger.log_event(
        SecurityEvent(
            event_type="api_key_management",
            action="create_api_key",
            resource="api_key",
            resource_id=api_key.id,
            user_id=admin.id,
            success=True,
            details={"name": req.name, "role": req.role.value},
        )
    )

    return {
        "id": api_key.id,
        "key": api_key.key,  # Only shown once!
        "name": api_key.name,
        "role": api_key.role.value,
        "expires_at": api_key.expires_at.isoformat() if api_key.expires_at else None,
        "created_at": api_key.created_at.isoformat(),
    }


@router.get("/api-keys")
async def list_api_keys(
    user_id: Optional[str] = None,
    is_active: Optional[bool] = None,
    admin: User = Depends(require_admin),
):
    """List API keys."""
    keys = await role_manager.list_api_keys(user_id=user_id, is_active=is_active)
    return {
        "api_keys": [
            {
                "id": k.id,
                "name": k.name,
                "user_id": k.user_id,
                "role": k.role.value,
                "is_active": k.is_active,
                "expires_at": k.expires_at.isoformat() if k.expires_at else None,
                "last_used": k.last_used.isoformat() if k.last_used else None,
                "usage_count": k.usage_count,
                "created_at": k.created_at.isoformat(),
            }
            for k in keys
        ],
        "total": len(keys),
    }


@router.post("/api-keys/rotate")
async def rotate_api_key(
    req: APIKeyRotateRequest,
    admin: User = Depends(require_admin),
):
    """Rotate an API key: issues a new key and revokes the old one."""
    api_key = await role_manager.rotate_api_key(req.key_id)

    if not api_key:
        raise HTTPException(status_code=404, detail="API key not found or already revoked")

    audit_logger.log_event(
        SecurityEvent(
            event_type="api_key_management",
            action="rotate_api_key",
            resource="api_key",
            resource_id=api_key.id,
            user_id=admin.id,
            success=True,
            details={"previous_key_id": req.key_id, "name": api_key.name, "role": api_key.role.value},
        )
    )

    return {
        "id": api_key.id,
        "key": api_key.key,  # Only shown once!
        "name": api_key.name,
        "role": api_key.role.value,
        "expires_at": api_key.expires_at.isoformat() if api_key.expires_at else None,
        "created_at": api_key.created_at.isoformat(),
        "previous_key_revoked": True,
    }


@router.delete("/api-keys/{key_id}")
async def revoke_api_key(key_id: str, admin: User = Depends(require_admin)):
    """Revoke API key."""
    success = await role_manager.revoke_api_key(key_id)

    if not success:
        raise HTTPException(status_code=404, detail="API key not found")

    audit_logger.log_event(
        SecurityEvent(
            event_type="api_key_management",
            action="revoke_api_key",
            resource="api_key",
            resource_id=key_id,
            user_id=admin.id,
            success=True,
        )
    )

    return {"revoked": True}


# ── Roles ──────────────────────────────────────────────────


@router.get("/roles")
async def list_roles(admin: User = Depends(require_admin)):
    """List all roles."""
    roles = role_manager.list_roles()
    return {
        "roles": [
            {
                "name": r.name.value,
                "display_name": r.display_name,
                "description": r.description,
                "permissions_count": len(r.permissions),
                "is_system": r.is_system,
            }
            for r in roles
        ],
    }


@router.get("/roles/{role_name}/permissions")
async def get_role_permissions(role_name: str, admin: User = Depends(require_admin)):
    """Get permissions for a role."""
    try:
        role = Role(role_name)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid role") from None

    role_def = role_manager.get_role(role)
    if not role_def:
        raise HTTPException(status_code=404, detail="Role not found")

    return {
        "role": role_name,
        "permissions": [p.value for p in role_def.permissions],
    }


# ── Permission Checks ─────────────────────────────────────


@router.post("/check-permissions")
async def check_permissions(
    req: PermissionCheckRequest,
    user: User = Depends(require_auth),
):
    """Check if current user has specific permissions."""
    result = role_manager.check_permissions(user, set(req.permissions))
    return {
        "allowed": result.allowed,
        "role": result.role.value if result.role else None,
        "missing_permissions": [p.value for p in result.missing_permissions],
    }


@router.get("/my-permissions")
async def get_my_permissions(user: User = Depends(require_auth)):
    """Get current user's permissions."""
    permissions = role_manager.get_user_permissions(user)
    return {
        "user_id": user.id,
        "role": user.role.value,
        "permissions": [p.value for p in permissions],
    }


# ── Security Summary ───────────────────────────────────────


@router.get("/audit/summary")
async def get_audit_summary(
    hours: int = Query(24, ge=1, le=168),
    admin: User = Depends(require_admin),
):
    """Get security audit summary."""
    return await audit_logger.get_security_summary(hours=hours)


@router.get("/audit/logs")
async def get_audit_logs(
    event_type: Optional[str] = None,
    user_id: Optional[str] = None,
    limit: int = Query(100, ge=1, le=1000),
    admin: User = Depends(require_admin),
):
    """Get audit logs."""
    entries = await audit_logger.get_entries(
        event_type=event_type,
        user_id=user_id,
        limit=limit,
    )
    return {
        "entries": [
            {
                "id": e.id,
                "timestamp": e.timestamp.isoformat(),
                "event_type": e.event_type,
                "action": e.action,
                "resource": e.resource,
                "resource_id": e.resource_id,
                "user_id": e.user_id,
                "success": e.success,
                "risk_level": e.risk_level,
            }
            for e in entries
        ],
        "total": len(entries),
    }


# ── Health ─────────────────────────────────────────────────


@router.get("/health")
async def security_health():
    """Health check for security service."""
    return {
        "status": "healthy",
        "rbac": "enabled",
        "audit_logging": "enabled",
        "rate_limiting": "enabled",
        "timestamp": utc_now().isoformat(),
    }
