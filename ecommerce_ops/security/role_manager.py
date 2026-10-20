"""
Role Management Service (PostgreSQL-backed)
Manages roles, users, and permission checks with persistent storage.
"""

import base64
import hashlib
import hmac
import logging
import secrets
import uuid
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional, Set

from sqlalchemy import select

from ecommerce_ops.api.metrics import (
    METRIC_LEGACY_API_KEY_REJECTED,
    METRIC_LEGACY_API_KEY_USES,
)
from ecommerce_ops.models.db import RBACApiKey, RBACUser, async_session_factory
from ecommerce_ops.security.models import (
    DEFAULT_ROLES,
    APIKey,
    Permission,
    PermissionCheck,
    Role,
    RoleDefinition,
    User,
)
from ecommerce_ops.utils import utc_now

logger = logging.getLogger("ecommerce_ops.security.role_manager")

PBKDF2_ITERATIONS = 600_000

# Hard cutover for the legacy unsalted SHA-256 API-key hash format. Until this
# date (naive UTC, matching ``utc_now()``) legacy hashes are accepted but logged
# and metered; after it, the verifier refuses them outright to force rotation.
LEGACY_HASH_SUNSET_UTC = datetime(2027, 1, 1)

# The auth middleware synthesizes this principal for the master (operator) API
# key without a backing DB row (see AuthenticationMiddleware._operator_user).
# Some operations — e.g. issuing an RBAC API key — require the owning user to
# exist so that issued keys stay validable (validate_api_key -> get_user).
OPERATOR_USER_ID = "operator"
OPERATOR_USER_EMAIL = "operator@local"


def _fast_hash_api_key(key: str) -> str:
    """Fast sha256 hash for O(1) key lookup (C10).

    This is used as a pre-filter: the slow PBKDF2 verification only runs
    on keys whose fast hash matches.  The fast hash is not stored as the
    primary hash (PBKDF2 remains the canonical secure hash), but it allows
    us to avoid scanning every row in ``rbac_api_keys`` on every request.
    """
    return hashlib.sha256(key.encode()).hexdigest()


def _hash_api_key(key: str) -> str:
    """Hash an API key using salted PBKDF2-SHA256 for secure storage."""
    salt = secrets.token_bytes(16)
    dk = hashlib.pbkdf2_hmac("sha256", key.encode("utf-8"), salt, PBKDF2_ITERATIONS)
    return "pbkdf2_sha256${}${}${}".format(
        PBKDF2_ITERATIONS,
        base64.b64encode(salt).decode("ascii"),
        base64.b64encode(dk).decode("ascii"),
    )


def _legacy_hash_api_key(key: str) -> str:
    """Legacy unsalted SHA-256 hexdigest (pre-migration rows only)."""
    return hashlib.sha256(key.encode()).hexdigest()


def _verify_api_key_hash(key: str, stored: str) -> bool:
    """Verify a key against a stored hash.

    Supports the current salted PBKDF2 format and falls back to legacy
    unsalted SHA-256 so existing keys keep working until rotated. Every legacy
    use is logged and metered so migration progress is observable, and after
    ``LEGACY_HASH_SUNSET_UTC`` the legacy path is refused outright.
    """
    if stored.count("$") != 3:
        if utc_now() >= LEGACY_HASH_SUNSET_UTC:
            logger.warning(
                "Legacy SHA-256 API-key hash rejected: past sunset %s, rotate the key",
                LEGACY_HASH_SUNSET_UTC.date(),
            )
            METRIC_LEGACY_API_KEY_REJECTED.inc()
            return False
        logger.warning(
            "Legacy unsalted SHA-256 API-key hash used for authentication; "
            "rotate the key to PBKDF2 before %s",
            LEGACY_HASH_SUNSET_UTC.date(),
        )
        METRIC_LEGACY_API_KEY_USES.inc()
        return hmac.compare_digest(_legacy_hash_api_key(key), stored)

    try:
        _prefix, iterations, salt_b64, expected_b64 = stored.split("$")
        salt = base64.b64decode(salt_b64)
        expected = base64.b64decode(expected_b64)
        dk = hashlib.pbkdf2_hmac("sha256", key.encode("utf-8"), salt, int(iterations))
        return hmac.compare_digest(dk, expected)
    except (ValueError, TypeError) as e:
        logger.warning("Unable to parse stored API key hash: %s", e)
        return False


