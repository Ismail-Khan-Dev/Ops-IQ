"""Email notifications through the Resend API.

The sender is a no-op unless ``RESEND_API_KEY`` is configured, so the rest of
the system degrades gracefully when email is not provisioned. Recipients are
chosen by callers (typically ``settings.NOTIFY_EMAIL``).

Resend is a hosted transactional email API (``POST https://api.resend.com/emails``)
that requires a verified sender domain for ``from`` — configure
``NOTIFY_FROM_EMAIL`` (e.g. ``notifications@yourdomain.com``) in production.
"""

import logging

from ecommerce_ops.config import settings

logger = logging.getLogger("ecommerce_ops.infra.email")


def email_enabled() -> bool:
    """True when a Resend key is configured and senders may fire."""
    return bool(settings.RESEND_API_KEY)


async def send_email(to: str, subject: str, text_body: str) -> bool:
    """Send a plain-text email through Resend. Returns True on success."""
    if not settings.RESEND_API_KEY:
        logger.debug("RESEND_API_KEY not configured, skipping email to %s", to)
        return False

    api_key = settings.RESEND_API_KEY.get_secret_value()
    from_addr = settings.NOTIFY_FROM_EMAIL or "Ecom Ops Agent <notifications@localhost.local>"

    import httpx

    try:
        async with httpx.AsyncClient(timeout=15) as client:
            resp = await client.post(
                "https://api.resend.com/emails",
                headers={"Authorization": f"Bearer {api_key}"},
                json={"from": from_addr, "to": [to], "subject": subject, "text": text_body},
            )
        if resp.status_code >= 300:
            logger.warning(
                "Resend email failed: status=%s body=%s", resp.status_code, resp.text[:200]
            )
            return False
        logger.info("Email notification sent to %s (%s)", to, subject)
        return True
    except Exception:
        logger.exception("Email notification failed to %s", to)
        return False


async def notify_email(subject: str, message: str) -> bool:
    """Send a notification to the configured operator email (no-op without it)."""
    if not settings.NOTIFY_EMAIL:
        return False
    return await send_email(to=settings.NOTIFY_EMAIL, subject=subject, text_body=message)
