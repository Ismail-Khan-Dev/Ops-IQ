"""
Shopify App Bridge v4 Session Token & Iframe Embedding Module
Provides JWT Session Token verification and Content Security Policy (CSP)
headers required for 'Built for Shopify' embedded app certification.
"""

import hashlib
import hmac
import json
import logging
import time
from typing import Any, Dict, Optional

from fastapi import HTTPException, Request, Response
from starlette.middleware.base import BaseHTTPMiddleware

from ecommerce_ops.config import Environment
from ecommerce_ops.config import settings as app_settings

logger = logging.getLogger("ecommerce_ops.connectors.shopify.app_bridge")


def _base64url_decode(input_str: str) -> bytes:
    """Decode base64url-encoded string (RFC 7515)."""
    import base64

    rem = len(input_str) % 4
    if rem > 0:
        input_str += "=" * (4 - rem)
    return base64.urlsafe_b64decode(input_str)


def verify_shopify_session_token(
    token: str,
    api_secret: Optional[str] = None,
    api_key: Optional[str] = None,
) -> Dict[str, Any]:
    """Verify Shopify App Bridge Session Token (JWT).

    Validates signature via HMAC-SHA256, expiration, and audience.
    Returns the decoded token claims containing shop and user identity.
    """
    if not api_secret and app_settings.SHOPIFY_API_SECRET:
        api_secret = app_settings.SHOPIFY_API_SECRET.get_secret_value()
    if not api_key:
        api_key = app_settings.SHOPIFY_API_KEY

    parts = token.strip().split(".")
    if len(parts) != 3:
        raise HTTPException(status_code=401, detail="Malformed session token structure")

    header_b64, payload_b64, signature_b64 = parts

    # In development/test mode without secret configured, decode payload safely
    if not api_secret:
        if app_settings.ENV != Environment.PRODUCTION:
            try:
                payload_json = json.loads(_base64url_decode(payload_b64).decode("utf-8"))
                return payload_json
            except Exception:
                raise HTTPException(status_code=401, detail="Invalid token encoding")
        raise HTTPException(status_code=500, detail="SHOPIFY_API_SECRET required for token verification")

    # 1. Verify HMAC-SHA256 Signature
    signing_input = f"{header_b64}.{payload_b64}".encode("utf-8")
    expected_sig = hmac.new(api_secret.encode("utf-8"), signing_input, hashlib.sha256).digest()
    actual_sig = _base64url_decode(signature_b64)

    if not hmac.compare_digest(expected_sig, actual_sig):
        raise HTTPException(status_code=401, detail="Invalid session token signature")

    # 2. Parse and validate claims
    try:
        claims = json.loads(_base64url_decode(payload_b64).decode("utf-8"))
    except Exception:
        raise HTTPException(status_code=401, detail="Invalid session token claims JSON")

    # 3. Check expiration
    exp = claims.get("exp")
    now = time.time()
    if exp and now > exp:
        raise HTTPException(status_code=401, detail="Session token expired")

    # 4. Check audience matches API Key if set
    aud = claims.get("aud")
    if api_key and aud and aud != api_key:
        raise HTTPException(status_code=401, detail="Session token audience mismatch")

    return claims


def extract_shop_from_session_token(token: str) -> Optional[str]:
    """Extract shop domain from dest claim (e.g. 'https://brand.myshopify.com' -> 'brand.myshopify.com')."""
    try:
        claims = verify_shopify_session_token(token)
        dest = claims.get("dest") or claims.get("iss") or ""
        return dest.replace("https://", "").replace("http://", "").replace("/admin", "").strip()
    except Exception:
        return None


class ShopifyAppBridgeMiddleware(BaseHTTPMiddleware):
    """Enforces Content Security Policy (CSP) frame-ancestors for Shopify embedded apps."""

    async def dispatch(self, request: Request, call_next):
        response: Response = await call_next(request)

        # Extract shop from query params or headers for dynamic CSP
        shop = request.query_params.get("shop")
        if not shop:
            shop_header = request.headers.get("X-Shopify-Shop-Domain")
            if shop_header:
                shop = shop_header.strip()

        # Build frame-ancestors directive
        ancestors = ["https://admin.shopify.com"]
        if shop:
            sanitized_shop = shop.replace("https://", "").replace("http://", "").rstrip("/")
            if not sanitized_shop.endswith(".myshopify.com"):
                sanitized_shop = f"{sanitized_shop}.myshopify.com"
            ancestors.append(f"https://{sanitized_shop}")

        ancestors_str = " ".join(ancestors)
        response.headers["Content-Security-Policy"] = (
            f"frame-ancestors {ancestors_str};"
        )
        return response