class RoleManager:
    """Manages roles, users, and permissions with PostgreSQL persistence."""

    def __init__(self):
        self._roles: Dict[str, RoleDefinition] = {
            role.value: defn for role, defn in DEFAULT_ROLES.items()
        }

    # ── Role Management (in-memory, rarely changes) ────────

    def get_role(self, role) -> Optional[RoleDefinition]:
        if isinstance(role, Role):
            return self._roles.get(role.value)
        return self._roles.get(str(role))

    def list_roles(self) -> List[RoleDefinition]:
        return list(self._roles.values())

    def create_role(
        self,
        name: str,
        display_name: str,
        description: str,
        permissions: Set[Permission],
    ) -> RoleDefinition:
        if name in self._roles:
            raise ValueError(f"Role {name} already exists")
        role_enum = Role(name) if name in {r.value for r in Role} else None
        definition = RoleDefinition(
            name=role_enum if role_enum else Role.VIEWER,
            display_name=display_name,
            description=description,
            permissions=permissions,
            is_system=False,
        )
        self._roles[name] = definition
        logger.info("Created role: %s", name)
        return definition

    def update_role_permissions(self, role, permissions: Set[Permission]) -> bool:
        key = role.value if isinstance(role, Role) else str(role)
        definition = self._roles.get(key)
        if not definition:
            return False
        if definition.is_system:
            logger.warning("Cannot modify system role: %s", role)
            return False
        definition.permissions = permissions
        definition.updated_at = utc_now()
        return True

    def delete_role(self, role) -> bool:
        key = role.value if isinstance(role, Role) else str(role)
        definition = self._roles.get(key)
        if not definition:
            return False
        if definition.is_system:
            return False
        del self._roles[key]
        return True

    # ── User Management (PostgreSQL) ──────────────────────

    async def create_user(
        self,
        email: str,
        name: Optional[str] = None,
        role: Role = Role.VIEWER,
        permissions: Optional[Set[Permission]] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> User:
        async with async_session_factory() as session:
            # Check duplicate email
            existing = await session.execute(select(RBACUser).where(RBACUser.email == email))
            if existing.scalar_one_or_none():
                raise ValueError(f"User with email {email} already exists")

            user_id = str(uuid.uuid4())
            db_user = RBACUser(
                id=user_id,
                email=email,
                name=name,
                role=role.value,
                is_active=True,
                permissions=[p.value for p in (permissions or set())],
                metadata_json=metadata or {},
            )
            session.add(db_user)
            await session.commit()

            logger.info("Created user: %s (email=%s, role=%s)", user_id, email, role)
            return User(
                id=user_id,
                email=email,
                name=name,
                role=role,
                permissions=permissions or set(),
                metadata=metadata or {},
            )

    async def get_user(self, user_id: str) -> Optional[User]:
        async with async_session_factory() as session:
            result = await session.execute(select(RBACUser).where(RBACUser.id == user_id))
            db_user = result.scalar_one_or_none()
            if not db_user:
                return None
            return self._db_to_user(db_user)

    async def get_user_by_email(self, email: str) -> Optional[User]:
        async with async_session_factory() as session:
            result = await session.execute(select(RBACUser).where(RBACUser.email == email))
            db_user = result.scalar_one_or_none()
            if not db_user:
                return None
            return self._db_to_user(db_user)

    async def list_users(
        self,
        role: Optional[Role] = None,
        is_active: Optional[bool] = None,
    ) -> List[User]:
        async with async_session_factory() as session:
            stmt = select(RBACUser)
            if role:
                stmt = stmt.where(RBACUser.role == role.value)
            if is_active is not None:
                stmt = stmt.where(RBACUser.is_active == is_active)
            result = await session.execute(stmt.order_by(RBACUser.created_at.desc()))
            return [self._db_to_user(u) for u in result.scalars().all()]

    async def update_user(
        self,
        user_id: str,
        name: Optional[str] = None,
        role: Optional[Role] = None,
        is_active: Optional[bool] = None,
        permissions: Optional[Set[Permission]] = None,
    ) -> bool:
        async with async_session_factory() as session:
            result = await session.execute(select(RBACUser).where(RBACUser.id == user_id))
            db_user = result.scalar_one_or_none()
            if not db_user:
                return False

            if name is not None:
                db_user.name = name
            if role is not None:
                db_user.role = role.value
            if is_active is not None:
                db_user.is_active = is_active
            if permissions is not None:
                db_user.permissions = [p.value for p in permissions]
            db_user.updated_at = utc_now()

            await session.commit()
            logger.info("Updated user: %s", user_id)
            return True

    async def delete_user(self, user_id: str) -> bool:
        async with async_session_factory() as session:
            result = await session.execute(select(RBACUser).where(RBACUser.id == user_id))
            db_user = result.scalar_one_or_none()
            if not db_user:
                return False
            await session.delete(db_user)
            await session.commit()
            logger.info("Deleted user: %s", user_id)
            return True

    async def record_login(self, user_id: str) -> bool:
        async with async_session_factory() as session:
            result = await session.execute(select(RBACUser).where(RBACUser.id == user_id))
            db_user = result.scalar_one_or_none()
            if not db_user:
                return False
            db_user.last_login = utc_now()
            db_user.login_count = (db_user.login_count or 0) + 1
            await session.commit()
            return True

    async def ensure_operator_user(self) -> None:
        """Idempotently persist the synthetic operator principal as an RBACUser.

        The admission middleware authenticates the master API key as a
        SUPER_ADMIN principal named ``operator`` that has no DB row.  Before
        issuing an RBAC key for that principal we must materialize it, otherwise
        ``create_api_key`` rejects an unknown owner and any key tied to a
        missing user would never resolve through ``validate_api_key``.
        """
        async with async_session_factory() as session:
            existing = (
                await session.execute(
                    select(RBACUser).where(RBACUser.id == OPERATOR_USER_ID)
                )
            ).scalar_one_or_none()
            if existing is not None:
                return
            session.add(
                RBACUser(
                    id=OPERATOR_USER_ID,
                    email=OPERATOR_USER_EMAIL,
                    name="Operator",
                    role=Role.SUPER_ADMIN.value,
                    is_active=True,
                    permissions=[p.value for p in set(Permission)],
                    metadata_json={},
                )
            )
            await session.commit()
            logger.info("Auto-provisioned operator RBAC user")

    # ── Permission Checks ──────────────────────────────────

    def check_permission(self, user: User, permission: Permission) -> PermissionCheck:
        if not user.is_active:
            return PermissionCheck(
                allowed=False,
                reason="User account is inactive",
                role=user.role,
            )
        role_def = self._roles.get(user.role)
        if role_def and permission in role_def.permissions:
            return PermissionCheck(allowed=True, role=user.role)
        if permission in user.permissions:
            return PermissionCheck(allowed=True, role=user.role)
        return PermissionCheck(
            allowed=False,
            reason=f"Permission {permission.value} not granted",
            role=user.role,
            missing_permissions=[permission],
        )

    def check_permissions(self, user: User, permissions: Set[Permission]) -> PermissionCheck:
        missing = []
        for permission in permissions:
            result = self.check_permission(user, permission)
            if not result.allowed:
                missing.extend(result.missing_permissions)
        if missing:
            return PermissionCheck(
                allowed=False,
                reason=f"Missing {len(missing)} permissions",
                role=user.role,
                missing_permissions=missing,
            )
        return PermissionCheck(allowed=True, role=user.role)

    def get_user_permissions(self, user: User) -> Set[Permission]:
        permissions: Set[Permission] = set()
        role_def = self._roles.get(user.role)
        if role_def:
            permissions.update(role_def.permissions)
        permissions.update(user.permissions)
        return permissions

    # ── API Key Management (PostgreSQL) ────────────────────

    async def create_api_key(
        self,
        user_id: str,
        name: str,
        role: Role,
        expires_days: Optional[int] = 90,
        permissions: Optional[Set[Permission]] = None,
    ) -> APIKey:
        async with async_session_factory() as session:
            result = await session.execute(select(RBACUser).where(RBACUser.id == user_id))
            if not result.scalar_one_or_none():
                raise ValueError(f"User {user_id} not found")

            key_id = str(uuid.uuid4())
            raw_key = f"eops_{secrets.token_urlsafe(32)}"
            key_hash = _hash_api_key(raw_key)
            key_prefix = raw_key[:12] + "..."

            expires_at = None
            if expires_days:
                expires_at = utc_now() + timedelta(days=expires_days)

            db_key = RBACApiKey(
                id=key_id,
                key_hash=key_hash,
                key_hash_fast=_fast_hash_api_key(raw_key),
                key_prefix=key_prefix,
                name=name,
                user_id=user_id,
                role=role.value,
                permissions=[p.value for p in (permissions or set())],
                is_active=True,
                expires_at=expires_at,
            )
            session.add(db_key)
            await session.commit()

            logger.info("Created API key: %s for user %s", key_id, user_id)
            return APIKey(
                id=key_id,
                key=raw_key,
                name=name,
                user_id=user_id,
                role=role,
                permissions=permissions or set(),
                expires_at=expires_at,
            )

    async def validate_api_key(self, key: str) -> Optional[APIKey]:
        fast_hash = _fast_hash_api_key(key)
        async with async_session_factory() as session:
            # C10: O(1) lookup via sha256 fast hash pre-filter
            result = await session.execute(
                select(RBACApiKey).where(
                    RBACApiKey.is_active,
                    RBACApiKey.key_hash_fast == fast_hash,
                )
            )
            db_key = result.scalar_one_or_none()
            if db_key is None:
                return None
            if not _verify_api_key_hash(key, db_key.key_hash):
                return None
            if db_key.expires_at and utc_now() > db_key.expires_at:
                return None

            db_key.last_used = utc_now()
            db_key.usage_count = (db_key.usage_count or 0) + 1
            await session.commit()

            return APIKey(
                id=db_key.id,
                key=key,
                name=db_key.name,
                user_id=db_key.user_id,
                role=Role(db_key.role),
                permissions={Permission(p) for p in (db_key.permissions or [])},
                is_active=db_key.is_active,
                expires_at=db_key.expires_at,
                last_used=db_key.last_used,
                usage_count=db_key.usage_count,
            )

    async def rotate_api_key(self, key_id: str) -> Optional[APIKey]:
        """Rotate an API key: issue a replacement and revoke the old one.

        The returned APIKey carries the NEW raw key (shown to the caller once).
        Returns None if the key to rotate does not exist or is already inactive.
        """
        async with async_session_factory() as session:
            result = await session.execute(select(RBACApiKey).where(RBACApiKey.id == key_id))
            db_key = result.scalar_one_or_none()
            if not db_key or not db_key.is_active:
                return None
            if db_key.expires_at and utc_now() > db_key.expires_at:
                return None

            # Issue replacement first, then revoke the old one so there is
            # never a window with no valid credential.
            replacement = await self.create_api_key(
                user_id=db_key.user_id,
                name=db_key.name,
                role=Role(db_key.role),
                permissions={Permission(p) for p in (db_key.permissions or [])},
                expires_days=90,
            )
            db_key.is_active = False
            db_key.metadata_json = {**(db_key.metadata_json or {}), "rotated_from": True}
            await session.commit()
            logger.info(
                "Rotated API key %s -> %s for user %s", key_id, replacement.id, db_key.user_id
            )
            return replacement

    async def revoke_api_key(self, key_id: str) -> bool:
        async with async_session_factory() as session:
            result = await session.execute(select(RBACApiKey).where(RBACApiKey.id == key_id))
            db_key = result.scalar_one_or_none()
            if not db_key:
                return False
            db_key.is_active = False
            await session.commit()
            logger.info("Revoked API key: %s", key_id)
            return True

    async def list_api_keys(
        self,
        user_id: Optional[str] = None,
        is_active: Optional[bool] = None,
    ) -> List[APIKey]:
        async with async_session_factory() as session:
            stmt = select(RBACApiKey)
            if user_id:
                stmt = stmt.where(RBACApiKey.user_id == user_id)
            if is_active is not None:
                stmt = stmt.where(RBACApiKey.is_active == is_active)
            result = await session.execute(stmt.order_by(RBACApiKey.created_at.desc()))
            return [
                APIKey(
                    id=k.id,
                    key=k.key_prefix,
                    name=k.name,
                    user_id=k.user_id,
                    role=Role(k.role),
                    permissions={Permission(p) for p in (k.permissions or [])},
                    is_active=k.is_active,
                    expires_at=k.expires_at,
                    last_used=k.last_used,
                    usage_count=k.usage_count,
                )
                for k in result.scalars().all()
            ]

    # ── Initialization ─────────────────────────────────────

    async def create_default_admin(
        self,
        email: str = "admin@example.com",
        password: Optional[str] = None,
    ) -> User:
        existing = await self.get_user_by_email(email)
        if existing:
            return existing
        return await self.create_user(
            email=email,
            name="Admin",
            role=Role.SUPER_ADMIN,
            metadata={"is_default_admin": True},
        )

    # ── Helpers ────────────────────────────────────────────

    def _db_to_user(self, db_user: RBACUser) -> User:
        return User(
            id=db_user.id,
            email=db_user.email,
            name=db_user.name,
            role=Role(db_user.role),
            is_active=db_user.is_active,
            permissions={Permission(p) for p in (db_user.permissions or [])},
            metadata=db_user.metadata_json or {},
            created_at=db_user.created_at,
            last_login=db_user.last_login,
            login_count=db_user.login_count or 0,
        )


# Singleton
role_manager = RoleManager()
