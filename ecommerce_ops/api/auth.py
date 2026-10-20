import hmac
import logging

from fastapi import HTTPException, Request

from ecommerce_ops.config import Environment, settings
from ecommerce_ops.security.credential_store import credential_store

logger = logging.getLogger("ecommerce_ops.api.auth")


async def verify_auth(request: Request) -> str:
    api_key_setting = settings.API_KEY
    auth_header = request.headers.get("Authorization", "")
    scheme, _, token = auth_header.partition(" ")

    if api_key_setting or settings.ENV == Environment.PRODUCTION:
        if scheme.lower() != "bearer" or not token:
            raise HTTPException(
                status_code=401,
                detail="Missing or invalid API key. Use: Bearer <api-key>",
            )

        # Fast path: the bootstrap env key.
        if api_key_setting and hmac.compare_digest(token, api_key_setting.get_secret_value()):
            operator = request.headers.get("X-Operator-Id", "api-operator")
            return operator

        # Rotation path: accept the active / in-grace credential cohort from
        # the rotation ledger (see ecommerce_ops.security.credential_store).
        try:
            if await credential_store.verify(token):
                operator = request.headers.get("X-Operator-Id", "api-operator")
                return operator
        except Exception:  # pragma: no cover - DB down must not crash hot path
            logger.exception("Credential store verification failed; denying request")

        raise HTTPException(
            status_code=401,
            detail="Missing or invalid API key. Use: Bearer <api-key>",
        )

    if settings.ENV != Environment.PRODUCTION:
        return "development-operator"

    raise HTTPException(status_code=500, detail="API_KEY not configured on server")


async def verify_auth_optional(request: Request) -> str:
    try:
        return await verify_auth(request)
    except HTTPException:
        return "anonymous"
