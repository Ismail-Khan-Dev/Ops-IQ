"""
Shopify API Routes
OAuth flow, webhooks, and sync endpoints.
"""

import logging
from typing import Optional

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query, Request
from pydantic import BaseModel
from sqlalchemy import select

from ecommerce_ops.connectors.shopify.client import ShopifyClient
from ecommerce_ops.connectors.shopify.handlers.order_handlers import WEBHOOK_HANDLERS
from ecommerce_ops.connectors.shopify.oauth import shopify_oauth
from ecommerce_ops.connectors.shopify.oauth_state import oauth_state_store
from ecommerce_ops.connectors.shopify.sync import ShopifySyncService
from ecommerce_ops.connectors.shopify.webhooks import webhook_router
from ecommerce_ops.models import ShopifyShopCredential, async_session_factory
from ecommerce_ops.security.auth import require_permission
from ecommerce_ops.security.models import Permission, User
from ecommerce_ops.utils import utc_now

logger = logging.getLogger("ecommerce_ops.api.shopify")

router = APIRouter(prefix="/shopify", tags=["shopify"])


class InstallRequest(BaseModel):
    shop_domain: str


class WebhookPayload(BaseModel):
    topic: str
    shop_domain: str
    body: dict


class SyncResponse(BaseModel):
    status: str
    products_synced: int = 0
    orders_synced: int = 0
    customers_synced: int = 0
    duration_seconds: float = 0.0
    errors: list = []


# ── OAuth Flow ─────────────────────────────────────────────


@router.post("/install")
async def install_shopify(
    req: InstallRequest,
    _: User = Depends(require_permission(Permission.SHOPIFY_CONFIGURE)),
):
    """Start Shopify OAuth installation flow."""
    state = await oauth_state_store.create(req.shop_domain)

    url = shopify_oauth.get_install_url(req.shop_domain, state)
    logger.info("Generated install URL for %s", req.shop_domain)
    return {"url": url, "state": state}


@router.get("/callback")
async def oauth_callback(
    code: str = Query(...),
    hmac: str = Query(...),
    shop: str = Query(...),
    state: str = Query(...),
    timestamp: str = Query(...),
):
    """Handle OAuth callback from Shopify."""
    # Verify and consume single-use state token (bound to shop)
    bound_shop: str | None = await oauth_state_store.consume(state)
    if bound_shop is None:
        raise HTTPException(status_code=400, detail="Invalid or expired state")
    if bound_shop != shop:
        raise HTTPException(status_code=400, detail="State does not match shop")

    # Verify HMAC
    params = {
        "code": code,
        "hmac": hmac,
        "shop": shop,
        "state": state,
        "timestamp": timestamp,
    }
    if not shopify_oauth.verify_hmac(params, hmac):
        raise HTTPException(status_code=401, detail="Invalid HMAC signature")

    # Exchange code for token
    session = await shopify_oauth.exchange_code(shop, code)
    if not session:
        raise HTTPException(status_code=500, detail="Token exchange failed")

    # C9: Persist OAuth token in database
    async with async_session_factory() as db_session:
        existing = await db_session.execute(
            select(ShopifyShopCredential).where(
                ShopifyShopCredential.shop_domain == session.shop_domain
            )
        )
        cred = existing.scalar_one_or_none()
        if cred:
            cred.access_token = session.access_token
            cred.scope = session.scope
            cred.updated_at = utc_now()
            cred.is_active = True
        else:
            db_session.add(
                ShopifyShopCredential(
                    shop_domain=session.shop_domain,
                    access_token=session.access_token,
                    scope=session.scope,
                    installed_at=utc_now(),
                    is_active=True,
                )
            )
        await db_session.commit()

    logger.info(
        "Shopify app installed: shop=%s, scope=%s",
        session.shop_domain,
        session.scope,
    )

    # Register webhook handlers
    webhook_router.register_many(WEBHOOK_HANDLERS)

    # Redirect to app dashboard
    return {
        "status": "success",
        "shop_domain": session.shop_domain,
        "message": "Shopify app installed successfully",
    }


# ── Webhooks ───────────────────────────────────────────────


@router.post("/webhooks/{topic:path}")
async def shopify_webhook(
    topic: str,
    request: Request,
):
    """Handle incoming Shopify webhooks with HMAC verification."""
    body = await request.body()
    headers = dict(request.headers)

    # Extract shop domain from headers
    shop_domain = headers.get("x-shopify-shop-domain", "unknown")

    logger.info("Received webhook: topic=%s shop=%s", topic, shop_domain)

    # Process synchronously to validate HMAC before responding
    result = await webhook_router.handle_webhook(
        topic=topic,
        shop_domain=shop_domain,
        body=body,
        headers=headers,
    )

    if result.get("status") == "unauthorized":
        logger.warning("Webhook HMAC verification failed: topic=%s shop=%s", topic, shop_domain)
        raise HTTPException(status_code=401, detail="Invalid webhook signature")

    if result.get("status") == "parse_error":
        logger.error("Webhook parse error: topic=%s shop=%s", topic, shop_domain)
        raise HTTPException(status_code=400, detail="Invalid webhook payload")

    return {"status": "received", "topic": topic, "result": result}


