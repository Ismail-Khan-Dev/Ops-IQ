"""
RBAC Models and Permissions
Role-Based Access Control models and permission definitions.
"""

from datetime import datetime
from enum import StrEnum
from typing import Any, Dict, List, Optional, Set

from pydantic import BaseModel, Field

from ecommerce_ops.utils import utc_now


class Permission(StrEnum):
    """System permissions."""

    # Dashboard
    DASHBOARD_VIEW = "dashboard:view"
    DASHBOARD_EDIT = "dashboard:edit"

    # Agents
    AGENTS_VIEW = "agents:view"
    AGENTS_CONFIGURE = "agents:configure"
    AGENTS_EXECUTE = "agents:execute"

    # Approvals
    APPROVALS_VIEW = "approvals:view"
    APPROVALS_APPROVE = "approvals:approve"
    APPROVALS_REJECT = "approvals:reject"
    APPROVALS_BATCH = "approvals:batch"

    # Shopify
    SHOPIFY_VIEW = "shopify:view"
    SHOPIFY_CONFIGURE = "shopify:configure"
    SHOPIFY_SYNC = "shopify:sync"
    SHOPIFY_WEBHOOKS = "shopify:webhooks"

    # Cart Recovery
    CART_RECOVERY_VIEW = "cart_recovery:view"
    CART_RECOVERY_EXECUTE = "cart_recovery:execute"

    # Customer Support
    SUPPORT_VIEW = "support:view"
    SUPPORT_RESPOND = "support:respond"
    SUPPORT_ESCALATE = "support:escalate"

    # Observability
    OBSERVABILITY_VIEW = "observability:view"
    OBSERVABILITY_EVALUATE = "observability:evaluate"

    # Memory
    MEMORY_VIEW = "memory:view"
    MEMORY_EDIT = "memory:edit"
    MEMORY_DELETE = "memory:delete"

    # Settings
    SETTINGS_VIEW = "settings:view"
    SETTINGS_EDIT = "settings:edit"

    # Users
    USERS_VIEW = "users:view"
    USERS_CREATE = "users:create"
    USERS_EDIT = "users:edit"
    USERS_DELETE = "users:delete"

    # Roles
    ROLES_VIEW = "roles:view"
    ROLES_MANAGE = "roles:manage"

    # Audit
    AUDIT_VIEW = "audit:view"
    AUDIT_EXPORT = "audit:export"

    # API Keys
    API_KEYS_VIEW = "api_keys:view"
    API_KEYS_CREATE = "api_keys:create"
    API_KEYS_REVOKE = "api_keys:revoke"

    # Integrations / outbound webhooks
    INTEGRATIONS_MANAGE = "integrations:manage"


class Role(StrEnum):
    """Predefined roles."""

    SUPER_ADMIN = "super_admin"
    ADMIN = "admin"
    OPERATOR = "operator"
    VIEWER = "viewer"
    API_ONLY = "api_only"


class RoleDefinition(BaseModel):
    """Definition of a role."""

    name: Role
    display_name: str
    description: str
    permissions: Set[Permission]
    is_system: bool = True  # System roles can't be deleted
    created_at: datetime = Field(default_factory=utc_now)
    updated_at: datetime = Field(default_factory=utc_now)


class User(BaseModel):
    """User model."""

    id: str
    email: str
    name: Optional[str] = None
    role: Role = Role.VIEWER
    is_active: bool = True
    is_api_only: bool = False
    permissions: Set[Permission] = Field(default_factory=set)
    metadata: Dict[str, Any] = Field(default_factory=dict)
    created_at: datetime = Field(default_factory=utc_now)
    last_login: Optional[datetime] = None
    login_count: int = 0

    class Config:
        extra = "allow"

    @property
    def is_admin(self) -> bool:
        return self.role in (Role.SUPER_ADMIN, Role.ADMIN)

    @property
    def is_super_admin(self) -> bool:
        return self.role == Role.SUPER_ADMIN


class APIKey(BaseModel):
    """API key model."""

    id: str
    key: str
    name: str
    user_id: str
    role: Role
    permissions: Set[Permission] = Field(default_factory=set)
    is_active: bool = True
    expires_at: Optional[datetime] = None
    last_used: Optional[datetime] = None
    usage_count: int = 0
    created_at: datetime = Field(default_factory=utc_now)
    metadata: Dict[str, Any] = Field(default_factory=dict)

    class Config:
        extra = "allow"

    @property
    def is_expired(self) -> bool:
        if self.expires_at:
            return utc_now() > self.expires_at
        return False


class PermissionCheck(BaseModel):
    """Result of a permission check."""

    allowed: bool
    reason: Optional[str] = None
    role: Optional[Role] = None
    missing_permissions: List[Permission] = Field(default_factory=list)


