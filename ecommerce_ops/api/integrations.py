"""
Integrations API Routes
Outbound webhook management (custom HTTPS endpoints).
"""

import logging
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field, field_validator
from sqlalchemy import select

from ecommerce_ops.infra.outbound_webhooks import send_test_webhook
from ecommerce_ops.models import OutboundWebhook, get_db_session
from ecommerce_ops.security.audit import audit_logger
from ecommerce_ops.security.auth import require_permission
from ecommerce_ops.security.models import Permission, SecurityEvent, User
from ecommerce_ops.utils import utc_now

logger = logging.getLogger("ecommerce_ops.api.integrations")

router = APIRouter(prefix="/integrations", tags=["integrations"])

WILDCARD_EVENT = "*"
KNOWN_EVENTS = {
    "hitl_request",
    "pipeline_failed",
    "execution_failed",
    "agent_graduated",
    "daily_summary",
    "test",
}


class WebhookCreateRequest(BaseModel):
    name: str = Field(..., min_length=1, max_length=120)
    url: str = Field(..., description="HTTPS endpoint that receives the events")
    events: List[str] = Field(
        ..., description='Event types; use ["*"] to receive every event'
    )
    secret: Optional[str] = Field(
        None, max_length=256, description="HMAC signing secret (sent as X-Ecom-Ops-Signature)"
    )
    enabled: bool = True

    @field_validator("url")
    @classmethod
    def _url_must_be_https(cls, v: str) -> str:
        v = v.strip()
        if not v.startswith("https://"):
            raise ValueError("Outbound webhook URL must use https://")
        return v

    @field_validator("events")
    @classmethod
    def _validate_events(cls, v: List[str]) -> List[str]:
        if not v:
            raise ValueError("At least one event type is required")
        normalized = []
        for e in v:
            if e == WILDCARD_EVENT:
                return [WILDCARD_EVENT]
            if e not in KNOWN_EVENTS:
                raise ValueError(f"Unknown event type: {e}")
            normalized.append(e)
        return sorted(set(normalized))


class WebhookUpdateRequest(BaseModel):
    name: Optional[str] = Field(None, min_length=1, max_length=120)
    url: Optional[str] = None
    events: Optional[List[str]] = None
    secret: Optional[str] = Field(None, max_length=256)
    enabled: Optional[bool] = None

    @field_validator("url")
    @classmethod
    def _url_must_be_https(cls, v: Optional[str]) -> Optional[str]:
        if v is None:
            return v
        v = v.strip()
        if not v.startswith("https://"):
            raise ValueError("Outbound webhook URL must use https://")
        return v

    @field_validator("events")
    @classmethod
    def _validate_events(cls, v: Optional[List[str]]) -> Optional[List[str]]:
        if v is None:
            return v
        if not v:
            raise ValueError("At least one event type is required")
        normalized = []
        for e in v:
            if e == WILDCARD_EVENT:
                return [WILDCARD_EVENT]
            if e not in KNOWN_EVENTS:
                raise ValueError(f"Unknown event type: {e}")
            normalized.append(e)
        return sorted(set(normalized))


class WebhookResponse(BaseModel):
    id: int
    name: str
    url: str
    events: List[str]
    enabled: bool
    created_at: str

    @classmethod
    def from_model(cls, h: OutboundWebhook) -> "WebhookResponse":
        return cls(
            id=h.id,
            name=h.name,
            url=h.url,
            events=h.events,
            enabled=h.enabled,
            created_at=h.created_at.isoformat() if h.created_at else "",
        )


def _serialize(h: OutboundWebhook) -> dict:
    return {
        "id": h.id,
        "name": h.name,
        "url": h.url,
        "events": h.events,
        "enabled": h.enabled,
        "created_at": h.created_at.isoformat() if h.created_at else "",
    }


async def _get_webhook_or_404(webhook_id: int, session):
    res = await session.execute(select(OutboundWebhook).where(OutboundWebhook.id == webhook_id))
    hook = res.scalar_one_or_none()
    if hook is None:
        raise HTTPException(status_code=404, detail="Webhook not found")
    return hook