# ── Sync ───────────────────────────────────────────────────


@router.post("/sync", response_model=SyncResponse)
async def sync_shopify_data(
    background_tasks: BackgroundTasks,
    full: bool = Query(False, description="Full sync or incremental"),
    shop_domain: Optional[str] = Query(
        None, description="Scope sync to an OAuth-installed store"
    ),
    _: User = Depends(require_permission(Permission.SHOPIFY_SYNC)),
):
    """Trigger data synchronization from Shopify."""
    from ecommerce_ops.config import settings as app_settings
    from ecommerce_ops.pipeline.runner import _resolve_shop_credentials

    resolved_domain, resolved_token = await _resolve_shop_credentials(shop_domain)
    if shop_domain and resolved_domain is None:
        raise HTTPException(
            status_code=400,
            detail=f"No active credential for shop {shop_domain}",
        )

    shop_domain = resolved_domain or app_settings.SHOPIFY_SHOP_DOMAIN
    access_token = resolved_token or (
        app_settings.SHOPIFY_ACCESS_TOKEN.get_secret_value()
        if app_settings.SHOPIFY_ACCESS_TOKEN
        else None
    )

    if not shop_domain or not access_token:
        raise HTTPException(
            status_code=400,
            detail="Shopify credentials not configured",
        )

    client = ShopifyClient(
        shop_domain=shop_domain,
        access_token=access_token,
        api_version=app_settings.SHOPIFY_API_VERSION,
    )

    sync_service = ShopifySyncService(client)

    async with async_session_factory() as session:
        result = await sync_service.full_sync(session)

    await client.close()

    return SyncResponse(
        status="completed",
        **result.to_dict(),
    )


# ── Status ─────────────────────────────────────────────────


@router.get("/status")
async def shopify_status(
    _: User = Depends(require_permission(Permission.SHOPIFY_VIEW)),
):
    """Check Shopify integration status."""
    from ecommerce_ops.config import settings as app_settings

    configured = bool(app_settings.SHOPIFY_SHOP_DOMAIN and app_settings.SHOPIFY_ACCESS_TOKEN)

    return {
        "configured": configured,
        "shop_domain": app_settings.SHOPIFY_SHOP_DOMAIN if configured else None,
        "api_version": app_settings.SHOPIFY_API_VERSION,
        "webhook_topics": webhook_router.get_supported_topics(),
    }


# ── Products ───────────────────────────────────────────────


@router.get("/products")
async def list_shopify_products(
    _: User = Depends(require_permission(Permission.SHOPIFY_VIEW)),
    limit: int = Query(50, ge=1, le=250),
):
    """List products from Shopify."""
    from ecommerce_ops.config import settings as app_settings

    if not app_settings.SHOPIFY_SHOP_DOMAIN or not app_settings.SHOPIFY_ACCESS_TOKEN:
        raise HTTPException(status_code=400, detail="Shopify not configured")

    access_token = app_settings.SHOPIFY_ACCESS_TOKEN.get_secret_value()

    client = ShopifyClient(
        shop_domain=app_settings.SHOPIFY_SHOP_DOMAIN,
        access_token=access_token,
        api_version=app_settings.SHOPIFY_API_VERSION,
    )

    try:
        response = await client.get_products(limit=limit)
        return response
    finally:
        await client.close()


# ── Orders ─────────────────────────────────────────────────


@router.get("/orders")
async def list_shopify_orders(
    _: User = Depends(require_permission(Permission.SHOPIFY_VIEW)),
    status: str = Query("any"),
    limit: int = Query(50, ge=1, le=250),
):
    """List orders from Shopify."""
    from ecommerce_ops.config import settings as app_settings

    if not app_settings.SHOPIFY_SHOP_DOMAIN or not app_settings.SHOPIFY_ACCESS_TOKEN:
        raise HTTPException(status_code=400, detail="Shopify not configured")

    access_token = app_settings.SHOPIFY_ACCESS_TOKEN.get_secret_value()

    client = ShopifyClient(
        shop_domain=app_settings.SHOPIFY_SHOP_DOMAIN,
        access_token=access_token,
        api_version=app_settings.SHOPIFY_API_VERSION,
    )

    try:
        response = await client.get_orders(status=status, limit=limit)
        return response
    finally:
        await client.close()