class AccessContext(BaseModel):
    """Context for access control decisions."""

    user_id: Optional[str] = None
    api_key_id: Optional[str] = None
    role: Optional[Role] = None
    permissions: Set[Permission] = Field(default_factory=set)
    ip_address: Optional[str] = None
    user_agent: Optional[str] = None
    timestamp: datetime = Field(default_factory=utc_now)


class SecurityEvent(BaseModel):
    """Security event for audit logging."""

    event_type: str
    user_id: Optional[str] = None
    api_key_id: Optional[str] = None
    action: str
    resource: str
    resource_id: Optional[str] = None
    success: bool
    ip_address: Optional[str] = None
    user_agent: Optional[str] = None
    details: Dict[str, Any] = Field(default_factory=dict)
    timestamp: datetime = Field(default_factory=utc_now)


# ── Default Role Definitions ───────────────────────────────

DEFAULT_ROLES: Dict[Role, RoleDefinition] = {
    Role.SUPER_ADMIN: RoleDefinition(
        name=Role.SUPER_ADMIN,
        display_name="Super Administrator",
        description="Full system access with all permissions",
        permissions=set(Permission),  # All permissions
        is_system=True,
    ),
    Role.ADMIN: RoleDefinition(
        name=Role.ADMIN,
        display_name="Administrator",
        description="Administrative access with most permissions",
        permissions={
            Permission.DASHBOARD_VIEW,
            Permission.DASHBOARD_EDIT,
            Permission.AGENTS_VIEW,
            Permission.AGENTS_CONFIGURE,
            Permission.AGENTS_EXECUTE,
            Permission.APPROVALS_VIEW,
            Permission.APPROVALS_APPROVE,
            Permission.APPROVALS_REJECT,
            Permission.APPROVALS_BATCH,
            Permission.SHOPIFY_VIEW,
            Permission.SHOPIFY_CONFIGURE,
            Permission.SHOPIFY_SYNC,
            Permission.SHOPIFY_WEBHOOKS,
            Permission.CART_RECOVERY_VIEW,
            Permission.CART_RECOVERY_EXECUTE,
            Permission.SUPPORT_VIEW,
            Permission.SUPPORT_RESPOND,
            Permission.SUPPORT_ESCALATE,
            Permission.OBSERVABILITY_VIEW,
            Permission.OBSERVABILITY_EVALUATE,
            Permission.MEMORY_VIEW,
            Permission.MEMORY_EDIT,
            Permission.MEMORY_DELETE,
            Permission.SETTINGS_VIEW,
            Permission.SETTINGS_EDIT,
            Permission.USERS_VIEW,
            Permission.USERS_CREATE,
            Permission.USERS_EDIT,
            Permission.AUDIT_VIEW,
            Permission.AUDIT_EXPORT,
            Permission.API_KEYS_VIEW,
            Permission.API_KEYS_CREATE,
            Permission.API_KEYS_REVOKE,
            Permission.INTEGRATIONS_MANAGE,
        },
        is_system=True,
    ),
    Role.OPERATOR: RoleDefinition(
        name=Role.OPERATOR,
        display_name="Operator",
        description="Operational access for day-to-day tasks",
        permissions={
            Permission.DASHBOARD_VIEW,
            Permission.AGENTS_VIEW,
            Permission.AGENTS_EXECUTE,
            Permission.APPROVALS_VIEW,
            Permission.APPROVALS_APPROVE,
            Permission.APPROVALS_REJECT,
            Permission.SHOPIFY_VIEW,
            Permission.SHOPIFY_SYNC,
            Permission.CART_RECOVERY_VIEW,
            Permission.CART_RECOVERY_EXECUTE,
            Permission.SUPPORT_VIEW,
            Permission.SUPPORT_RESPOND,
            Permission.OBSERVABILITY_VIEW,
            Permission.MEMORY_VIEW,
            Permission.SETTINGS_VIEW,
            Permission.AUDIT_VIEW,
        },
        is_system=True,
    ),
    Role.VIEWER: RoleDefinition(
        name=Role.VIEWER,
        display_name="Viewer",
        description="Read-only access to dashboards and data",
        permissions={
            Permission.DASHBOARD_VIEW,
            Permission.AGENTS_VIEW,
            Permission.APPROVALS_VIEW,
            Permission.SHOPIFY_VIEW,
            Permission.CART_RECOVERY_VIEW,
            Permission.SUPPORT_VIEW,
            Permission.OBSERVABILITY_VIEW,
            Permission.SETTINGS_VIEW,
        },
        is_system=True,
    ),
    Role.API_ONLY: RoleDefinition(
        name=Role.API_ONLY,
        display_name="API Only",
        description="API access only, no dashboard access",
        permissions={
            Permission.AGENTS_EXECUTE,
            Permission.SHOPIFY_SYNC,
            Permission.SHOPIFY_WEBHOOKS,
            Permission.CART_RECOVERY_EXECUTE,
            Permission.SUPPORT_RESPOND,
        },
        is_system=True,
    ),
}