@router.get("/webhooks")
async def list_webhooks(
    _: User = Depends(require_permission(Permission.INTEGRATIONS_MANAGE)),
    db=Depends(get_db_session),
):
    """List all outbound webhook destinations."""
    res = await db.execute(select(OutboundWebhook).order_by(OutboundWebhook.id))
    return {"webhooks": [_serialize(h) for h in res.scalars().all()]}


@router.post("/webhooks", status_code=201)
async def create_webhook(
    req: WebhookCreateRequest,
    admin: User = Depends(require_permission(Permission.INTEGRATIONS_MANAGE)),
    db=Depends(get_db_session),
):
    """Register a new outbound webhook destination."""
    existing = await db.execute(
        select(OutboundWebhook).where(OutboundWebhook.name == req.name)
    )
    if existing.scalar_one_or_none() is not None:
        raise HTTPException(status_code=409, detail="A webhook with this name already exists")

    hook = OutboundWebhook(
        name=req.name.strip(),
        url=req.url.strip(),
        events=req.events,
        secret=req.secret,
        enabled=req.enabled,
    )
    db.add(hook)
    await db.commit()
    await db.refresh(hook)

    audit_logger.log_event(
        SecurityEvent(
            event_type="integrations",
            action="create_outbound_webhook",
            resource="outbound_webhook",
            resource_id=str(hook.id),
            user_id=admin.id,
            success=True,
            details={"name": hook.name, "url": hook.url},
        )
    )

    return _serialize(hook)


@router.patch("/webhooks/{webhook_id}")
async def update_webhook(
    webhook_id: int,
    req: WebhookUpdateRequest,
    admin: User = Depends(require_permission(Permission.INTEGRATIONS_MANAGE)),
    db=Depends(get_db_session),
):
    """Update a webhook destination (disabled webhooks stop receiving events)."""
    hook = await _get_webhook_or_404(webhook_id, db)

    if req.name is not None:
        existing = await db.execute(
            select(OutboundWebhook).where(
                OutboundWebhook.name == req.name.strip(),
                OutboundWebhook.id != webhook_id,
            )
        )
        if existing.scalar_one_or_none() is not None:
            raise HTTPException(status_code=409, detail="A webhook with this name already exists")
        hook.name = req.name.strip()
    if req.url is not None:
        hook.url = req.url.strip()
    if req.events is not None:
        hook.events = req.events
    if req.secret is not None:
        hook.secret = req.secret or None
    if req.enabled is not None:
        hook.enabled = req.enabled
    hook.updated_at = utc_now()
    await db.commit()
    await db.refresh(hook)

    audit_logger.log_event(
        SecurityEvent(
            event_type="integrations",
            action="update_outbound_webhook",
            resource="outbound_webhook",
            resource_id=str(hook.id),
            user_id=admin.id,
            success=True,
            details={"name": hook.name, "enabled": hook.enabled},
        )
    )

    return _serialize(hook)


@router.delete("/webhooks/{webhook_id}")
async def delete_webhook(
    webhook_id: int,
    admin: User = Depends(require_permission(Permission.INTEGRATIONS_MANAGE)),
    db=Depends(get_db_session),
):
    """Permanently remove a webhook destination."""
    hook = await _get_webhook_or_404(webhook_id, db)
    await db.delete(hook)
    await db.commit()

    audit_logger.log_event(
        SecurityEvent(
            event_type="integrations",
            action="delete_outbound_webhook",
            resource="outbound_webhook",
            resource_id=str(webhook_id),
            user_id=admin.id,
            success=True,
        )
    )

    return {"status": "deleted", "id": webhook_id}


