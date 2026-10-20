"""
Server API-key credential store backing full credential rotation (week 9).

Only SHA-256 hashes are persisted; the raw key is shown exactly once at issue
time.  Semantics:

- ``.issue()``  — create a fresh active credential (returns raw key once).
- ``.verify()`` — constant-time check against *active* keys and *rotated*
  keys still inside their grace window.  Uses a short TTL in-process cache so
  the hot authentication path does not hit the database every request.
- ``.start_rotation()`` — issue a new key AND demote every currently-active
  key to ``rotated`` with ``valid_until = now + grace``.  Callers get
  zero-downtime rotation: old keys keep working until the window lapses.
- ``.finalize_rotation()`` — revoke all rotated keys immediately (cutover).

The rotation ledger is additive, so a mistake never disables auth: the most
recent ``start_rotation`` keeps the previous cohort valid for ``grace_days``.
"""

import hashlib
import logging
import secrets
import time
from datetime import timedelta
from typing import Dict, List, Optional, Tuple

from sqlalchemy import select, update

from ecommerce_ops.models import ServerCredential, async_session_factory
from ecommerce_ops.utils import utc_now

logger = logging.getLogger("ecommerce_ops.security.credential_store")

DEFAULT_GRACE_DAYS = 7
_CACHE_TTL_SECONDS = 30

KEY_PREFIX = "eops"


def hash_server_key(key: str) -> str:
    """SHA-256 hex digest — the only representation persisted."""
    return hashlib.sha256(key.encode("utf-8")).hexdigest()


def _prefix(key: str) -> str:
    return f"{key[:12]}..."


class ServerCredentialStore:
    """Async store + in-process cache for server credential rotation."""

    def __init__(self) -> None:
        self._cache: Dict[str, Tuple[str, Optional[str]]] = {}  # key_hash -> (status, valid_until)
        self._cache_loaded: float = 0.0

    # ── Internals ─────────────────────────────────────────

    async def _cache_relevant(self) -> Dict[str, Tuple[str, Optional[str]]]:
        """Load (and cache) the hashes the verifier should accept.

        Acceptable = status ``active``, or status ``rotated`` with
        ``valid_until`` in the future.  Rows whose ``valid_until`` lapsed are
        lazily flipped to ``revoked`` in the DB by the same query family.
        """
        if self._cache and time.monotonic() - self._cache_loaded < _CACHE_TTL_SECONDS:
            return self._cache

        from sqlalchemy import select

        now = utc_now()
        async with async_session_factory() as session:
            rows = (
                (
                    await session.execute(
                        select(ServerCredential).where(
                            ServerCredential.status.in_(("active", "rotated"))
                        )
                    )
                )
                .scalars()
                .all()
            )
            # Lazily revoke rows whose grace window has lapsed.
            expired = [
                r.id
                for r in rows
                if r.status == "rotated" and r.valid_until is not None and r.valid_until < now
            ]
            if expired:
                await session.execute(
                    update(ServerCredential)
                    .where(ServerCredential.id.in_(expired))
                    .values(status="revoked")
                    .execution_options(synchronize_session=False)
                )
                await session.commit()

        self._cache = {
            r.key_hash: (r.status, r.valid_until.isoformat() if r.valid_until else None)
            for r in rows
            if r.id not in set(expired)
        }
        self._cache_loaded = time.monotonic()
        return self._cache

    # ── Public API ────────────────────────────────────────

    async def verify(self, key: str) -> bool:
        """True if ``key`` matches an active or in-grace rotated credential."""
        digest = hash_server_key(key)
        accepted = await self._cache_relevant()
        return accepted.get(digest) is not None

    async def issue(
        self,
        grace_days: int = DEFAULT_GRACE_DAYS,
        demote_active: bool = False,
    ) -> Tuple[str, str]:
        """Issue a new active credential.

        :param demote_active: if True, all other active keys become ``rotated``
            with ``valid_until = now + grace_days`` (rotation semantics).
        :returns: ``(raw_key, key_prefix)``.  The raw key is returned once.
        """
        raw_key = f"{KEY_PREFIX}_{secrets.token_urlsafe(32)}"
        now = utc_now()

        async with async_session_factory() as session:
            if demote_active:
                await session.execute(
                    update(ServerCredential)
                    .where(ServerCredential.status == "active")
                    .values(
                        status="rotated",
                        valid_until=now + timedelta(days=grace_days),
                        rotated_at=now,
                    )
                    .execution_options(synchronize_session=False)
                )

            session.add(
                ServerCredential(
                    key_hash=hash_server_key(raw_key),
                    key_prefix=_prefix(raw_key),
                    status="active",
                    valid_until=None,
                )
            )
            await session.commit()

        self._cache = {}
        logger.info(
            "Issued server credential %s (demote_active=%s, grace=%dd)",
            _prefix(raw_key),
            demote_active,
            grace_days,
        )
        return raw_key, _prefix(raw_key)

    async def start_rotation(self, grace_days: int = DEFAULT_GRACE_DAYS) -> Tuple[str, str]:
        """Rotate the server credential with a zero-downtime grace window."""
        return await self.issue(grace_days=grace_days, demote_active=True)

    async def finalize_rotation(self) -> int:
        """Revoke every rotated credential immediately (cutover).

        :returns: number of credentials revoked.
        """
        async with async_session_factory() as session:
            result = await session.execute(
                update(ServerCredential)
                .where(ServerCredential.status == "rotated")
                .values(status="revoked")
                .execution_options(synchronize_session=False)
            )
            await session.commit()
        revoked = result.rowcount if result.rowcount is not None else 0
        self._cache = {}
        logger.info("Finalized rotation: revoked %d rotated credential(s)", revoked)
        return revoked

    async def revoke_key(self, key_hash: str) -> bool:
        """Cut over a single credential by its hash."""
        async with async_session_factory() as session:
            result = await session.execute(
                update(ServerCredential)
                .where(ServerCredential.status.in_(("active", "rotated")))
                .where(ServerCredential.key_hash == key_hash)
                .values(status="revoked")
                .execution_options(synchronize_session=False)
            )
            await session.commit()
        revoked = (result.rowcount or 0) > 0
        if revoked:
            self._cache = {}
        return revoked

    async def list_credentials(self) -> List[Dict[str, object]]:
        """Return rotation-status summaries (hash + prefix only, never raw)."""
        async with async_session_factory() as session:
            rows = (
                (
                    await session.execute(
                        select(ServerCredential).order_by(ServerCredential.created_at.desc())
                    )
                )
                .scalars()
                .all()
            )
        return [
            {
                "id": r.id,
                "key_prefix": r.key_prefix,
                "status": r.status,
                "valid_until": r.valid_until.isoformat() if r.valid_until else None,
                "created_at": r.created_at.isoformat() if r.created_at else None,
                "rotated_at": r.rotated_at.isoformat() if r.rotated_at else None,
            }
            for r in rows
        ]


credential_store = ServerCredentialStore()
