"""Outbound webhook delivery (custom HTTPS endpoints).

Events emitted by the system (HITL requests, pipeline failures, agent
graduations, daily summaries, …) are fanned out to every enabled webhook whose
``events`` list matches.  Delivery is best-effort and fire-and-forget: failures
are logged and counted but never raise into the caller — notification fan-out
must not break the pipeline path.

Payloads are JSON with two extra headers:

- ``X-Ecom-Ops-Event`` — the event type.
- ``X-Ecom-Ops-Signature`` — ``sha256=<hex>`` HMAC-SHA256 of the payload using
  the webhook's configured ``secret`` (when set), so receivers can verify the
  message really came from this system.
"""

import hashlib
import hmac
import json
import logging
from typing import Any, Dict

from sqlalchemy import select

from ecommerce_ops.api.metrics import METRIC_OUTBOUND_WEBHOOKS

logger = logging.getLogger("ecommerce_ops.infra.outbound_webhooks")

WILDCARD_EVENT = "*"
SIGNATURE_HEADER = "X-Ecom-Ops-Signature"
EVENT_HEADER = "X-Ecom-Ops-Event"


def sign_payload(body: bytes, secret: str) -> str:
    """HMAC-SHA256 (hex) of a payload body."""
    return hmac.new(secret.encode("utf-8"), body, hashlib.sha256).hexdigest()


def _matches(webhook_events: list, event_type: str) -> bool:
    if WILDCARD_EVENT in webhook_events:
        return True
    return event_type in webhook_events


async def dispatch_outbound_webhook(event_type: str, payload: Dict[str, Any]) -> None:
    """Fan out ``payload`` to every enabled webhook subscribed to the event.

    Best-effort: any failure (DB unavailable, network error) is logged and
    swallowed so notification fan-out can never break the core pipeline.
    """
    try:
        from ecommerce_ops.models.db import OutboundWebhook, async_session_factory

        async with async_session_factory() as session:
            res = await session.execute(
                select(OutboundWebhook).where(OutboundWebhook.enabled.is_(True))
            )
            webhooks = res.scalars().all()
    except Exception:
        logger.debug("Outbound webhook dispatch skipped (DB unavailable)", exc_info=True)
        return

    if not webhooks:
        return

    body = json.dumps(payload, separators=(",", ":")).encode("utf-8")
    headers = {
        "Content-Type": "application/json",
        EVENT_HEADER: event_type,
    }

    import httpx

    async with httpx.AsyncClient(timeout=10) as client:
        for hook in webhooks:
            if not _matches(hook.events, event_type):
                continue
            hook_headers = dict(headers)
            if hook.secret:
                hook_headers[SIGNATURE_HEADER] = sign_payload(body, hook.secret)
            try:
                resp = await client.post(hook.url, content=body, headers=hook_headers)
                if resp.status_code >= 300:
                    raise RuntimeError(f"HTTP {resp.status_code}: {resp.text[:200]}")
                logger.info(
                    "Outbound webhook %s delivered for event %s", hook.name, event_type
                )
                METRIC_OUTBOUND_WEBHOOKS.labels(event_type=event_type, result="sent").inc()
            except Exception as e:
                logger.warning(
                    "Outbound webhook %s failed for event %s: %s", hook.name, event_type, e
                )
                METRIC_OUTBOUND_WEBHOOKS.labels(event_type=event_type, result="failed").inc()


async def send_test_webhook(webhook_id: int) -> bool:
    """Send a synthetic ``test`` event to one webhook. Returns delivery status."""
    from ecommerce_ops.models.db import OutboundWebhook, async_session_factory

    async with async_session_factory() as session:
        res = await session.execute(
            select(OutboundWebhook).where(OutboundWebhook.id == webhook_id)
        )
        hook = res.scalar_one_or_none()
    if hook is None:
        return False

    payload = {"event": "test", "message": "Test webhook from Ecom Ops"}
    body = json.dumps(payload, separators=(",", ":")).encode("utf-8")

    try:
        import httpx

        headers = {"Content-Type": "application/json", EVENT_HEADER: "test"}
        if hook.secret:
            headers[SIGNATURE_HEADER] = sign_payload(body, hook.secret)
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.post(hook.url, content=body, headers=headers)
        if resp.status_code >= 300:
            raise RuntimeError(f"HTTP {resp.status_code}: {resp.text[:200]}")
        return True
    except Exception:
        logger.warning("Outbound webhook test failed: %s", hook.url)
        return False