@router.post("/webhooks/{webhook_id}/test")
async def test_webhook(
    webhook_id: int,
    admin: User = Depends(require_permission(Permission.INTEGRATIONS_MANAGE)),
    db=Depends(get_db_session),
):
    """Send a synthetic test event to a webhook to verify connectivity."""
    await _get_webhook_or_404(webhook_id, db)
    delivered = await send_test_webhook(webhook_id)

    audit_logger.log_event(
        SecurityEvent(
            event_type="integrations",
            action="test_outbound_webhook",
            resource="outbound_webhook",
            resource_id=str(webhook_id),
            user_id=admin.id,
            success=delivered,
        )
    )

    if not delivered:
        raise HTTPException(status_code=502, detail="Test delivery failed")
    return {"status": "delivered", "id": webhook_id}


# ── Ecosystem Bridges (Klaviyo & Gorgias) ──────────────────


class KlaviyoTestRequest(BaseModel):
    customer_email: str = "test.shopper@example.com"
    cart_id: str = "cart_test_101"
    cart_total: float = 89.99
    discount_code: str = "OPSIQ-TEST"


class GorgiasTestRequest(BaseModel):
    ticket_id: Optional[str] = None
    customer_email: Optional[str] = "support.customer@example.com"
    subject: str = "Test Inquiry"
    message: str = "OpsIQ AI draft recommendation test message"


@router.get("/ecosystem-status")
async def get_ecosystem_status(
    _: User = Depends(require_permission(Permission.INTEGRATIONS_MANAGE)),
):
    """Check connectivity and configuration status for Klaviyo, Gorgias, and Slack."""
    from ecommerce_ops.config import settings as app_settings

    return {
        "klaviyo": {
            "configured": bool(app_settings.KLAVIYO_API_KEY),
            "company_id": app_settings.KLAVIYO_COMPANY_ID,
        },
        "gorgias": {
            "configured": bool(
                app_settings.GORGIAS_DOMAIN
                and app_settings.GORGIAS_EMAIL
                and app_settings.GORGIAS_API_KEY
            ),
            "domain": app_settings.GORGIAS_DOMAIN,
            "email": app_settings.GORGIAS_EMAIL,
        },
        "slack": {
            "configured": bool(
                app_settings.SLACK_WEBHOOK_URL or app_settings.SLACK_BOT_TOKEN
            ),
            "channel": app_settings.SLACK_CHANNEL or "#general",
            "has_signing_secret": bool(app_settings.SLACK_SIGNING_SECRET),
        },
    }


@router.post("/klaviyo/test")
async def test_klaviyo_event_bridge(
    req: KlaviyoTestRequest = KlaviyoTestRequest(),
    _: User = Depends(require_permission(Permission.INTEGRATIONS_MANAGE)),
):
    """Test tracking an event in Klaviyo via the Event Bridge."""
    from ecommerce_ops.connectors.klaviyo import KlaviyoClient

    client = KlaviyoClient()
    try:
        res = await client.trigger_cart_recovery(
            customer_email=req.customer_email,
            cart_id=req.cart_id,
            cart_total=req.cart_total,
            discount_code=req.discount_code,
        )
        return {
            "status": "success",
            "klaviyo_configured": client.is_configured,
            "response": res,
        }
    finally:
        await client.close()


@router.post("/gorgias/test")
async def test_gorgias_bridge(
    req: GorgiasTestRequest = GorgiasTestRequest(),
    _: User = Depends(require_permission(Permission.INTEGRATIONS_MANAGE)),
):
    """Test creating a ticket or adding an internal note in Gorgias."""
    from ecommerce_ops.connectors.gorgias import GorgiasClient

    client = GorgiasClient()
    try:
        if req.ticket_id:
            res = await client.add_internal_note(req.ticket_id, req.message)
            action_done = "internal_note_added"
        else:
            res = await client.create_ticket(
                customer_email=req.customer_email or "test@example.com",
                subject=req.subject,
                message_body=req.message,
            )
            action_done = "ticket_created"

        return {
            "status": "success",
            "action": action_done,
            "gorgias_configured": client.is_configured,
            "response": res,
        }
    finally:
        await client.close()
