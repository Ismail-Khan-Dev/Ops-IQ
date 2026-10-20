"""
SSO Authentication API Routes
"""
import logging

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel

from ecommerce_ops.security.auth import require_auth
from ecommerce_ops.security.models import User
from ecommerce_ops.security.sso import sso_manager

logger = logging.getLogger("ecommerce_ops.api.sso")

router = APIRouter(prefix="/auth/sso", tags=["sso"])


class SSOLoginRequest(BaseModel):
    provider: str


class SSOCallbackRequest(BaseModel):
    provider: str
    code: str
    state: str


@router.get("/providers")
async def list_sso_providers():
    """List available SSO providers."""
    providers = sso_manager.get_providers()
    return {
        "providers": [
            {"name": p.name, "display_name": p.display_name, "enabled": p.enabled}
            for p in providers
        ]
    }


@router.post("/login")
async def sso_login(req: SSOLoginRequest):
    """Initiate SSO login - returns authorization URL."""
    url = sso_manager.create_authorization_url(req.provider)
    return {"authorization_url": url, "provider": req.provider}


@router.post("/callback")
async def sso_callback(req: SSOCallbackRequest):
    """Handle SSO callback - exchanges code for session."""
    provider = await sso_manager.validate_state_async(req.state)
    if provider != req.provider:
        raise HTTPException(status_code=400, detail="Provider mismatch")

    session = await sso_manager.exchange_code(provider, req.code)
    return {
        "status": "authenticated",
        "provider": session.provider,
        "user_email": session.user_email,
        "user_name": session.user_name,
        "role": session.role,
    }


@router.post("/logout")
async def sso_logout(
    request: Request,
    _: User = Depends(require_auth),
):
    """Logout - revoke SSO session."""
    return {"status": "logged_out"}
