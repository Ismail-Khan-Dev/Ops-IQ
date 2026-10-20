"""
Shopify OAuth 2.0 Handler
Handles app installation flow, token exchange, and shop authentication.
"""

import base64
import hashlib
import hmac
import logging
import secrets
import time
from typing import ClassVar, List, Optional
from urllib.parse import urlencode

import httpx
from pydantic import BaseModel

from ecommerce_ops.config import settings

logger = logging.getLogger("ecommerce_ops.connectors.shopify.oauth")


class OAuthSession(BaseModel):
    shop_domain: str
    access_token: str
    scope: str
    installed_at: float
    expires_at: Optional[float] = None


class ShopifyOAuth:
    """Shopify OAuth 2.0 implementation."""

    SCOPES: ClassVar[List[str]] = [
        "read_products",
        "write_products",
        "read_orders",
        "write_orders",
        "read_customers",
        "read_inventory",
        "write_inventory",
        "read_checkouts",
        "write_checkouts",
        "read_fulfillments",
        "write_fulfillments",
    ]

    def __init__(self):
        self.client_id = settings.SHOPIFY_CLIENT_ID
        self.client_secret = (
            settings.SHOPIFY_CLIENT_SECRET.get_secret_value()
            if settings.SHOPIFY_CLIENT_SECRET
            else None
        )
        self.app_url = settings.SHOPIFY_APP_URL
        self.api_version = settings.SHOPIFY_API_VERSION

    def get_install_url(self, shop_domain: str, state: Optional[str] = None) -> str:
        """Generate OAuth authorization URL for merchant to install app."""
        if not state:
            state = secrets.token_urlsafe(32)

        params = {
            "client_id": self.client_id,
            "scope": ",".join(self.SCOPES),
            "redirect_uri": f"{self.app_url}/api/shopify/callback",
            "state": state,
        }

        # Clean shop domain
        shop_domain = self._clean_shop_domain(shop_domain)
        url = f"https://{shop_domain}/admin/oauth/authorize?{urlencode(params)}"
        logger.info("Generated install URL for shop: %s", shop_domain)
        return url

    async def exchange_code(self, shop_domain: str, code: str) -> Optional[OAuthSession]:
        """Exchange authorization code for access token."""
        shop_domain = self._clean_shop_domain(shop_domain)

        async with httpx.AsyncClient(timeout=30) as client:
            try:
                response = await client.post(
                    f"https://{shop_domain}/admin/oauth/access_token",
                    json={
                        "client_id": self.client_id,
                        "client_secret": self.client_secret,
                        "code": code,
                    },
                    headers={"Content-Type": "application/json"},
                )
                response.raise_for_status()
                data = response.json()

                session = OAuthSession(
                    shop_domain=shop_domain,
                    access_token=data["access_token"],
                    scope=data.get("scope", ",".join(self.SCOPES)),
                    installed_at=time.time(),
                )

                logger.info("OAuth token exchanged for shop: %s", shop_domain)
                return session

            except httpx.HTTPStatusError as e:
                logger.error(
                    "OAuth token exchange failed for %s: %s", shop_domain, e.response.status_code
                )
                return None
            except Exception as e:
                logger.error("OAuth token exchange error for %s: %s", shop_domain, e)
                return None

    def verify_hmac(self, params: dict, hmac_signature: str) -> bool:
        """Verify HMAC signature from Shopify."""
        if not self.client_secret:
            logger.warning("Client secret not configured, skipping HMAC verification")
            return False

        # Remove hmac from params
        params_to_verify = {k: v for k, v in params.items() if k != "hmac"}

        # Sort and concatenate
        sorted_params = sorted(params_to_verify.items())
        query_string = "&".join(f"{k}={v}" for k, v in sorted_params)

        # Calculate HMAC
        calculated = hmac.new(
            self.client_secret.encode("utf-8"),
            query_string.encode("utf-8"),
            hashlib.sha256,
        ).hexdigest()

        return hmac.compare_digest(calculated, hmac_signature)

    def verify_webhook(self, body: bytes, hmac_header: str) -> bool:
        """Verify webhook HMAC signature.

        Shopify sends webhooks with an ``X-Shopify-Hmac-SHA256`` header whose
        value is the BASE64-encoded SHA-256 HMAC of the raw body, signed with
        the app client secret. (The OAuth ``hmac`` query param is hex-encoded
        and handled separately in ``verify_hmac``.)
        """
        if not self.client_secret:
            logger.warning("Client secret not configured, skipping webhook verification")
            return False
        if not hmac_header:
            logger.warning("Missing X-Shopify-Hmac-SHA256 header")
            return False

        calculated = hmac.new(
            self.client_secret.encode("utf-8"),
            body,
            hashlib.sha256,
        ).digest()
        computed_b64 = base64.b64encode(calculated).decode("utf-8")

        return hmac.compare_digest(computed_b64, hmac_header)

    def _clean_shop_domain(self, shop_domain: str) -> str:
        """Clean and validate shop domain."""
        # Remove protocol
        shop_domain = shop_domain.replace("https://", "").replace("http://", "")
        # Remove trailing slash
        shop_domain = shop_domain.rstrip("/")
        # Remove /admin suffix
        if shop_domain.endswith("/admin"):
            shop_domain = shop_domain[:-6]
        # Add .myshopify.com if missing
        if ".myshopify.com" not in shop_domain:
            shop_domain = f"{shop_domain}.myshopify.com"
        return shop_domain


# Singleton
shopify_oauth = ShopifyOAuth()
